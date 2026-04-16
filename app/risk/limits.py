"""Risk limit checks."""

from app.risk.models import RiskDecision


def check_daily_loss(current_drawdown: float, max_daily_loss: float) -> RiskDecision:
    if current_drawdown >= max_daily_loss:
        return RiskDecision(approved=False, reason="daily_loss_limit_reached")
    return RiskDecision(approved=True, reason="ok")
