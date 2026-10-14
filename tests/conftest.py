import json
from types import SimpleNamespace

import pytest

from devils_advocate.schema import RebuttalCard


def make_card(**overrides) -> dict:
    card = {
        "decision": "3월까지 신제품 출시",
        "steelman": "시장 선점이 늦으면 기회가 사라진다.",
        "weakest_assumption": "수요가 확실하다는 전제",
        "counterpoints": [{"category": "근거 부족", "point": "문의 두 건은 수요 근거로 약하다."}],
        "question_now": "유료로 쓰겠다고 확인한 고객이 몇 곳인가요?",
        "alternatives": ["파일럿 고객 3곳으로 먼저 검증"],
        "concede_if": "선계약 고객이 확인되면",
        "severity": 4,
    }
    card.update(overrides)
    return card


def text_response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.response


class FakeClient:
    """anthropic.Anthropic 대신 쓰는 가짜. 보낸 요청을 기록하고 정해 둔 응답을 돌려준다."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.requests.append(kwargs)
                if outer.error:
                    raise outer.error
                return outer.response

            def stream(self, **kwargs):
                outer.requests.append(kwargs)
                if outer.error:
                    raise outer.error
                return FakeStream(outer.response)

        self.beta = SimpleNamespace(messages=_Messages())


@pytest.fixture
def card_dict():
    return make_card()


@pytest.fixture
def card(card_dict):
    return RebuttalCard.model_validate(card_dict)
