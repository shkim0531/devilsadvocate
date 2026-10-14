"""반론을 만드는 쪽. 실제 Claude 호출(ClaudeRebutter)과 API 키 없이 쓰는 가짜(FakeRebutter)."""

from __future__ import annotations

import json
from typing import Any, Protocol

import anthropic
from pydantic import ValidationError

from . import prompts
from .config import Settings
from .schema import LIVE_SCHEMA, REPORT_SCHEMA, Counterpoint, LiveResult, MeetingReport, RebuttalCard

# 거절(refusal)되면 Anthropic이 권장하는 모델로 서버 쪽에서 자동 재시도한다.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class RebuttalError(RuntimeError):
    """사용자에게 그대로 보여 줄 수 있는 오류."""


class Rebutter(Protocol):
    def live(
        self,
        *,
        transcript: str,
        targets: list[str],
        previous_decisions: list[str],
        intensity: str,
        target_mode: str,
        company_context: str,
        forced: bool,
    ) -> LiveResult: ...

    def report(
        self,
        *,
        transcript: str,
        ceo_speaker: str | None,
        intensity: str,
        company_context: str,
    ) -> MeetingReport: ...


class ClaudeRebutter:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client if client is not None else anthropic.Anthropic()

    def live(
        self,
        *,
        transcript: str,
        targets: list[str],
        previous_decisions: list[str],
        intensity: str,
        target_mode: str,
        company_context: str,
        forced: bool,
    ) -> LiveResult:
        request = self._request(
            system=prompts.system_prompt(intensity, company_context),
            user=prompts.live_user_prompt(transcript, targets, previous_decisions, target_mode, forced),
            schema=LIVE_SCHEMA,
            effort=self.settings.live_effort,
            max_tokens=16000,
        )
        response = self._call(lambda: self.client.beta.messages.create(**request))
        result = _parse(response, LiveResult)
        if result.should_rebut and result.card is None:
            return LiveResult(should_rebut=False, skip_reason="반론 내용이 비어 있습니다.")
        return result

    def report(
        self,
        *,
        transcript: str,
        ceo_speaker: str | None,
        intensity: str,
        company_context: str,
    ) -> MeetingReport:
        request = self._request(
            system=prompts.system_prompt(intensity, company_context),
            user=prompts.report_user_prompt(transcript, ceo_speaker),
            schema=REPORT_SCHEMA,
            effort=self.settings.report_effort,
            max_tokens=64000,
        )

        def stream() -> Any:
            # 회의록이 길면 응답도 길어지므로 스트리밍으로 받아 HTTP 시간 초과를 피한다.
            with self.client.beta.messages.stream(**request) as s:
                return s.get_final_message()

        response = self._call(stream)
        report = _parse(response, MeetingReport)
        report.cards.sort(key=lambda c: c.severity, reverse=True)
        return report

    def _request(self, *, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> dict:
        return {
            "model": self.settings.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    @staticmethod
    def _call(fn: Any) -> Any:
        try:
            return fn()
        except anthropic.AuthenticationError as exc:
            raise RebuttalError("API 키가 올바르지 않습니다. .env의 ANTHROPIC_API_KEY를 확인하세요.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise RebuttalError("이 API 키로는 모델을 쓸 권한이 없습니다.") from exc
        except anthropic.NotFoundError as exc:
            raise RebuttalError("모델을 찾지 못했습니다. DA_MODEL 설정을 확인하세요.") from exc
        except anthropic.RateLimitError as exc:
            raise RebuttalError("요청 한도를 넘었습니다. 잠시 후 다시 시도하세요.") from exc
        except anthropic.BadRequestError as exc:
            raise RebuttalError(f"요청이 거부되었습니다: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise RebuttalError(f"Claude 서버 오류({exc.status_code})입니다. 잠시 후 다시 시도하세요.") from exc
        except anthropic.APIConnectionError as exc:
            raise RebuttalError("Claude 서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.") from exc


def _parse(response: Any, model: type) -> Any:
    if response.stop_reason == "refusal":
        raise RebuttalError("Claude가 이 요청에 대한 응답을 거절했습니다.")
    if response.stop_reason == "max_tokens":
        raise RebuttalError("응답이 너무 길어 중간에 끊겼습니다. 회의록을 나눠서 다시 시도하세요.")
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise RebuttalError("Claude 응답이 비어 있습니다.")
    try:
        return model.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RebuttalError("Claude 응답 형식을 읽지 못했습니다.") from exc


class FakeRebutter:
    """API 키 없이 화면 흐름을 확인하는 가짜 응답. 내용은 입력을 그대로 되돌려 주는 수준이다."""

    def live(
        self,
        *,
        transcript: str,
        targets: list[str],
        previous_decisions: list[str],
        intensity: str,
        target_mode: str,
        company_context: str,
        forced: bool,
    ) -> LiveResult:
        statement = targets[-1] if targets else (transcript.strip().split("\n")[-1] if transcript.strip() else "")
        if not statement:
            return LiveResult(should_rebut=False, skip_reason="반론할 발언이 없습니다.")
        return LiveResult(should_rebut=True, card=_fake_card(statement))

    def report(
        self,
        *,
        transcript: str,
        ceo_speaker: str | None,
        intensity: str,
        company_context: str,
    ) -> MeetingReport:
        lines = [line for line in transcript.split("\n") if line.strip()]
        picked = [line for line in lines if ceo_speaker and f"{ceo_speaker}:" in line] or lines
        return MeetingReport(
            meeting_summary=f"[가짜 응답] 발언 {len(lines)}개짜리 회의록입니다.",
            cards=[_fake_card(line) for line in picked[:2]],
            overall_assessment="[가짜 응답] 실제 반론은 API 키를 넣고 DA_FAKE_LLM을 끄면 볼 수 있습니다.",
        )


def _fake_card(statement: str) -> RebuttalCard:
    return RebuttalCard(
        decision=f"[가짜 응답] {statement[:80]}",
        steelman="(가짜) 대표 논리를 가장 강하게 정리한 내용이 여기에 들어갑니다.",
        weakest_assumption="(가짜) 이 결정이 기대는 가장 약한 전제가 여기에 들어갑니다.",
        counterpoints=[
            Counterpoint(category="숨은 가정", point="(가짜) 숨은 가정에 대한 반론"),
            Counterpoint(category="실행 리스크", point="(가짜) 실행 리스크에 대한 반론"),
        ],
        question_now="(가짜) 이 결정이 실패하면 가장 먼저 어디서 알 수 있을까요?",
        alternatives=["(가짜) 작게 시험해 보고 확대하는 방안"],
        concede_if="(가짜) 이런 근거가 확인되면 반론을 거둡니다.",
        severity=3,
    )
