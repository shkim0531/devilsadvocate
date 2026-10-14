import anthropic
import httpx2 as httpx
import pytest

from devils_advocate import prompts
from devils_advocate.config import Settings
from devils_advocate.llm import FALLBACK_BETA, ClaudeRebutter, FakeRebutter, RebuttalError
from devils_advocate.schema import LIVE_SCHEMA, REPORT_SCHEMA, RebuttalCard

from .conftest import FakeClient, make_card, text_response

LIVE_ARGS = dict(
    transcript="대표: 출시합시다",
    targets=["출시합시다"],
    previous_decisions=[],
    intensity="spicy",
    target_mode="auto",
    company_context="직원 12명",
    forced=False,
)
REPORT_ARGS = dict(transcript="[00:05] 대표: 출시합시다", ceo_speaker="대표", intensity="mild", company_context="")


def rebutter(response=None, error=None, **settings):
    client = FakeClient(response=response, error=error)
    return ClaudeRebutter(Settings(**settings), client=client), client


def test_live_request_shape():
    r, client = rebutter(text_response({"should_rebut": True, "skip_reason": "", "card": make_card()}))
    result = r.live(**LIVE_ARGS)
    assert result.should_rebut and result.card.severity == 4
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"]["effort"] == "medium"
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": LIVE_SCHEMA}
    assert req["betas"] == [FALLBACK_BETA] and req["fallbacks"] == "default"
    assert "thinking" not in req  # Opus 5.5는 항상 생각하므로 따로 켜지 않는다.
    assert "직원 12명" in req["system"]
    assert "매운맛" in req["system"]


def test_live_skip():
    r, _ = rebutter(text_response({"should_rebut": False, "skip_reason": "인사말", "card": None}))
    result = r.live(**LIVE_ARGS)
    assert not result.should_rebut and result.skip_reason == "인사말"


def test_live_should_rebut_without_card_becomes_skip():
    r, _ = rebutter(text_response({"should_rebut": True, "skip_reason": "", "card": None}))
    assert not r.live(**LIVE_ARGS).should_rebut


def test_report_streams_and_sorts_by_severity():
    payload = {
        "meeting_summary": "요약",
        "cards": [make_card(severity=2, decision="A"), make_card(severity=5, decision="B")],
        "overall_assessment": "총평",
    }
    r, client = rebutter(text_response(payload), report_effort="xhigh")
    report = r.report(**REPORT_ARGS)
    assert [c.decision for c in report.cards] == ["B", "A"]
    req = client.requests[0]
    assert req["output_config"]["format"]["schema"] == REPORT_SCHEMA
    assert req["output_config"]["effort"] == "xhigh"
    assert "대표 화자는 '대표'" in req["messages"][0]["content"]


@pytest.mark.parametrize(
    ("stop_reason", "message"),
    [("refusal", "거절"), ("max_tokens", "끊겼")],
)
def test_bad_stop_reasons(stop_reason, message):
    r, _ = rebutter(text_response({}, stop_reason=stop_reason))
    with pytest.raises(RebuttalError, match=message):
        r.live(**LIVE_ARGS)


def test_invalid_json():
    r, _ = rebutter(text_response("not json"))
    with pytest.raises(RebuttalError, match="형식"):
        r.live(**LIVE_ARGS)


def _status_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("오류", response=response, body=None)


@pytest.mark.parametrize(
    ("error_cls", "status", "message"),
    [
        (anthropic.AuthenticationError, 401, "API 키"),
        (anthropic.RateLimitError, 429, "한도"),
        (anthropic.NotFoundError, 404, "모델"),
        (anthropic.InternalServerError, 500, "500"),
    ],
)
def test_api_errors_become_rebuttal_errors(error_cls, status, message):
    r, _ = rebutter(error=_status_error(error_cls, status))
    with pytest.raises(RebuttalError, match=message):
        r.live(**LIVE_ARGS)


def test_connection_error():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    r, _ = rebutter(error=anthropic.APIConnectionError(request=request))
    with pytest.raises(RebuttalError, match="연결"):
        r.report(**REPORT_ARGS)


def test_severity_is_clamped():
    assert RebuttalCard.model_validate(make_card(severity=9)).severity == 5
    assert RebuttalCard.model_validate(make_card(severity=0)).severity == 1


def test_fake_rebutter():
    fake = FakeRebutter()
    assert fake.live(**LIVE_ARGS).card.decision.endswith("출시합시다")
    report = fake.report(**REPORT_ARGS)
    assert len(report.cards) == 1


def test_prompts_intensity_and_context():
    assert "순한맛" in prompts.system_prompt("mild", "")
    assert "company_context" not in prompts.system_prompt("mild", "  ")
    assert "자금 6개월" in prompts.system_prompt("medium", "자금 6개월")


def test_live_prompt_lists_previous_and_forced():
    text = prompts.live_user_prompt("기록", ["새 발언"], ["이전 결정"], "manual", forced=True)
    assert "이전 결정" in text and "새 발언" in text
    assert "'대표 발언'으로 표시한" in text
    assert "지금 반박" in text


def test_report_prompt_without_speaker():
    assert "지정되지 않았습니다" in prompts.report_user_prompt("기록", None)
