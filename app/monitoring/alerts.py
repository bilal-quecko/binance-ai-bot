"""Alert placeholders."""

from dataclasses import dataclass


@dataclass(slots=True)
class AlertEvent:
    code: str
    message: str
    severity: str = "info"
