"""웹 화면과 API를 제공하는 서버."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import report as report_md
from .config import Settings, has_api_credentials
from .llm import ClaudeRebutter, FakeRebutter, Rebutter, RebuttalError
from .schema import Intensity, TargetMode
from .session import MeetingSession, SessionStore
from .transcript import TranscriptError, format_transcript, parse_transcript, speakers

PACKAGE_DIR = Path(__file__).parent
STATIC_DIR = PACKAGE_DIR / "static"
SAMPLE_FILE = "sample_meeting.txt"

# 회의록 텍스트 크기 상한(문자 수). 몇 시간짜리 회의록도 충분히 들어간다.
MAX_TRANSCRIPT_CHARS = 400_000


class SessionSettings(BaseModel):
    intensity: Intensity = "spicy"
    target_mode: TargetMode = "auto"
    company_context: str = Field(default="", max_length=4000)


class UtteranceIn(BaseModel):
    text: str = Field(max_length=2000)
    is_ceo: bool = False


class AnalyzeIn(BaseModel):
    content: str = Field(max_length=MAX_TRANSCRIPT_CHARS)
    filename: str | None = None
    ceo_speaker: str | None = None
    intensity: Intensity = "spicy"
    company_context: str = Field(default="", max_length=4000)


class ParseIn(BaseModel):
    content: str = Field(max_length=MAX_TRANSCRIPT_CHARS)
    filename: str | None = None


def create_app(settings: Settings | None = None, rebutter: Rebutter | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = SessionStore()
    app = FastAPI(title="악마의 변호인 회의 에이전트")
    state: dict[str, Rebutter | None] = {"rebutter": rebutter}

    def get_rebutter() -> Rebutter:
        if state["rebutter"] is None:
            if settings.fake_llm:
                state["rebutter"] = FakeRebutter()
            elif has_api_credentials():
                state["rebutter"] = ClaudeRebutter(settings)
            else:
                raise HTTPException(
                    503, "API 키가 없습니다. .env 파일에 ANTHROPIC_API_KEY를 넣고 서버를 다시 시작하세요."
                )
        return state["rebutter"]

    def get_session(session_id: str) -> MeetingSession:
        session = store.get(session_id)
        if session is None:
            raise HTTPException(404, "회의 세션을 찾지 못했습니다. 화면을 새로고침하세요.")
        return session

    def run_live(session: MeetingSession, forced: bool) -> dict:
        rebutter_ = get_rebutter()
        with session.lock:
            if session.in_flight:
                return {"status": "busy", "card": None}
            targets, consumed_until = session.begin_call()
            transcript = session.recent_transcript()
            previous = session.previous_decisions()
        try:
            result = rebutter_.live(
                transcript=transcript,
                targets=targets,
                previous_decisions=previous,
                intensity=session.intensity,
                target_mode=session.target_mode,
                company_context=session.company_context,
                forced=forced,
            )
        except RebuttalError as exc:
            with session.lock:
                session.abort_call()
            raise HTTPException(502, str(exc)) from exc
        except Exception:
            with session.lock:
                session.abort_call()
            raise
        with session.lock:
            issued = session.finish_call(consumed_until, result.card if result.should_rebut else None, forced)
        if issued is None:
            return {"status": "skipped", "reason": result.skip_reason, "card": None}
        return {"status": "rebutted", "card": issued.card.model_dump(), "forced": forced}

    @app.get("/api/status")
    def status() -> dict:
        return {
            "model": settings.model,
            "fake": settings.fake_llm,
            "ready": settings.fake_llm or has_api_credentials() or state["rebutter"] is not None,
            "min_interval": settings.min_interval,
        }

    @app.post("/api/sessions")
    def create_session(body: SessionSettings) -> dict:
        session = store.add(
            MeetingSession(
                min_interval=settings.min_interval,
                pause_seconds=settings.pause_seconds,
                intensity=body.intensity,
                target_mode=body.target_mode,
                company_context=body.company_context,
            )
        )
        return {"id": session.id}

    @app.put("/api/sessions/{session_id}/settings")
    def update_settings(session_id: str, body: SessionSettings) -> dict:
        session = get_session(session_id)
        with session.lock:
            session.intensity = body.intensity
            session.target_mode = body.target_mode
            session.company_context = body.company_context
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/utterances")
    def add_utterance(session_id: str, body: UtteranceIn) -> dict:
        session = get_session(session_id)
        with session.lock:
            session.add_utterance(body.text, body.is_ceo)
            count = len(session.utterances)
        return {"count": count}

    @app.post("/api/sessions/{session_id}/tick")
    def tick(session_id: str) -> dict:
        """브라우저가 주기적으로 부른다. 끼어들 때라고 판단되면 반론을 만들어 돌려준다."""
        session = get_session(session_id)
        with session.lock:
            ready = session.should_trigger()
            wait = session.seconds_until_ready()
        if not ready:
            return {"status": "waiting", "card": None, "cooldown": round(wait, 1)}
        return run_live(session, forced=False)

    @app.post("/api/sessions/{session_id}/rebut-now")
    def rebut_now(session_id: str) -> dict:
        session = get_session(session_id)
        with session.lock:
            empty = not session.utterances
        if empty:
            raise HTTPException(400, "아직 기록된 발언이 없습니다.")
        return run_live(session, forced=True)

    @app.get("/api/sessions/{session_id}/export", response_class=PlainTextResponse)
    def export_session(session_id: str) -> str:
        session = get_session(session_id)
        with session.lock:
            transcript = [(u.text, u.is_ceo) for u in session.utterances]
            cards = [c.card for c in session.cards]
            intensity = session.intensity
        return report_md.session_markdown(transcript, cards, intensity)

    @app.get("/api/sample", response_class=PlainTextResponse)
    def sample() -> str:
        return resources.files("devils_advocate.samples").joinpath(SAMPLE_FILE).read_text(encoding="utf-8")

    @app.post("/api/parse")
    def parse(body: ParseIn) -> dict:
        try:
            utterances = parse_transcript(body.content, body.filename)
        except TranscriptError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"count": len(utterances), "speakers": speakers(utterances)}

    @app.post("/api/analyze")
    def analyze(body: AnalyzeIn) -> dict:
        try:
            utterances = parse_transcript(body.content, body.filename)
        except TranscriptError as exc:
            raise HTTPException(400, str(exc)) from exc
        ceo = (body.ceo_speaker or "").strip() or None
        try:
            result = get_rebutter().report(
                transcript=format_transcript(utterances),
                ceo_speaker=ceo,
                intensity=body.intensity,
                company_context=body.company_context,
            )
        except RebuttalError as exc:
            raise HTTPException(502, str(exc)) from exc
        markdown = report_md.report_markdown(result, source_name=body.filename, intensity=body.intensity)
        return {"report": result.model_dump(), "markdown": markdown, "utterance_count": len(utterances)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
