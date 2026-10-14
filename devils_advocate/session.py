"""실시간 회의 한 건의 상태와, 반론을 끼워 넣을 시점을 판단하는 규칙."""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .schema import RebuttalCard

# 자동 모드에서 결정·지시성 발언을 미리 걸러 내는 단서. 최종 판단은 Claude가 한다.
DECISION_CUES = re.compile(
    r"결정|확정|진행하|추진|하겠습니다|하겠어요|할게요|할 겁니다|할 거예요|합시다|하자|갑시다|가자|가죠|"
    r"하죠|해주세요|해 주세요|(?<!안녕)하세요|하도록|하기로|해야|합니다\s*$|도입|채용|투자|출시|중단|철수|"
    r"늘리|줄이|바꾸|바꿉|목표|예산|계약|맡기|맡겨|정하"
)

# 반론 요청에 넣을 최근 발언 수. 실시간 응답 속도와 비용을 위해 회의 전체를 보내지 않는다.
CONTEXT_WINDOW = 40
# 말이 멈추지 않아도 대상 발언이 이만큼 쌓이면 반론한다.
FORCE_PENDING = 5
# 한 번에 반론 대상으로 넘기는 새 발언의 최대 수(가장 최근 것부터).
MAX_TARGETS = 15


@dataclass
class LiveUtterance:
    text: str
    is_ceo: bool
    at: float


@dataclass
class IssuedCard:
    card: RebuttalCard
    at: float
    forced: bool


@dataclass
class MeetingSession:
    min_interval: float
    pause_seconds: float
    intensity: str = "spicy"
    target_mode: str = "auto"
    company_context: str = ""
    clock: Callable[[], float] = time.monotonic
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    utterances: list[LiveUtterance] = field(default_factory=list)
    cards: list[IssuedCard] = field(default_factory=list)
    last_call_at: float | None = None
    _pending_from: int = 0  # 아직 반론 판단에 넘기지 않은 첫 발언의 위치
    in_flight: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_utterance(self, text: str, is_ceo: bool) -> None:
        text = text.strip()
        if text:
            self.utterances.append(LiveUtterance(text=text, is_ceo=is_ceo, at=self.clock()))

    def pending_targets(self) -> list[str]:
        pending = self.utterances[self._pending_from :]
        if self.target_mode == "manual":
            pending = [u for u in pending if u.is_ceo]
        return [u.text for u in pending[-MAX_TARGETS:]]

    def should_trigger(self) -> bool:
        """한두 문장이 쌓이고 말이 멈췄으며, 마지막 반론 요청 뒤 최소 간격이 지났으면 True."""
        if self.in_flight:
            return False
        targets = self.pending_targets()
        if not targets:
            return False
        if self.target_mode == "auto" and not any(DECISION_CUES.search(t) for t in targets):
            return False
        now = self.clock()
        if self.last_call_at is not None and now - self.last_call_at < self.min_interval:
            return False
        if len(targets) >= FORCE_PENDING:
            return True
        return now - self.utterances[-1].at >= self.pause_seconds

    def seconds_until_ready(self) -> float:
        if self.last_call_at is None:
            return 0.0
        return max(0.0, self.min_interval - (self.clock() - self.last_call_at))

    def begin_call(self) -> tuple[list[str], int]:
        """반론 요청 직전 호출. 대상 발언과, 요청이 끝난 뒤 넘길 위치를 돌려준다."""
        self.in_flight = True
        self.last_call_at = self.clock()
        return self.pending_targets(), len(self.utterances)

    def finish_call(self, consumed_until: int, card: RebuttalCard | None, forced: bool) -> IssuedCard | None:
        self.in_flight = False
        self._pending_from = max(self._pending_from, consumed_until)
        if card is None:
            return None
        issued = IssuedCard(card=card, at=self.clock(), forced=forced)
        self.cards.append(issued)
        return issued

    def abort_call(self) -> None:
        """요청이 실패하면 대상 발언은 남겨 두고 다음 기회에 다시 시도한다."""
        self.in_flight = False

    def recent_transcript(self) -> str:
        lines = []
        for u in self.utterances[-CONTEXT_WINDOW:]:
            lines.append(f"{'대표' if u.is_ceo else '발언'}: {u.text}")
        return "\n".join(lines)

    def previous_decisions(self) -> list[str]:
        return [c.card.decision for c in self.cards]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, MeetingSession] = {}
        self._lock = threading.Lock()

    def add(self, session: MeetingSession) -> MeetingSession:
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> MeetingSession | None:
        with self._lock:
            return self._sessions.get(session_id)
