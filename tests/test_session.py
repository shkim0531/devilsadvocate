from devils_advocate.session import FORCE_PENDING, MeetingSession


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_session(**kwargs):
    clock = Clock()
    session = MeetingSession(min_interval=30, pause_seconds=2.5, clock=clock, **kwargs)
    return session, clock


def test_waits_for_pause():
    s, clock = make_session()
    s.add_utterance("신제품을 3월에 출시하겠습니다", False)
    assert not s.should_trigger()
    clock.now += 3
    assert s.should_trigger()


def test_auto_mode_needs_decision_cue():
    s, clock = make_session()
    s.add_utterance("안녕하세요 다들 오셨네요", False)
    clock.now += 5
    assert not s.should_trigger()
    s.add_utterance("그럼 이번 달 안에 채용 공고 내 주세요", False)
    clock.now += 5
    assert s.should_trigger()


def test_manual_mode_only_ceo_marked():
    s, clock = make_session(target_mode="manual")
    s.add_utterance("출시합시다", False)
    clock.now += 5
    assert not s.should_trigger()
    s.add_utterance("가격은 30퍼센트 낮게 갑니다", True)
    clock.now += 5
    assert s.should_trigger()
    assert s.pending_targets() == ["가격은 30퍼센트 낮게 갑니다"]


def test_manual_mode_does_not_require_cue():
    s, clock = make_session(target_mode="manual")
    s.add_utterance("시장은 지금 뜨겁습니다", True)
    clock.now += 5
    assert s.should_trigger()


def test_min_interval_between_calls(card):
    s, clock = make_session()
    s.add_utterance("출시하겠습니다", False)
    clock.now += 3
    targets, until = s.begin_call()
    assert targets == ["출시하겠습니다"]
    s.finish_call(until, card, forced=False)
    s.add_utterance("채용도 진행합시다", False)
    clock.now += 5
    assert not s.should_trigger()
    assert 0 < s.seconds_until_ready() <= 30
    clock.now += 30
    assert s.should_trigger()
    assert s.pending_targets() == ["채용도 진행합시다"]


def test_no_trigger_while_in_flight():
    s, clock = make_session()
    s.add_utterance("출시하겠습니다", False)
    clock.now += 3
    s.begin_call()
    assert not s.should_trigger()


def test_utterances_during_call_stay_pending(card):
    s, clock = make_session()
    s.add_utterance("출시하겠습니다", False)
    clock.now += 3
    _, until = s.begin_call()
    s.add_utterance("투자도 받겠습니다", False)  # 요청 중에 들어온 발언
    s.finish_call(until, None, forced=False)
    assert s.pending_targets() == ["투자도 받겠습니다"]


def test_abort_keeps_targets():
    s, clock = make_session()
    s.add_utterance("출시하겠습니다", False)
    clock.now += 3
    s.begin_call()
    s.abort_call()
    assert not s.in_flight
    assert s.pending_targets() == ["출시하겠습니다"]


def test_force_when_many_pending_without_pause():
    s, clock = make_session()
    for i in range(FORCE_PENDING):
        s.add_utterance(f"{i}번 안건 진행합시다", False)
    assert s.should_trigger()


def test_empty_utterance_ignored():
    s, _ = make_session()
    s.add_utterance("   ", True)
    assert s.utterances == []


def test_transcript_and_previous(card):
    s, clock = make_session()
    s.add_utterance("출시합시다", True)
    s.add_utterance("일정이 빠듯합니다", False)
    clock.now += 3
    _, until = s.begin_call()
    s.finish_call(until, card, forced=True)
    assert s.recent_transcript() == "대표: 출시합시다\n발언: 일정이 빠듯합니다"
    assert s.previous_decisions() == [card.decision]
    assert s.cards[0].forced
