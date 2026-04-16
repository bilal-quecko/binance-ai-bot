"""Metrics placeholders."""

from dataclasses import dataclass


@dataclass(slots=True)
class MetricPoint:
    name: str
    value: float
    unit: str = "count"
