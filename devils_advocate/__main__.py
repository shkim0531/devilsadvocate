"""명령줄 진입점.

    python -m devils_advocate serve              # 웹 화면 실행 (http://localhost:8000)
    python -m devils_advocate analyze 회의록.txt  # 회의록 반론 리포트를 터미널에 출력
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devils_advocate", description="😈 악마의 변호인 회의 에이전트")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="웹 화면을 실행합니다")
    serve.add_argument("--host", default="127.0.0.1", help="기본값은 이 컴퓨터에서만 접속 가능한 127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    analyze = sub.add_parser("analyze", help="회의록 파일로 반론 리포트를 만듭니다")
    analyze.add_argument("file", type=Path, help="회의록 파일(.txt, .vtt, .srt)")
    analyze.add_argument("--ceo", default=None, help="대표 화자 이름(회의록에 적힌 그대로)")
    analyze.add_argument("--intensity", choices=["mild", "medium", "spicy"], default="spicy")
    analyze.add_argument("--context", default="", help="회사 맥락(직원 수, 자금 사정, 올해 목표 등)")
    analyze.add_argument("-o", "--output", type=Path, default=None, help="마크다운으로 저장할 경로")
    return parser


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"파일 인코딩을 읽지 못했습니다: {path}")


def run_serve(host: str, port: int) -> None:
    import uvicorn

    from .config import Settings, has_api_credentials
    from .server import create_app

    settings = Settings.from_env()
    if host not in LOCAL_HOSTS:
        print("⚠️  이 컴퓨터 밖에서도 접속할 수 있게 실행합니다. 인증 기능이 없으니 외부에 공개하지 마세요.")
    if settings.fake_llm:
        print("ℹ️  가짜 응답 모드(DA_FAKE_LLM)입니다. Claude를 호출하지 않습니다.")
    elif not has_api_credentials():
        print("⚠️  ANTHROPIC_API_KEY가 없습니다. .env 파일에 키를 넣어야 반론을 만들 수 있습니다.")
    shown = "localhost" if host in LOCAL_HOSTS else host
    print(f"😈 Chrome에서 http://{shown}:{port} 을 여세요. (모델: {settings.model})")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="warning")


def run_analyze(args: argparse.Namespace) -> int:
    from .config import Settings, has_api_credentials
    from .llm import ClaudeRebutter, FakeRebutter, RebuttalError
    from .report import report_markdown
    from .transcript import TranscriptError, format_transcript, parse_transcript

    settings = Settings.from_env()
    if not settings.fake_llm and not has_api_credentials():
        print("ANTHROPIC_API_KEY가 없습니다. .env 파일을 확인하세요.", file=sys.stderr)
        return 2
    try:
        utterances = parse_transcript(_read_text(args.file), args.file.name)
    except (OSError, TranscriptError) as exc:
        print(f"회의록을 읽지 못했습니다: {exc}", file=sys.stderr)
        return 2
    rebutter = FakeRebutter() if settings.fake_llm else ClaudeRebutter(settings)
    print(f"발언 {len(utterances)}개를 분석합니다. 1~2분 걸릴 수 있습니다...", file=sys.stderr)
    try:
        result = rebutter.report(
            transcript=format_transcript(utterances),
            ceo_speaker=args.ceo,
            intensity=args.intensity,
            company_context=args.context,
        )
    except RebuttalError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    markdown = report_markdown(result, source_name=args.file.name, intensity=args.intensity)
    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
        print(f"저장했습니다: {args.output}", file=sys.stderr)
    else:
        print(markdown)
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        run_serve(args.host, args.port)
        return 0
    return run_analyze(args)


if __name__ == "__main__":
    sys.exit(main())
