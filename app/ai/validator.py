"""AI validator placeholders."""

from app.ai.schemas import AiDecision


def validate_ai_decision(payload: dict) -> AiDecision:
    return AiDecision.model_validate(payload)
