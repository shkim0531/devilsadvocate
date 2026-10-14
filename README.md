# 😈 악마의 변호인 회의 에이전트

회의 중 대표의 결정·주장을 듣고 가장 논리적인 반론을 제기하는 AI 에이전트입니다.
집단사고를 막기 위해 일부러 반대편에 서는 "악마의 변호인" 역할을 Claude가 맡습니다.

목적은 대표를 이기는 것이 아니라, 실행 전에 약점을 드러내 결정을 더 단단하게 만드는 것입니다.

> **설치·API 키 없이 쓰려면:** claude.ai 프로젝트에 지침만 붙여 넣으면 녹취록 반론 리포트를 만들 수 있습니다.
> [claude-ai/README.md](claude-ai/README.md)를 보세요. (실시간 회의 기능은 아래 프로그램 버전에만 있습니다.)

## 기능

| 모드 | 언제 | 하는 일 |
|---|---|---|
| 🎙 실시간 회의 | 회의 중 | 노트북 마이크로 회의를 받아 적다가 대표의 결정이 나오면 반론 카드를 띄움. 소리 내어 읽기 가능 |
| 📄 회의록 분석 | 회의 후 | 클로바노트·Zoom·Teams 회의록(.txt, .vtt, .srt)을 넣으면 반론 리포트 작성. 마크다운 저장·인쇄 가능 |

### 반론 카드 구성

- **대표 논리의 최강 버전:** 대표 논리를 먼저 가장 강하게 정리해 허수아비 공격을 막음
- **가장 약한 가정:** 틀리면 결정 전체가 무너지는 전제
- **반론 포인트:** 숨은 가정, 근거 부족, 실패 시나리오, 기회비용, 실행 리스크, 이해관계자, 인지 편향
- **지금 던질 질문:** 회의에서 바로 물어볼 한 문장
- **대안**, **이게 확인되면 인정:** 반대로만 끝나지 않도록 출구 제시
- **심각도:** 1~5

### 설정

- **반박 강도:** 순한맛 · 보통맛 · 매운맛(기본)
- **반박 대상:** 자동(결정·지시성 발언을 알아서 골라냄) / 수동('👔 대표 발언 중' 버튼을 켠 동안 나온 발언만)
- **회사 맥락:** 직원 수, 자금 사정, 올해 목표 등을 적으면 반론이 현실적으로 바뀜
- **소리 내어 읽기:** 새 반론의 '가장 약한 가정'과 '지금 던질 질문'을 스피커로 읽어 줌

설정은 브라우저에 저장되어 다음에 열 때도 유지됩니다.

### 원칙

- 수치·사례·법 조항을 지어내지 않고, 모르는 것은 "확인이 필요하다"는 질문으로 바꿈
- 사람이 아니라 아이디어를 공격하고, 정중한 존댓말을 씀
- 결정이 아닌 발언에는 억지로 반론하지 않고, 이미 한 반론은 되풀이하지 않음

## 실행 방법

준비물: Python 3.10 이상, Google Chrome, Claude API 키([Anthropic 콘솔](https://console.anthropic.com)에서 발급)

**Windows (PowerShell)**

```powershell
git clone https://github.com/shkim0531/devilsadvocate.git
cd devilsadvocate
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # 메모장으로 .env를 열어 ANTHROPIC_API_KEY 입력
python -m devils_advocate serve
```

> PowerShell에서 `Activate.ps1` 실행이 막히면 먼저 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 실행하세요.

**macOS**

```bash
git clone https://github.com/shkim0531/devilsadvocate.git
cd devilsadvocate
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # .env를 열어 ANTHROPIC_API_KEY 입력
python -m devils_advocate serve
```

Chrome에서 http://localhost:8000 을 열고 마이크를 허용합니다.

처음에는 **📄 회의록 분석 → 📋 예시 회의록 → 😈 반론 리포트 만들기**로 결과부터 확인하는 것을 권장합니다.

### 회의록을 터미널에서 바로 분석

```bash
python -m devils_advocate analyze 회의록.txt --ceo 대표 -o 리포트.md
```

`--ceo`는 회의록에 적힌 대표 화자 이름입니다(생략하면 Claude가 판단). `--intensity mild|medium|spicy`, `--context "직원 12명..."`도 쓸 수 있습니다.

### API 키 없이 화면만 확인

`.env`에 `DA_FAKE_LLM=1`을 넣으면 Claude를 부르지 않고 가짜 반론으로 화면 흐름만 확인할 수 있습니다.

## 동작 방식

```
회의 음성 → Chrome 음성 인식(한국어) → 발언 기록
                                         ↓
반론 카드 ← Claude가 반론 작성 ← 서버가 끼어들 때 판단
```

서버는 브라우저가 1.5초마다 묻는 요청에 답하면서, 다음 조건이 모두 맞을 때만 Claude를 부릅니다.

1. 마지막 판단 이후 새 발언이 있음
   - 자동 모드: 새 발언 중 하나 이상이 결정·지시성 표현("하겠습니다", "합시다", "진행", "채용", "출시" 등)을 포함
   - 수동 모드: '대표 발언'으로 표시된 새 발언이 있음
2. 말이 2.5초 이상 멈춤 (새 발언이 5개 이상 쌓이면 멈추지 않아도 진행)
3. 마지막 반론 요청 뒤 30초 이상 지남

결정이 아닌 발언이면 Claude가 반론하지 않고 넘어갑니다. **⚡ 지금 반박** 버튼은 위 조건과 상관없이 즉시 요청합니다.

- 사용 모델: `claude-opus-5-5` (`.env`의 `DA_MODEL`로 변경 가능)
- 실시간 반론은 빠르게(`effort: medium`), 회의록 리포트는 꼼꼼하게(`effort: high`) 작성
- Claude의 안전 장치가 요청을 거절하면 Anthropic이 권장하는 다른 모델로 자동 재시도(server-side fallback)
- 실시간 반론에는 최근 발언 40개만 보내 속도와 비용을 줄임

### 설정값 (.env)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (필수) | Claude API 키 |
| `DA_MODEL` | `claude-opus-5-5` | 사용할 모델 |
| `DA_MIN_INTERVAL` | `30` | 반론 사이 최소 간격(초) |
| `DA_PAUSE_SECONDS` | `2.5` | 말이 멈췄다고 보는 침묵 길이(초) |
| `DA_LIVE_EFFORT` | `medium` | 실시간 반론의 생각 깊이 (`low`~`max`) |
| `DA_REPORT_EFFORT` | `high` | 회의록 리포트의 생각 깊이 |
| `DA_FAKE_LLM` | `0` | `1`이면 가짜 응답 모드 |

## 비용 (추정)

`claude-opus-5-5` 요금(입력 100만 토큰당 4달러, 출력 100만 토큰당 20달러) 기준 추정치입니다. 실제 비용은 회의 길이와 반론 횟수에 따라 달라집니다.

| 항목 | 비용 |
|---|---|
| 실시간 회의 1시간 | 약 2~5달러 |
| 회의록 리포트 1건 | 약 0.3~0.5달러 |
| 음성 인식 (Chrome) | 무료 |

Anthropic 콘솔에서 월 사용 한도를 설정해 두는 것을 권장합니다.

## 주의 사항

- **음성 인식 품질:** 조용한 대면 회의에서는 쓸 만하지만 동시 발화·원거리에서는 정확도가 떨어집니다. Chrome 음성 인식은 화자를 구분하지 못합니다.
- **데이터 전송:** 음성은 Google(Chrome 음성 인식), 텍스트는 Anthropic으로 전송됩니다. 사내 보안·개인정보 정책을 확인하세요.
- **녹음 고지:** 참석자에게 미리 알리고 동의를 받는 것을 권장합니다.
- **최종 판단은 사람이:** 반론은 판단 재료이며 회의 맥락을 잘못 이해할 수 있습니다.
- **조직 문화:** 대표가 이 역할에 동의할 때 효과가 가장 큽니다.
- **접속 범위:** 기본은 이 컴퓨터에서만 접속됩니다(127.0.0.1). 인증 기능이 없으니 `--host 0.0.0.0` 등으로 외부에 공개하지 마세요.
- **기록 보관:** 실시간 회의 기록은 서버 메모리에만 있고 서버를 끄면 사라집니다. 필요하면 **💾 기록 저장**으로 내려받으세요.

## 개발

```bash
pip install -r requirements-dev.txt
python -m pytest
```

```
devils_advocate/
├── __main__.py     # 명령줄 (serve, analyze)
├── server.py       # 웹 서버와 API
├── session.py      # 실시간 회의 상태, 끼어들 시점 판단
├── llm.py          # Claude 호출, 가짜 응답
├── prompts.py      # Claude 지시문
├── schema.py       # 반론 카드 형식(JSON 스키마)
├── transcript.py   # 회의록 파일 읽기(.txt, .vtt, .srt)
├── report.py       # 마크다운 변환
├── samples/        # 예시 회의록
└── static/         # 화면 (HTML, CSS, JS)
```

## 다음 단계 후보

- 외부 실시간 전사 연동 (Windows 11 실시간 자막, WhisperLiveKit 등)
- 한국어 특화 음성 인식 API 연동으로 화자 자동 구분
- 슬랙으로 반론·리포트 전송
- 회의 간 기억: 지난 회의의 결정과 약속을 추적해 반론에 활용
