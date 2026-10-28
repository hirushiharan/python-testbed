"""SQS queues and SNS topics.

Both are activity-based: a queue is active if messages were sent in the lookback window, a
topic if messages were published.
"""

from __future__ import annotations

import json
from typing import Any

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context


@register("sqs")
def collect_sqs(ctx: Context, region: str) -> list[Resource]:
    """List SQS queues in one region."""
    client = ctx.client("sqs", region)
    urls = list(ctx.paginate("sqs", region, "list_queues", "QueueUrls"))
    resources = [r for r in ctx.map(lambda url: _queue(ctx, client, region, url), urls) if r]

    activity = latest_activity(
        ctx,
        "sqs",
        region,
        {
            r.id: MetricQuery("AWS/SQS", "NumberOfMessagesSent", {"QueueName": r.id})
            for r in resources
        },
    )
    for resource in resources:
        last, source, active = apply_activity(
            activity, resource.id, "cloudwatch:NumberOfMessagesSent"
        )
        resource.last_activity, resource.last_activity_source, resource.is_active = (
            last,
            source,
            active,
        )
    return resources


def _queue(ctx: Context, client: Any, region: str, url: str) -> Resource | None:
    name = url.rsplit("/", 1)[-1]
    attributes = ctx.safe(
        "sqs",
        region,
        f"GetQueueAttributes:{name}",
        lambda: client.get_queue_attributes(QueueUrl=url, AttributeNames=["All"]).get(
            "Attributes", {}
        ),
    )
    if attributes is None:
        return None
    tags = ctx.safe(
        "sqs",
        region,
        f"ListQueueTags:{name}",
        lambda: client.list_queue_tags(QueueUrl=url).get("Tags", {}),
        {},
    )
    redrive = json.loads(attributes["RedrivePolicy"]) if attributes.get("RedrivePolicy") else {}
    return Resource(
        service="sqs",
        type="queue",
        id=name,
        arn=attributes.get("QueueArn"),
        region=region,
        name=name,
        status="available",
        created_at=iso(int(attributes["CreatedTimestamp"]))
        if attributes.get("CreatedTimestamp")
        else None,
        tags=tags_to_dict(tags),
        metadata={
            "url": url,
            "fifo": attributes.get("FifoQueue") == "true",
            "messages_available": attributes.get("ApproximateNumberOfMessages"),
            "messages_in_flight": attributes.get("ApproximateNumberOfMessagesNotVisible"),
            "messages_delayed": attributes.get("ApproximateNumberOfMessagesDelayed"),
            "visibility_timeout_s": attributes.get("VisibilityTimeout"),
            "retention_s": attributes.get("MessageRetentionPeriod"),
        },
        dependencies=deps(
            dep("dead-letter-queue", redrive.get("deadLetterTargetArn"), "sqs"),
            dep("kms-key", attributes.get("KmsMasterKeyId"), "kms"),
        ),
    )


@register("sns")
def collect_sns(ctx: Context, region: str) -> list[Resource]:
    """List SNS topics and their subscriptions in one region."""
    client = ctx.client("sns", region)
    arns = [t["TopicArn"] for t in ctx.paginate("sns", region, "list_topics", "Topics")]
    resources = [r for r in ctx.map(lambda arn: _topic(ctx, client, region, arn), arns) if r]

    activity = latest_activity(
        ctx,
        "sns",
        region,
        {
            r.id: MetricQuery("AWS/SNS", "NumberOfMessagesPublished", {"TopicName": r.id})
            for r in resources
        },
    )
    for resource in resources:
        last, source, active = apply_activity(
            activity, resource.id, "cloudwatch:NumberOfMessagesPublished"
        )
        resource.last_activity, resource.last_activity_source, resource.is_active = (
            last,
            source,
            active,
        )
    return resources


def _topic(ctx: Context, client: Any, region: str, arn: str) -> Resource | None:
    name = arn.rsplit(":", 1)[-1]
    attributes = ctx.safe(
        "sns",
        region,
        f"GetTopicAttributes:{name}",
        lambda: client.get_topic_attributes(TopicArn=arn).get("Attributes", {}),
    )
    if attributes is None:
        return None
    tags = ctx.safe(
        "sns",
        region,
        f"ListTagsForResource:{name}",
        lambda: client.list_tags_for_resource(ResourceArn=arn).get("Tags", []),
        [],
    )
    subscriptions = (
        ctx.safe(
            "sns",
            region,
            f"ListSubscriptionsByTopic:{name}",
            lambda: list(
                ctx.paginate(
                    "sns", region, "list_subscriptions_by_topic", "Subscriptions", TopicArn=arn
                )
            ),
            [],
        )
        or []
    )
    return Resource(
        service="sns",
        type="topic",
        id=name,
        arn=arn,
        region=region,
        name=name,
        status="available",
        tags=tags_to_dict(tags),
        metadata={
            "display_name": attributes.get("DisplayName") or None,
            "fifo": attributes.get("FifoTopic") == "true",
            "subscriptions_confirmed": attributes.get("SubscriptionsConfirmed"),
            "subscriptions_pending": attributes.get("SubscriptionsPending"),
            "subscription_protocols": sorted({s.get("Protocol", "") for s in subscriptions}),
        },
        dependencies=deps(
            dep("kms-key", attributes.get("KmsMasterKeyId"), "kms"),
            *[
                dep(f"delivers-to:{s.get('Protocol')}", s.get("Endpoint"))
                for s in subscriptions
                if str(s.get("Endpoint", "")).startswith("arn:")
            ],
        ),
    )
