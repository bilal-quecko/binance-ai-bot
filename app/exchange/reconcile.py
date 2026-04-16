"""Order reconciliation placeholder."""

from dataclasses import dataclass


@dataclass(slots=True)
class ReconcileResult:
    status: str
    detail: str
