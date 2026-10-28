"""Run telemetry: per-call API timing, in-flight tracking, heartbeat and end-of-run report.

Everything here only observes. Only operation names, regions, durations and status codes are
logged; request parameters, headers and credentials are never touched.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

SLOW_CALL_SECONDS = 10.0
HEARTBEAT_SECONDS = 30.0
MAX_HEARTBEAT_LINES = 12
SLOWEST_TASKS_SHOWN = 10

THROTTLE_CODES = {
    "Throttling",
    "ThrottlingException",
    "ThrottledException",
    "RequestThrottledException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "TransactionInProgressException",
    "RequestLimitExceeded",
    "BandwidthLimitExceeded",
    "LimitExceededException",
    "RequestThrottled",
    "SlowDown",
    "PriorRequestNotComplete",
    "EC2ThrottledException",
}


class Cancelled(BaseException):
    """Raised in worker threads once the run is cancelled (derives BaseException so the
    collectors' broad ``except Exception`` handlers do not swallow it)."""


_local = threading.local()


def current_task() -> str | None:
    """Name of the task the calling thread is working for, if any."""
    return getattr(_local, "task", None)


@contextmanager
def bind_task(name: str | None) -> Iterator[None]:
    """Attribute API calls made by this thread to ``name`` (used for nested worker threads)."""
    previous = current_task()
    _local.task = name
    try:
        yield
    finally:
        _local.task = previous


def format_duration(seconds: float) -> str:
    """Format seconds as ``1m05s`` (or ``4.2s`` under a minute)."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


@dataclass
class TaskRecord:
    """Outcome of one collector/discovery task."""

    name: str
    service: str
    resources: int = 0
    types: dict[str, int] = field(default_factory=dict)
    errors: int = 0
    seconds: float = 0.0
    outcome: str = "ok"

    def set_result(self, resources: list[Any]) -> None:
        """Record how many resources were found, broken down by resource type."""
        self.resources = len(resources)
        self.types = dict(sorted(Counter(r.type for r in resources).items()))


@dataclass
class ActiveCall:
    """An API call that is currently on the wire."""

    task: str | None
    operation: str
    region: str
    started: float


class Telemetry:
    """Thread-safe counters and in-flight state for one inventory run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.monotonic()
        self.cancelled = threading.Event()
        self.api_calls = 0
        self.failed_calls = 0
        self.retries = 0
        self.throttles = 0
        self.slow_calls = 0
        self.tasks_total = 0
        self.tasks_done = 0
        self.records: list[TaskRecord] = []
        self._running: dict[str, float] = {}
        self._calls: dict[int, ActiveCall] = {}
        self._task_errors: Counter[str] = Counter()

    # -- botocore hooks -------------------------------------------------------------------

    def instrument(self, client: Any, region: str) -> None:
        """Attach timing/retry/throttle hooks to a boto3 client."""
        events = client.meta.events

        def before_call(model: Any, context: dict[str, Any], **_: Any) -> None:
            if self.cancelled.is_set():
                raise Cancelled()
            operation = f"{model.service_model.service_name}.{model.name}"
            now = time.monotonic()
            context["inventory_call"] = (operation, now)
            with self._lock:
                self._calls[threading.get_ident()] = ActiveCall(
                    current_task(), operation, region, now
                )

        def after_call(parsed: dict[str, Any], context: dict[str, Any], **_: Any) -> None:
            metadata = parsed.get("ResponseMetadata", {})
            self._finish(
                context,
                region,
                status=metadata.get("HTTPStatusCode"),
                retries=metadata.get("RetryAttempts", 0),
                error_code=(parsed.get("Error") or {}).get("Code"),
            )

        def after_call_error(exception: Exception, context: dict[str, Any], **_: Any) -> None:
            self._finish(context, region, exception=exception)

        def needs_retry(response: Any = None, **_: Any) -> None:
            parsed = response[1] if response else None
            if not isinstance(parsed, dict):
                return None
            code = (parsed.get("Error") or {}).get("Code")
            status = (parsed.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            if code in THROTTLE_CODES or status == 429:
                with self._lock:
                    self.throttles += 1
            return None

        events.register("before-call", before_call)
        events.register("after-call", after_call)
        events.register("after-call-error", after_call_error)
        events.register("needs-retry", needs_retry)

    def _finish(
        self,
        context: dict[str, Any],
        region: str,
        *,
        status: int | None = None,
        retries: int = 0,
        error_code: str | None = None,
        exception: Exception | None = None,
    ) -> None:
        operation, started = context.get("inventory_call", ("unknown", time.monotonic()))
        seconds = time.monotonic() - started
        if exception is not None:
            retries = (
                getattr(exception, "response", {})
                .get("ResponseMetadata", {})
                .get("RetryAttempts", 0)
            )
        slow = seconds >= SLOW_CALL_SECONDS
        with self._lock:
            self._calls.pop(threading.get_ident(), None)
            self.api_calls += 1
            self.retries += retries or 0
            self.slow_calls += slow
            self.failed_calls += exception is not None

        if exception is not None:
            logger.warning(
                "API CALL FAILED %s region=%s after %.1fs: %s",
                operation,
                region,
                seconds,
                type(exception).__name__,
            )
        elif slow:
            logger.warning(
                "SLOW CALL %s region=%s took %.1fs status=%s retries=%s",
                operation,
                region,
                seconds,
                status,
                retries,
            )
        else:
            logger.debug(
                "API %s region=%s %.2fs status=%s retries=%s%s",
                operation,
                region,
                seconds,
                status,
                retries,
                f" error={error_code}" if error_code else "",
            )

    # -- tasks ----------------------------------------------------------------------------

    def note_error(self) -> None:
        """Count a recorded error against the task the calling thread belongs to."""
        task = current_task()
        if task:
            with self._lock:
                self._task_errors[task] += 1

    @contextmanager
    def task(self, name: str, service: str) -> Iterator[TaskRecord]:
        """Track one unit of work: logs START/DONE and keeps timing for the final report."""
        record = TaskRecord(name=name, service=service)
        started = time.monotonic()
        with self._lock:
            self._running[name] = started
        logger.info("START %s", name)
        try:
            with bind_task(name):
                yield record
        except BaseException:
            record.outcome = "aborted"
            raise
        finally:
            record.seconds = time.monotonic() - started
            with self._lock:
                self._running.pop(name, None)
                self.tasks_done += 1
                record.errors = self._task_errors.get(name, 0)
                self.records.append(record)
                done, total = self.tasks_done, self.tasks_total
            breakdown = ", ".join(f"{t}={n}" for t, n in record.types.items())
            logger.info(
                "DONE  %s [%d/%d]: %d resources%s, %d errors, %s%s",
                name,
                done,
                total,
                record.resources,
                f" ({breakdown})" if breakdown else "",
                record.errors,
                format_duration(record.seconds),
                "" if record.outcome == "ok" else f" [{record.outcome}]",
            )

    # -- heartbeat ------------------------------------------------------------------------

    def heartbeat_lines(self, error_count: int) -> list[str]:
        """Describe overall progress and what every running task is doing right now."""
        now = time.monotonic()
        with self._lock:
            running = sorted(self._running.items(), key=lambda item: item[1])
            calls = list(self._calls.values())
            lines = [
                f"HEARTBEAT {format_duration(now - self.started)} elapsed | "
                f"tasks {self.tasks_done}/{self.tasks_total} done, {len(running)} running | "
                f"errors {error_count} | API calls {self.api_calls} "
                f"(retries {self.retries}, throttled {self.throttles}, "
                f"slow {self.slow_calls}, failed {self.failed_calls})"
            ]
        by_task: dict[str | None, list[ActiveCall]] = defaultdict(list)
        for call in calls:
            by_task[call.task].append(call)
        for name, started in running[:MAX_HEARTBEAT_LINES]:
            active = sorted(by_task.get(name, []), key=lambda c: c.started)
            if active:
                oldest = active[0]
                detail = f"in {oldest.operation} ({oldest.region}) for {now - oldest.started:.1f}s"
                if len(active) > 1:
                    detail += f" [+{len(active) - 1} more concurrent calls]"
            else:
                detail = "between API calls"
            lines.append(f"  running {name} for {format_duration(now - started)}: {detail}")
        if len(running) > MAX_HEARTBEAT_LINES:
            lines.append(f"  ... and {len(running) - MAX_HEARTBEAT_LINES} more running")
        return lines

    def start_heartbeat(
        self, error_count: Callable[[], int], interval: float = HEARTBEAT_SECONDS
    ) -> threading.Event:
        """Log a heartbeat every ``interval`` seconds until the returned event is set."""
        stop = threading.Event()

        def loop() -> None:
            while not stop.wait(interval):
                for line in self.heartbeat_lines(error_count()):
                    logger.info(line)

        threading.Thread(target=loop, name="heartbeat", daemon=True).start()
        return stop

    # -- final report ---------------------------------------------------------------------

    def report_lines(self, error_count: int) -> list[str]:
        """Per-service timing table, slowest tasks and API totals."""
        with self._lock:
            records = list(self.records)
            counters = (self.api_calls, self.retries, self.throttles, self.slow_calls)
            failed = self.failed_calls
        per_service: dict[str, list[TaskRecord]] = defaultdict(list)
        for record in records:
            per_service[record.service].append(record)

        lines = [
            "RUN REPORT",
            f"  {'service':<19}{'tasks':>6}{'resources':>10}{'errors':>8}"
            f"{'total':>10}{'avg':>9}{'max':>9}",
        ]
        for service in sorted(per_service):
            items = per_service[service]
            total = sum(r.seconds for r in items)
            lines.append(
                f"  {service:<19}{len(items):>6}{sum(r.resources for r in items):>10}"
                f"{sum(r.errors for r in items):>8}{format_duration(total):>10}"
                f"{format_duration(total / len(items)):>9}"
                f"{format_duration(max(r.seconds for r in items)):>9}"
            )
        lines.append(f"  Slowest {SLOWEST_TASKS_SHOWN} tasks:")
        for record in sorted(records, key=lambda r: r.seconds, reverse=True)[:SLOWEST_TASKS_SHOWN]:
            lines.append(
                f"    {format_duration(record.seconds):>8}  {record.name}"
                f" ({record.resources} resources, {record.errors} errors)"
            )
        api_calls, retries, throttles, slow = counters
        lines.append(
            f"  API calls {api_calls} | retries {retries} | throttled {throttles} | "
            f"slow (>{SLOW_CALL_SECONDS:.0f}s) {slow} | failed {failed} | "
            f"errors recorded {error_count} | "
            f"wall time {format_duration(time.monotonic() - self.started)}"
        )
        return lines


class Progress:
    """Thread-safe 'n/total' progress logger for long loops (IAM principals, buckets, ...)."""

    def __init__(self, label: str, total: int, every: int = 25) -> None:
        self.label = label
        self.total = total
        self.every = every
        self._count = 0
        self._started = time.monotonic()
        self._lock = threading.Lock()
        logger.info("%s: %d to process", label, total)

    def wrap(self, fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Wrap a per-item function so each call (success or failure) counts as progress."""

        def run(item: Any) -> Any:
            try:
                return fn(item)
            finally:
                self.tick()

        return run

    def tick(self) -> None:
        """Mark one item done; logs every ``every`` items and at the end."""
        with self._lock:
            self._count += 1
            count = self._count
        if count % self.every == 0 or count == self.total:
            logger.info(
                "%s: %d/%d (%s)",
                self.label,
                count,
                self.total,
                format_duration(time.monotonic() - self._started),
            )
