# 강남대 이러닝캠퍼스 과제·마감일 에이전트

강남대학교 이러닝캠퍼스([ecampus.kangnam.ac.kr](https://ecampus.kangnam.ac.kr))에 흩어진
과제와 마감일을 한곳에 모아 보여주고, 로컬 AI로 요약·질문까지 할 수 있는 에이전트입니다.

## 주요 기능

- **마감 목록** — 모든 강좌의 과제·퀴즈 마감을 D-day 순으로 한 표에
- **제출 여부 표시** — 제출 완료 / 미제출 구분
- **오늘·내일 브리핑** — 당장 할 일만 추려서
- **자연어 질문** — "이번주 미제출 과제" 처럼 물어보기
- **과제 AI 요약** — 과제 설명을 로컬 LLM이 요약
- **로컬 AI** — Ollama가 있으면 자연어로, 없으면 규칙 기반으로 **항상 동작**

## 이러닝캠퍼스 분석 결과

| 항목 | 내용 |
|---|---|
| 플랫폼 | **Moodle** 기반 + 한국형 **Coursemos / Ubion** 커스터마이징 |
| 로그인 | `login/index.php` (아이디/비밀번호) + SSO |
| 마감일 소스 | `calendar/export_execute.php` (iCal) — 로그인 없이 접근 가능 |
| 과제 상세 | 강좌별 `mod/assign`·`mod/quiz` 페이지 스크래핑 — 정확한 시각·제출여부 |

## 수집 방식 (두 가지 모드)

```
                ┌─ iCal 캘린더 export ─────▶ 마감 날짜 (로그인 불필요, 시각은 근사)
수집 ─┤
                └─ 강좌별 과제/퀴즈 스크래핑 ▶ 정확한 종료시각 + 제출여부 (로그인 필요)
                                   │
                                   ▼
                     집계·중복제거·정렬·필터 (aggregate)
                                   │
                                   ▼
             CLI 출력  +  로컬 AI (요약 / 자연어 질문 / 브리핑)
```

| 모드 | 조건 | 특징 |
|---|---|---|
| iCal | `ECAMPUS_ICAL_URL` 만 설정 | 비밀번호 불필요. 마감 '날짜'는 정확, '시각'은 근사 |
| 정밀 | `KNU_USERNAME` / `KNU_PASSWORD` 설정 | 각 과제 페이지에서 정확한 종료시각 + 제출여부 수집 |

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env        # .env 에 본인 설정 입력
```

## 사용법

```bash
python -m elearning.main                 # 마감 목록 표 (기본)
python -m elearning.main list --all      # 지난 마감까지 포함
python -m elearning.main -v list         # 진행상황 자세히 출력
python -m elearning.main digest          # 오늘/내일 마감 브리핑
python -m elearning.main ask "이번주 미제출 과제"   # 자연어 질문
python -m elearning.main summary         # 과제 AI 요약 (정밀 모드 필요)
```

## 로컬 AI (선택)

`digest`·`ask`·`summary` 는 로컬 LLM([Ollama](https://ollama.com))이 켜져 있으면
자연스러운 문장으로, 없으면 규칙 기반으로 동작합니다. **Ollama 없이도 모든 기능이 동작**합니다.

```bash
ollama pull qwen2.5:3b        # 한 번만 (한국어 가능 모델)
# .env 의 LLM_BACKEND=auto 이면 자동 감지해 사용
```

데이터(과제 정보)가 전부 로컬에 있고 AI도 로컬에서 돌므로 **개인정보가 외부로 나가지 않습니다.**

## 설정 (.env)

| 키 | 설명 |
|---|---|
| `ECAMPUS_ICAL_URL` | iCal 마감일 URL (캘린더 → 달력 내보내기에서 복사) |
| `KNU_USERNAME` / `KNU_PASSWORD` | 정밀 모드용 로그인 (선택) |
| `OLLAMA_MODEL` | 사용할 로컬 모델 (예: `qwen2.5:3b`) |

## 보안 원칙

- 계정 비밀번호는 로컬 `.env` 에만 저장하며 저장소에 커밋하지 않습니다 (`.gitignore` 처리).
- 로그인 세션 쿠키는 로컬 파일(`.session_cookies.json`)에만 캐시합니다.
- 외부로 어떤 자격증명도 전송하지 않습니다.

## 프로젝트 구조

```
elearning/
  client.py         로그인 + 세션 관리
  calendar_ical.py  iCal export 파싱 (마감 날짜)
  scraper.py        강좌별 과제/퀴즈 스크래핑 (정확한 시각·제출여부)
  aggregate.py      두 소스 병합·중복제거·정렬·필터
  assistant.py      브리핑 / 자연어 질문 / 요약 (규칙 + LLM 하이브리드)
  llm.py            로컬 LLM(Ollama) 추상화 + 폴백
  models.py         데이터 모델
  config.py         .env 설정 로딩
  main.py           CLI 진입점
```
