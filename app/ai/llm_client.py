"""LLM client placeholder."""

from app.ai.schemas import AiDecision


class LlmClient:
    async def analyze(self) -> AiDecision:
        raise NotImplementedError("AI integration is not implemented in the scaffold.")
