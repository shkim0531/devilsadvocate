import pytest
from fastapi.testclient import TestClient

from devils_advocate.config import Settings
from devils_advocate.llm import FakeRebutter, RebuttalError
from devils_advocate.schema import LiveResult
from devils_advocate.server import create_app

SAMPLE_TXT = "대표: 3월에 출시합시다\n팀장: 일정이 빠듯합니다\n"


class RecordingRebutter(FakeRebutter):
    def __init__(self, skip=False, error=None):
        self.calls = []
        self.skip = skip
        self.error = error

    def live(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if self.skip:
            return LiveResult(should_rebut=False, skip_reason="잡담")
        return super().live(**kwargs)

    def report(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return super().report(**kwargs)


def make_client(rebutter=None, **settings):
    settings.setdefault("pause_seconds", 0)
    return TestClient(create_app(Settings(**settings), rebutter=rebutter))


@pytest.fixture
def rebutter():
    return RecordingRebutter()


@pytest.fixture
def client(rebutter):
    return make_client(rebutter)


def new_session(client, **body):
    return client.post("/api/sessions", json=body).json()["id"]


def test_index_and_static(client):
    assert "악마의 변호인" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_status(client):
    data = client.get("/api/status").json()
    assert data["model"] == "claude-opus-5-5"
    assert data["ready"] is True


def test_live_flow_tick_rebuts_then_cools_down(client, rebutter):
    sid = new_session(client, intensity="mild", company_context="직원 12명")
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "3월에 출시합시다", "is_ceo": False})
    res = client.post(f"/api/sessions/{sid}/tick").json()
    assert res["status"] == "rebutted"
    assert res["card"]["severity"] == 3
    assert rebutter.calls[0]["intensity"] == "mild"
    assert rebutter.calls[0]["company_context"] == "직원 12명"
    assert rebutter.calls[0]["forced"] is False

    client.post(f"/api/sessions/{sid}/utterances", json={"text": "채용도 진행합시다"})
    res = client.post(f"/api/sessions/{sid}/tick").json()
    assert res["status"] == "waiting" and res["cooldown"] > 0
    assert len(rebutter.calls) == 1


def test_tick_without_utterances_waits(client):
    sid = new_session(client)
    assert client.post(f"/api/sessions/{sid}/tick").json()["status"] == "waiting"


def test_rebut_now_ignores_cooldown(client, rebutter):
    sid = new_session(client)
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "출시합시다"})
    client.post(f"/api/sessions/{sid}/tick")
    res = client.post(f"/api/sessions/{sid}/rebut-now").json()
    assert res["status"] == "rebutted" and res["forced"] is True
    assert rebutter.calls[1]["forced"] is True
    assert rebutter.calls[1]["previous_decisions"]  # 앞선 반론을 알려 준다


def test_rebut_now_without_utterances(client):
    sid = new_session(client)
    assert client.post(f"/api/sessions/{sid}/rebut-now").status_code == 400


def test_skip_result():
    client = make_client(RecordingRebutter(skip=True))
    sid = new_session(client)
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "출시합시다"})
    res = client.post(f"/api/sessions/{sid}/tick").json()
    assert res == {"status": "skipped", "reason": "잡담", "card": None}


def test_error_is_reported_and_targets_kept():
    rebutter = RecordingRebutter(error=RebuttalError("요청 한도를 넘었습니다."))
    client = make_client(rebutter, min_interval=0)
    sid = new_session(client)
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "출시합시다"})
    res = client.post(f"/api/sessions/{sid}/tick")
    assert res.status_code == 502 and "한도" in res.json()["detail"]
    rebutter.error = None
    assert client.post(f"/api/sessions/{sid}/tick").json()["status"] == "rebutted"
    assert rebutter.calls[-1]["targets"] == ["출시합시다"]


def test_settings_update_switches_to_manual(client, rebutter):
    sid = new_session(client)
    res = client.put(f"/api/sessions/{sid}/settings", json={"intensity": "medium", "target_mode": "manual"})
    assert res.status_code == 200
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "출시합시다", "is_ceo": False})
    assert client.post(f"/api/sessions/{sid}/tick").json()["status"] == "waiting"
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "가격도 낮춥니다", "is_ceo": True})
    assert client.post(f"/api/sessions/{sid}/tick").json()["status"] == "rebutted"
    assert rebutter.calls[0]["targets"] == ["가격도 낮춥니다"]
    assert rebutter.calls[0]["intensity"] == "medium"


def test_invalid_settings_rejected(client):
    assert client.post("/api/sessions", json={"intensity": "hot"}).status_code == 422


def test_unknown_session(client):
    assert client.post("/api/sessions/nope/tick").status_code == 404


def test_export_markdown(client):
    sid = new_session(client)
    client.post(f"/api/sessions/{sid}/utterances", json={"text": "출시합시다", "is_ceo": True})
    client.post(f"/api/sessions/{sid}/rebut-now")
    md = client.get(f"/api/sessions/{sid}/export").text
    assert "## 반론 (1건)" in md and "**대표:** 출시합시다" in md


def test_sample_and_parse(client):
    sample = client.get("/api/sample").text
    res = client.post("/api/parse", json={"content": sample, "filename": "sample_meeting.txt"}).json()
    assert "대표" in res["speakers"]


def test_parse_empty(client):
    assert client.post("/api/parse", json={"content": " "}).status_code == 400


def test_analyze(client, rebutter):
    res = client.post(
        "/api/analyze",
        json={"content": SAMPLE_TXT, "filename": "a.txt", "ceo_speaker": "대표", "intensity": "medium"},
    )
    data = res.json()
    assert res.status_code == 200
    assert data["utterance_count"] == 2
    assert data["markdown"].startswith("# 😈 악마의 변호인 반론 리포트")
    assert rebutter.calls[0]["ceo_speaker"] == "대표"
    assert rebutter.calls[0]["transcript"] == "대표: 3월에 출시합시다\n팀장: 일정이 빠듯합니다"


def test_analyze_blank_speaker_means_auto(client, rebutter):
    client.post("/api/analyze", json={"content": SAMPLE_TXT, "ceo_speaker": "  "})
    assert rebutter.calls[0]["ceo_speaker"] is None


def test_analyze_error():
    client = make_client(RecordingRebutter(error=RebuttalError("거절했습니다")))
    res = client.post("/api/analyze", json={"content": SAMPLE_TXT})
    assert res.status_code == 502 and "거절" in res.json()["detail"]


def test_without_api_key_returns_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = make_client()
    assert client.get("/api/status").json()["ready"] is False
    res = client.post("/api/analyze", json={"content": SAMPLE_TXT})
    assert res.status_code == 503 and "API 키" in res.json()["detail"]


def test_fake_mode_from_settings(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = make_client(fake_llm=True)
    res = client.post("/api/analyze", json={"content": SAMPLE_TXT})
    assert res.status_code == 200
    assert "[가짜 응답]" in res.json()["report"]["meeting_summary"]
