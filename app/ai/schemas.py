"""AI schema placeholders."""

from pydantic import BaseModel


class AiDecision(BaseModel):
    regime: str
    action_bias: str
    quality_score: float
    risk_note: str
    block_trade: bool = False
