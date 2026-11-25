# 클라우드 배포 가이드 (Render.com, 무료)

PC를 꺼도 폰에서 24시간 접속할 수 있도록 클라우드에 올리는 방법입니다.
무료이며 HTTPS가 기본 제공됩니다.

## ⚠️ 먼저 읽기 (보안)

- 정밀 모드는 학교 로그인이 필요하므로 **비밀번호가 Render에 환경변수로 저장**됩니다.
  환경변수는 저장소(GitHub)에는 올라가지 않고 Render 서버에만 보관됩니다.
- **`WEB_TOKEN`을 반드시 설정하세요.** 안 하면 링크를 아는 누구나 과제 목록을 봅니다.
  토큰은 길고 추측 어려운 문자열로 (예: `knu-a8f3k2x9qp`).

## 준비물

- GitHub 계정 (이미 저장소 올림: `dg823/kangnam-elearning-agent`)
- Render.com 계정 (GitHub로 가입 가능, 무료)

## 단계

1. **Render 가입** — https://render.com → "Get Started" → GitHub로 로그인.

2. **새 서비스 생성**
   - 대시보드 → **New +** → **Web Service**
   - **Build and deploy from a Git repository** 선택 → `kangnam-elearning-agent` 저장소 연결
   - Render가 `render.yaml` 을 자동 인식합니다.

3. **환경변수 입력** (Environment 탭) — 본인이 직접 입력:

   | 키 | 값 |
   |---|---|
   | `ECAMPUS_ICAL_URL` | 이러닝 캘린더 iCal URL |
   | `KNU_USERNAME` | 본인 학번 |
   | `KNU_PASSWORD` | 본인 비밀번호 |
   | `WEB_TOKEN` | 직접 정한 비밀 토큰 (예: `knu-a8f3k2x9qp`) |

4. **배포** — Create Web Service. 몇 분 후 `https://kangnam-elearning.onrender.com` 같은 주소가 생깁니다.

5. **폰에서 접속** — 주소 끝에 토큰을 붙여서:
   ```
   https://<생성된주소>.onrender.com/?token=knu-a8f3k2x9qp
   ```
   한 번 열면 토큰이 저장되어 이후엔 그냥 접속됩니다. "홈 화면에 추가"로 앱처럼.

## 참고 (무료 플랜 특성)

- 무료 플랜은 15분간 요청이 없으면 서버를 재웁니다. 이 앱은 Render 에서 실행될 때
  10분마다 자기 주소(`/healthz`)를 불러 **스스로 깨어 있으므로** 따로 설정할 것이 없습니다.
- 그래서 서버 하나가 한 달 내내 켜져 있게 되며, Render 무료 한도(월 750시간) 안에 들어갑니다.
  같은 계정에 다른 무료 서비스를 더 만들면 이 시간을 나눠 쓰게 되니 주의하세요.
- 데이터는 아무도 안 열어도 3시간마다 미리 새로 받고, 열었을 때 20분 넘게 지났으면
  화면은 저장된 데이터로 바로 보여주면서 뒤에서 새로 받습니다(약 15초).
- 로컬 AI(Ollama)는 클라우드에서 안 돌아가므로, 질문·요약은 **규칙 기반**으로 동작합니다
  (마감 목록·필터·제출여부는 동일하게 정확).

## 비밀번호를 클라우드에 두기 싫다면

`KNU_USERNAME`/`KNU_PASSWORD` 를 빼고 `ECAMPUS_ICAL_URL` 만 넣으면
비밀번호 없이 iCal 모드로 동작합니다(마감 날짜는 정확, 시각은 근사·제출여부 없음).
