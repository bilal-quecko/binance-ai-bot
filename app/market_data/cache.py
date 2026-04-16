"""In-memory market cache."""

from collections import defaultdict
from typing import Any


class MarketCache:
    """Very small in-memory cache for development."""

    def __init__(self) -> None:
        self._data: dict[str, list[Any]] = defaultdict(list)

    def push(self, key: str, value: Any) -> None:
        self._data[key].append(value)

    def get(self, key: str) -> list[Any]:
        return self._data.get(key, [])
