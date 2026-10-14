from datetime import datetime

from devils_advocate import __main__ as cli
from devils_advocate.config import Settings
from devils_advocate.report import card_markdown, report_markdown, session_markdown, severity_bar
from devils_advocate.schema import MeetingReport


def test_severity_bar():
    assert severity_bar(4) == "●●●●○"


def test_card_markdown(card):
    md = card_markdown(card, title="1. 출시")
    assert md.startswith("### 1. 출시")
    assert "- [근거 부족] 문의 두 건은 수요 근거로 약하다." in md
    assert "**지금 던질 질문:** 유료로" in md


def test_report_markdown(card):
    report = MeetingReport(meeting_summary="요약", cards=[card], overall_assessment="총평")
    md = report_markdown(report, source_name="회의.txt", intensity="spicy", generated_at=datetime(2026, 1, 5, 9, 0))
    assert "- 반박 강도: 매운맛" in md
    assert "- 작성 시각: 2026-01-05 09:00" in md
    assert "## 반론 (1건)" in md


def test_report_markdown_without_cards():
    report = MeetingReport(meeting_summary="요약", cards=[], overall_assessment="총평")
    assert "반론할 결정이 없었습니다." in report_markdown(report, source_name=None, intensity="mild")


def test_session_markdown_empty():
    md = session_markdown([], [], "medium")
    assert "반론이 없었습니다." in md and "(없음)" in md


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("DA_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("DA_MIN_INTERVAL", "45")
    monkeypatch.setenv("DA_PAUSE_SECONDS", "잘못된값")
    monkeypatch.setenv("DA_FAKE_LLM", "1")
    s = Settings.from_env()
    assert (s.model, s.min_interval, s.pause_seconds, s.fake_llm) == ("claude-sonnet-5-5", 45.0, 2.5, True)


def test_settings_defaults(monkeypatch):
    for name in ("DA_MODEL", "DA_MIN_INTERVAL", "DA_FAKE_LLM", "DA_LIVE_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env()
    assert (s.model, s.min_interval, s.live_effort, s.fake_llm) == ("claude-opus-5-5", 30.0, "medium", False)


def test_cli_analyze_fake(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DA_FAKE_LLM", "1")
    path = tmp_path / "회의.txt"
    path.write_text("대표: 출시합시다\n", encoding="utf-8")
    out = tmp_path / "report.md"
    assert cli.main(["analyze", str(path), "--ceo", "대표", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# 😈")


def test_cli_reads_cp949(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DA_FAKE_LLM", "1")
    path = tmp_path / "회의.txt"
    path.write_bytes("대표: 출시합시다\n".encode("cp949"))
    assert cli.main(["analyze", str(path)]) == 0
    assert "출시합시다" in capsys.readouterr().out


def test_cli_without_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    for name in ("DA_FAKE_LLM", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    assert cli.main(["analyze", str(path)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_cli_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DA_FAKE_LLM", "1")
    assert cli.main(["analyze", str(tmp_path / "없음.txt")]) == 2
