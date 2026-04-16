"""Indicator placeholders."""

from collections.abc import Sequence


def sma(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    return sum(values) / len(values)
