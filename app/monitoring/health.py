"""Health-check helpers."""

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class HealthStatus:
    name: str
    status: str
    mode: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
