"""Tests for run logging/telemetry: per-call timing, START/DONE lines, heartbeat, report."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

import boto3
import pytest
from botocore.awsrequest import AWSResponse

from src.aws_inventory import telemetry
from src.aws_inventory.cli import configure_logging
from src.aws_inventory.collectors import COLLECTORS
from src.aws_inventory.collectors.base import Collector
from src.aws_inventory.model import Resource
from src.aws_inventory.runner import _run_collector, plan_tasks, task_name
from src.aws_inventory.session import CLIENT_CONFIG, Context
from src.aws_inventory.telemetry import Cancelled, Progress

ACCOUNT = "123456789012"
REGION = "us-east-1"
TELEMETRY_LOGGER = "src.aws_inventory.telemetry"


def make_ctx() -> Context:
    return Context(boto3.Session(), ACCOUNT)


def instrumented(
    ctx: Context,
    responses: dict[str, dict[str, Any]] | None = None,
    on_call: Callable[[], None] | None = None,
) -> Any:
    """A real botocore SQS client with canned responses and the telemetry hooks attached."""
    client = boto3.client(
        "sqs", region_name=REGION, aws_access_key_id="AKIATEST", aws_secret_access_key="secret"
    )
    ctx.telemetry.instrument(client, REGION)

    def handler(model: Any, **_: Any) -> tuple[AWSResponse, dict[str, Any]]:
        if on_call:
            on_call()
        return AWSResponse("http://fake", 200, {}, None), (responses or {}).get(model.name, {})

    client.meta.events.register("before-call", handler)
    return client


def test_api_call_hooks_log_operation_and_duration_not_params(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = make_ctx()
    metadata = {"HTTPStatusCode": 200, "RetryAttempts": 1}
    client = instrumented(ctx, {"ListQueues": {"ResponseMetadata": metadata}})
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        client.list_queues(QueueNamePrefix="super-secret-prefix")

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "API sqs.ListQueues region=us-east-1" in text
    assert "status=200 retries=1" in text
    assert ctx.telemetry.retries == 1
    assert ctx.telemetry.api_calls == 1
    assert "super-secret-prefix" not in text
    assert "AKIATEST" not in text


def test_slow_call_logs_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = make_ctx()
    client = instrumented(ctx)
    monkeypatch.setattr(telemetry, "SLOW_CALL_SECONDS", 0.0)
    with caplog.at_level(logging.WARNING, logger=TELEMETRY_LOGGER):
        client.list_queues()
    assert any("SLOW CALL sqs.ListQueues" in r.getMessage() for r in caplog.records)
    assert ctx.telemetry.slow_calls == 1


def test_cancelled_run_aborts_next_api_call() -> None:
    ctx = make_ctx()
    client = instrumented(ctx)
    ctx.telemetry.cancelled.set()
    with pytest.raises(Cancelled):
        client.list_queues()


def test_record_error_logs_warning_and_counts_against_task(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = make_ctx()
    with caplog.at_level(logging.WARNING):
        with ctx.telemetry.task("demo/us-east-1", "demo"):
            ctx.record_error("demo", REGION, "ListThings", RuntimeError("boom"))
    assert any(
        r.levelname == "WARNING" and "ERROR demo/us-east-1 ListThings" in r.getMessage()
        for r in caplog.records
    )
    assert ctx.telemetry.records[0].errors == 1


def test_run_collector_logs_start_and_done_with_type_breakdown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake(ctx: Context, region: str) -> list[Resource]:
        return [
            Resource("demo", "box", "a", None, region),
            Resource("demo", "box", "b", None, region),
            Resource("demo", "tube", "c", None, region),
        ]

    ctx = make_ctx()
    ctx.telemetry.tasks_total = 1
    with caplog.at_level(logging.INFO, logger=TELEMETRY_LOGGER):
        _run_collector(ctx, Collector("demo", "regional", fake), REGION)
    messages = [r.getMessage() for r in caplog.records]
    assert "START demo/us-east-1" in messages
    done = next(m for m in messages if m.startswith("DONE  demo/us-east-1"))
    assert "[1/1]: 3 resources (box=2, tube=1), 0 errors" in done


def test_heartbeat_lists_in_flight_tasks_and_current_call() -> None:
    ctx = make_ctx()
    tel = ctx.telemetry
    tel.tasks_total = 5
    release, inside = threading.Event(), threading.Event()

    def block() -> None:
        inside.set()
        release.wait(5)

    client = instrumented(ctx, on_call=block)

    def work() -> None:
        with tel.task("iam/global", "iam"):
            client.list_queues()

    thread = threading.Thread(target=work)
    thread.start()
    assert inside.wait(5)
    lines = tel.heartbeat_lines(error_count=2)
    release.set()
    thread.join()

    assert lines[0].startswith("HEARTBEAT")
    assert "tasks 0/5 done, 1 running" in lines[0]
    assert "errors 2" in lines[0]
    assert any("running iam/global" in line and "in sqs.ListQueues" in line for line in lines[1:])


def test_plan_tasks_puts_global_collectors_first_and_tasks_are_named() -> None:
    selected = [COLLECTORS[name] for name in sorted(COLLECTORS)]
    tasks = plan_tasks(selected, ["us-east-1", "eu-west-1"], "us-east-1")
    first_regional = next(i for i, (c, _) in enumerate(tasks) if c.scope == "regional")
    assert {c.service for c, _ in tasks[:first_regional]} == {"iam", "s3", "cloudfront"}
    assert all(c.scope == "regional" for c, _ in tasks[first_regional:])
    assert len(tasks) == 3 + 10 * 2
    assert task_name(COLLECTORS["iam"], "us-east-1") == "iam/global"
    assert task_name(COLLECTORS["ec2"], "eu-west-1") == "ec2/eu-west-1"


def test_client_config_has_timeouts_and_bounded_retries() -> None:
    assert CLIENT_CONFIG.connect_timeout == 10
    assert CLIENT_CONFIG.read_timeout == 30
    assert CLIENT_CONFIG.retries["max_attempts"] == 5


def test_progress_logs_at_interval_and_completion(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=TELEMETRY_LOGGER):
        progress = Progress("iam roles", 5, every=2)
        for _ in range(5):
            progress.tick()
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0] == "iam roles: 5 to process"
    assert [m.split(" (")[0] for m in messages[1:]] == [
        "iam roles: 2/5",
        "iam roles: 4/5",
        "iam roles: 5/5",
    ]


def test_log_file_is_written_without_botocore_debug(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "run.log"
    configure_logging(verbose=False, log_path=log_path)
    try:
        logging.getLogger("src.aws_inventory.demo").debug("detail line")
        logging.getLogger("botocore.endpoint").debug("Credential=AKIASECRET signed headers")
        for handler in logging.getLogger().handlers:
            handler.flush()
        text = log_path.read_text(encoding="utf-8")
    finally:
        for handler in list(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)
    assert "detail line" in text
    assert "[MainThread]" in text
    assert "AKIASECRET" not in text


def test_end_of_run_report_lists_services_and_slowest_tasks() -> None:
    ctx = make_ctx()
    with ctx.telemetry.task("ec2/us-east-1", "ec2") as record:
        record.set_result([Resource("ec2", "instance", "i-1", None, REGION)])
    report = "\n".join(ctx.telemetry.report_lines(error_count=0))
    assert "RUN REPORT" in report
    assert "Slowest 10 tasks" in report
    assert "ec2/us-east-1 (1 resources, 0 errors)" in report
    assert "API calls 0" in report
