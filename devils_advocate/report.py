"""반론 카드·리포트를 마크다운으로 바꾼다(저장·공유용)."""

from __future__ import annotations

from datetime import datetime

from .schema import INTENSITY_LABELS, MeetingReport, RebuttalCard


def severity_bar(severity: int) -> str:
    return "●" * severity + "○" * (5 - severity)


def card_markdown(card: RebuttalCard, title: str | None = None) -> str:
    lines = [f"### {title or card.decision}", ""]
    if title:
        lines += [f"**대상 결정:** {card.decision}", ""]
    lines += [
        f"**심각도:** {severity_bar(card.severity)} ({card.severity}/5)",
        "",
        f"**대표 논리의 최강 버전:** {card.steelman}",
        "",
        f"**가장 약한 가정:** {card.weakest_assumption}",
        "",
        "**반론 포인트**",
        "",
    ]
    lines += [f"- [{cp.category}] {cp.point}" for cp in card.counterpoints] or ["- (없음)"]
    lines += ["", f"**지금 던질 질문:** {card.question_now}", "", "**대안**", ""]
    lines += [f"- {alt}" for alt in card.alternatives] or ["- (없음)"]
    lines += ["", f"**이게 확인되면 인정:** {card.concede_if}", ""]
    return "\n".join(lines)


def report_markdown(
    report: MeetingReport,
    *,
    source_name: str | None,
    intensity: str,
    generated_at: datetime | None = None,
) -> str:
    when = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 😈 악마의 변호인 반론 리포트",
        "",
        f"- 회의록: {source_name or '(직접 입력)'}",
        f"- 반박 강도: {INTENSITY_LABELS.get(intensity, intensity)}",
        f"- 작성 시각: {when}",
        "",
        "## 회의 요약",
        "",
        report.meeting_summary,
        "",
        f"## 반론 ({len(report.cards)}건)",
        "",
    ]
    if not report.cards:
        lines += ["반론할 결정이 없었습니다.", ""]
    for i, card in enumerate(report.cards, start=1):
        lines.append(card_markdown(card, title=f"{i}. {card.decision}"))
    lines += ["## 총평", "", report.overall_assessment, ""]
    lines += ["---", "", "_반론은 판단 재료입니다. 최종 판단은 사람이 합니다._", ""]
    return "\n".join(lines)


def session_markdown(session_transcript: list[tuple[str, bool]], cards: list[RebuttalCard], intensity: str) -> str:
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 😈 실시간 회의 기록",
        "",
        f"- 저장 시각: {when}",
        f"- 반박 강도: {INTENSITY_LABELS.get(intensity, intensity)}",
        "",
        f"## 반론 ({len(cards)}건)",
        "",
    ]
    if not cards:
        lines += ["반론이 없었습니다.", ""]
    for i, card in enumerate(cards, start=1):
        lines.append(card_markdown(card, title=f"{i}. {card.decision}"))
    lines += ["## 발언 기록", ""]
    lines += [f"- {'**대표:** ' if is_ceo else ''}{text}" for text, is_ceo in session_transcript] or ["(없음)"]
    lines.append("")
    return "\n".join(lines)
