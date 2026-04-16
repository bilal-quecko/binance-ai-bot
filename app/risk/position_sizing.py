"""Position sizing placeholders."""


def fixed_fraction_size(equity: float, risk_per_trade: float) -> float:
    return equity * risk_per_trade
