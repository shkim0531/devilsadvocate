"""환경 변수(.env 포함)에서 읽는 실행 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    # 실시간 반론은 빨라야 하므로 medium, 회의록 리포트는 꼼꼼하게 high.
    live_effort: str = "medium"
    report_effort: str = "high"
    # 반론 사이 최소 간격(초)과, 말이 멈췄다고 보는 침묵 길이(초).
    min_interval: float = 30.0
    pause_seconds: float = 2.5
    # API 키 없이 화면 흐름을 확인할 때 쓰는 가짜 응답 모드.
    fake_llm: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model=os.environ.get("DA_MODEL", "").strip() or DEFAULT_MODEL,
            live_effort=os.environ.get("DA_LIVE_EFFORT", "").strip() or "medium",
            report_effort=os.environ.get("DA_REPORT_EFFORT", "").strip() or "high",
            min_interval=_float("DA_MIN_INTERVAL", 30.0),
            pause_seconds=_float("DA_PAUSE_SECONDS", 2.5),
            fake_llm=_bool("DA_FAKE_LLM"),
        )


def has_api_credentials() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY", "").strip()
        or os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    )
