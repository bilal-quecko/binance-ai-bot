from app.risk.limits import check_daily_loss


def test_daily_loss_limit_blocks() -> None:
    decision = check_daily_loss(current_drawdown=0.03, max_daily_loss=0.02)
    assert decision.approved is False
    assert decision.reason == "daily_loss_limit_reached"
