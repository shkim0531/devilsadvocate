"""반론 카드와 리포트의 형식. Claude의 구조화 출력(JSON 스키마)도 여기서 만든다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Intensity = Literal["mild", "medium", "spicy"]
TargetMode = Literal["auto", "manual"]

INTENSITY_LABELS: dict[str, str] = {"mild": "순한맛", "medium": "보통맛", "spicy": "매운맛"}

CATEGORIES = [
    "숨은 가정",
    "근거 부족",
    "실패 시나리오",
    "기회비용",
    "실행 리스크",
    "이해관계자",
    "인지 편향",
    "기타",
]


class Counterpoint(BaseModel):
    category: str
    point: str


class RebuttalCard(BaseModel):
    decision: str = Field(description="반론 대상이 된 대표의 결정·주장 요약")
    steelman: str = Field(description="대표 논리의 최강 버전")
    weakest_assumption: str
    counterpoints: list[Counterpoint]
    question_now: str
    alternatives: list[str]
    concede_if: str
    severity: int

    @field_validator("severity", mode="before")
    @classmethod
    def _clamp_severity(cls, value: object) -> int:
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 3
        return max(1, min(5, number))


class LiveResult(BaseModel):
    should_rebut: bool
    skip_reason: str = ""
    card: RebuttalCard | None = None


class MeetingReport(BaseModel):
    meeting_summary: str
    cards: list[RebuttalCard]
    overall_assessment: str


_COUNTERPOINT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "point": {"type": "string"},
    },
    "required": ["category", "point"],
    "additionalProperties": False,
}

_CARD_PROPERTIES = {
    "decision": {"type": "string", "description": "반론 대상인 대표의 결정·주장을 한두 문장으로 요약"},
    "steelman": {"type": "string", "description": "대표 논리를 가장 강하게 정리한 버전"},
    "weakest_assumption": {"type": "string", "description": "틀리면 결정 전체가 무너지는 전제"},
    "counterpoints": {"type": "array", "items": _COUNTERPOINT_SCHEMA},
    "question_now": {"type": "string", "description": "회의에서 지금 바로 물어볼 한 문장"},
    "alternatives": {"type": "array", "items": {"type": "string"}},
    "concede_if": {"type": "string", "description": "이것이 확인되면 반론을 거두겠다는 조건"},
    "severity": {"type": "integer", "description": "1(사소함)~5(결정을 재검토해야 함)"},
}

CARD_SCHEMA = {
    "type": "object",
    "properties": _CARD_PROPERTIES,
    "required": list(_CARD_PROPERTIES),
    "additionalProperties": False,
}

LIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "should_rebut": {"type": "boolean"},
        "skip_reason": {"type": "string", "description": "반론하지 않을 때 그 이유, 반론할 때는 빈 문자열"},
        "card": {"anyOf": [CARD_SCHEMA, {"type": "null"}]},
    },
    "required": ["should_rebut", "skip_reason", "card"],
    "additionalProperties": False,
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_summary": {"type": "string"},
        "cards": {"type": "array", "items": CARD_SCHEMA},
        "overall_assessment": {"type": "string"},
    },
    "required": ["meeting_summary", "cards", "overall_assessment"],
    "additionalProperties": False,
}
