from typing import Literal

from pydantic import BaseModel, Field


class AIAnalysis(BaseModel):
    condition_assessment: str | Literal["unknown"] = "unknown"
    detected_issues: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    deal_quality: str | Literal["unknown"] = "unknown"
    confidence: float = Field(ge=0, le=1, default=0)


class AIService:
    async def analyze(self, **_: object) -> AIAnalysis:
        return AIAnalysis(missing_information=["AI provider is disabled"])
