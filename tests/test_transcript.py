import pytest

from devils_advocate.transcript import TranscriptError, format_transcript, parse_transcript, speakers

CLOVA = """회의 제목
2026.10.12 월 오전 10:00 ・ 5분
대표 개발팀장

대표 00:05
3월까지 출시하겠습니다.
인력을 전부 투입합시다.

개발팀장 01:10
일정이 빠듯합니다.
"""


def test_clova_note_txt():
    utts = parse_transcript(CLOVA, "회의.txt")
    assert [(u.speaker, u.timestamp) for u in utts] == [("대표", "00:05"), ("개발팀장", "01:10")]
    assert utts[0].text == "3월까지 출시하겠습니다. 인력을 전부 투입합시다."


def test_clova_skips_header_lines():
    utts = parse_transcript(CLOVA)
    assert all("회의 제목" not in u.text for u in utts)


def test_teams_vtt_voice_tags_and_merge():
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<v 김대표>신규 채용을 진행합니다.</v>

2
00:00:03.500 --> 00:00:05.000
<v 김대표>이번 달 안에요.</v>

3
00:01:05.000 --> 00:01:07.000
<v 박팀장>예산은요?</v>
"""
    utts = parse_transcript(vtt, "meeting.vtt")
    assert [u.speaker for u in utts] == ["김대표", "박팀장"]
    assert utts[0].text == "신규 채용을 진행합니다. 이번 달 안에요."
    assert utts[0].timestamp == "00:01"
    assert utts[1].timestamp == "01:05"


def test_zoom_vtt_named_lines():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\n대표: 출시합시다\n"
    utts = parse_transcript(vtt)
    assert utts[0].speaker == "대표"
    assert utts[0].text == "출시합시다"


def test_srt():
    srt = "1\n00:00:01,000 --> 00:00:02,000\n가격을 낮추겠습니다\n\n2\n00:00:03,000 --> 00:00:04,000\n두 번째 줄\n"
    utts = parse_transcript(srt, "a.srt")
    # 화자가 없으면 합치지 않는다.
    assert [u.text for u in utts] == ["가격을 낮추겠습니다", "두 번째 줄"]
    assert utts[0].timestamp == "00:01"


def test_srt_detected_without_extension():
    srt = "1\n00:00:01,000 --> 00:00:02,000\n안녕하세요\n"
    assert parse_transcript(srt)[0].text == "안녕하세요"


def test_plain_text_with_and_without_speakers():
    utts = parse_transcript("대표: 진행합시다\n그냥 메모 한 줄\n", "notes.txt")
    assert (utts[0].speaker, utts[0].text) == ("대표", "진행합시다")
    assert (utts[1].speaker, utts[1].text) == (None, "그냥 메모 한 줄")


def test_plain_text_time_is_not_a_speaker():
    utts = parse_transcript("12:30에 다시 모입시다")
    assert utts[0].speaker is None


def test_crlf_and_bom():
    utts = parse_transcript("﻿대표: 하나\r\n팀장: 둘\r\n")
    assert [u.speaker for u in utts] == ["대표", "팀장"]


def test_empty_raises():
    with pytest.raises(TranscriptError):
        parse_transcript("   \n ")


def test_vtt_without_cues_raises():
    with pytest.raises(TranscriptError):
        parse_transcript("WEBVTT\n\nNOTE 빈 파일\n", "x.vtt")


def test_speakers_and_format():
    utts = parse_transcript(CLOVA)
    assert speakers(utts) == ["대표", "개발팀장"]
    assert format_transcript(utts).split("\n")[1] == "[01:10] 개발팀장: 일정이 빠듯합니다."


def test_sample_file_parses():
    from importlib import resources

    text = resources.files("devils_advocate.samples").joinpath("sample_meeting.txt").read_text(encoding="utf-8")
    utts = parse_transcript(text, "sample_meeting.txt")
    assert "대표" in speakers(utts)
    assert len(utts) >= 8
