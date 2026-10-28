"""Importing this package registers every service collector."""

from src.aws_inventory.collectors import (  # noqa: F401
    apigateway,
    cloudfront,
    containers,
    dynamodb,
    ec2,
    elbv2,
    iam,
    lambda_,
    messaging,
    rds,
    s3,
)
from src.aws_inventory.collectors.base import COLLECTORS, Collector, register  # noqa: F401
