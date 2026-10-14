"""회의록 파일(.txt, .vtt, .srt)을 발언 목록으로 바꾼다.

지원 형식
- 클로바노트 내보내기 txt: "참석자 1 00:15" 줄 다음에 발언 내용
- 일반 txt: "이름: 발언" 줄, 또는 화자 없는 줄
- WebVTT(Zoom·Teams): "<v 이름>발언</v>" 또는 "이름: 발언"
- SRT: 번호, 시간, 내용 블록
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath


@dataclass
class Utterance:
    text: str
    speaker: str | None = None
    timestamp: str | None = None  # "mm:ss" 또는 "hh:mm:ss"


_TIME = r"\d{1,2}:\d{2}(?::\d{2})?"
_CLOVA_HEADER = re.compile(rf"^(?P<speaker>.+?)\s+(?P<ts>{_TIME})\s*$")
_CUE_TIMING = re.compile(
    r"^(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}"
)
_VOICE_TAG = re.compile(r"<v(?:\.[^\s>]+)*\s+([^>]+)>")
_TAG = re.compile(r"</?[^>]+>")
# "이름: 발언" — 이름은 짧아야 하고 시간(12:30)이나 URL은 화자로 보지 않는다.
_NAMED_LINE = re.compile(r"^(?P<speaker>[^:：\d][^:：]{0,24})\s*[:：]\s*(?P<text>.+)$")


class TranscriptError(ValueError):
    pass


def parse_transcript(content: str, filename: str | None = None) -> list[Utterance]:
    """파일 내용과 이름(확장자)으로 형식을 판단해 발언 목록을 돌려준다."""
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if not content.strip():
        raise TranscriptError("회의록 내용이 비어 있습니다.")

    suffix = PurePath(filename).suffix.lower() if filename else ""
    first_line = content.strip().split("\n", 1)[0].strip()

    if suffix == ".vtt" or first_line.startswith("WEBVTT"):
        utterances = _parse_cues(content)
    elif suffix == ".srt" or _looks_like_srt(content):
        utterances = _parse_cues(content)
    elif _looks_like_clova(content):
        utterances = _parse_clova(content)
    else:
        utterances = _parse_plain(content)

    utterances = _merge_consecutive(utterances)
    if not utterances:
        raise TranscriptError("회의록에서 발언을 찾지 못했습니다.")
    return utterances


def _looks_like_srt(content: str) -> bool:
    lines = [line.strip() for line in content.strip().split("\n")[:3]]
    return len(lines) >= 2 and lines[0].isdigit() and bool(_CUE_TIMING.match(lines[1]))


def _looks_like_clova(content: str) -> bool:
    headers = sum(1 for line in content.split("\n") if _CLOVA_HEADER.match(line.strip()))
    return headers >= 2


def _parse_clova(content: str) -> list[Utterance]:
    utterances: list[Utterance] = []
    current: Utterance | None = None
    for raw in content.split("\n"):
        line = raw.strip()
        header = _CLOVA_HEADER.match(line)
        if header:
            if current and current.text:
                utterances.append(current)
            current = Utterance(text="", speaker=header["speaker"].strip(), timestamp=header["ts"])
            continue
        if current is None:
            # 첫 화자 줄 앞은 제목·날짜·참석자 목록이므로 건너뛴다.
            continue
        if line:
            current.text = f"{current.text} {line}".strip()
        elif current.text:
            utterances.append(current)
            current = None
    if current and current.text:
        utterances.append(current)
    return utterances


def _parse_cues(content: str) -> list[Utterance]:
    utterances: list[Utterance] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if _CUE_TIMING.match(line)), None)
        if timing_index is None:
            continue  # WEBVTT 헤더, NOTE, STYLE 블록
        timestamp = _short_time(_CUE_TIMING.match(lines[timing_index])["start"])
        text_lines = lines[timing_index + 1 :]
        if not text_lines:
            continue
        joined = " ".join(text_lines)
        speaker = None
        voice = _VOICE_TAG.search(joined)
        if voice:
            speaker = voice.group(1).strip()
        text = _TAG.sub("", joined).strip()
        if speaker is None:
            named = _NAMED_LINE.match(text)
            if named:
                speaker, text = named["speaker"].strip(), named["text"].strip()
        if text:
            utterances.append(Utterance(text=text, speaker=speaker, timestamp=timestamp))
    return utterances


def _parse_plain(content: str) -> list[Utterance]:
    utterances: list[Utterance] = []
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue
        named = _NAMED_LINE.match(line)
        if named:
            utterances.append(Utterance(text=named["text"].strip(), speaker=named["speaker"].strip()))
        else:
            utterances.append(Utterance(text=line))
    return utterances


def _short_time(value: str) -> str:
    """"00:01:05.120" → "01:05", "01:02:03,000" → "01:02:03"."""
    value = re.split(r"[.,]", value)[0]
    parts = value.split(":")
    if len(parts) == 3 and parts[0] in {"0", "00"}:
        parts = parts[1:]
    return ":".join(parts)


def _merge_consecutive(utterances: list[Utterance]) -> list[Utterance]:
    """자막 형식은 한 사람의 말이 여러 조각으로 나뉘므로 같은 화자의 연속 발언을 합친다."""
    merged: list[Utterance] = []
    for utt in utterances:
        if merged and utt.speaker is not None and merged[-1].speaker == utt.speaker:
            merged[-1].text = f"{merged[-1].text} {utt.text}"
        else:
            merged.append(Utterance(text=utt.text, speaker=utt.speaker, timestamp=utt.timestamp))
    return merged


def speakers(utterances: list[Utterance]) -> list[str]:
    seen: dict[str, None] = {}
    for utt in utterances:
        if utt.speaker:
            seen.setdefault(utt.speaker, None)
    return list(seen)


def format_transcript(utterances: list[Utterance]) -> str:
    """프롬프트와 리포트에 넣을 한 줄 한 발언 형식."""
    lines = []
    for utt in utterances:
        prefix = f"[{utt.timestamp}] " if utt.timestamp else ""
        who = f"{utt.speaker}: " if utt.speaker else ""
        lines.append(f"{prefix}{who}{utt.text}")
    return "\n".join(lines)
