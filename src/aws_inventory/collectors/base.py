"""Collector registry: each service registers one function that lists its resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from src.aws_inventory.model import Resource
from src.aws_inventory.session import Context

CollectFn = Callable[[Context, str], list[Resource]]


@dataclass(frozen=True)
class Collector:
    """A service collector; ``global`` collectors run once instead of once per region."""

    service: str
    scope: Literal["regional", "global"]
    collect: CollectFn


COLLECTORS: dict[str, Collector] = {}


def register(
    service: str, scope: Literal["regional", "global"] = "regional"
) -> Callable[[CollectFn], CollectFn]:
    """Decorator that adds a collect function to the registry."""

    def decorator(fn: CollectFn) -> CollectFn:
        COLLECTORS[service] = Collector(service=service, scope=scope, collect=fn)
        return fn

    return decorator
