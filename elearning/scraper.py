"""HTML 스크래핑 기반 수집 (보조/대체 소스).

iCal 이 막혀 있거나 상세정보가 필요할 때 사용한다.
- 수강 강좌 목록: /my/ 대시보드
- 예정 마감: /calendar/view.php?view=upcoming

주의: Coursemos/Ubion 테마의 실제 DOM 은 로그인 후 1회 점검하여
셀렉터를 보정할 필요가 있다. (아래 selector 는 표준 Moodle 기준)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from .client import EcampusClient
from .models import Course, Deadline

_KST = timezone.utc  # 표시는 로컬에서 변환; 저장은 tz-aware 로


def fetch_courses(client: EcampusClient) -> list[Course]:
    """수강 강좌 목록을 캘린더 페이지의 강좌 선택 콤보박스에서 얻는다.

    (/my/ 대시보드는 강좌 링크를 JS로 렌더링해 서버 HTML 에 없으므로,
     서버가 그대로 내려주는 select[name=course] 를 신뢰한다.)
    """
    r = client.get("/calendar/view.php?view=upcoming")
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    select = soup.find("select", {"name": "course"})
    courses: list[Course] = []
    if not select:
        return courses
    for opt in select.find_all("option"):
        cid = (opt.get("value") or "").strip()
        name = opt.get_text(strip=True)
        if not cid.isdigit() or cid == "1" or not name:
            continue  # '1' = 모든 강좌
        courses.append(
            Course(
                name=name,
                course_id=cid,
                url=f"{client.base}/course/view.php?id={cid}",
            )
        )
    return courses


def fetch_upcoming(client: EcampusClient) -> list[Deadline]:
    r = client.get("/calendar/view.php?view=upcoming")
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    out: list[Deadline] = []

    # 표준 Moodle: 각 이벤트가 [data-region="event-item"] 혹은 .event 로 감싸짐
    blocks = soup.select("[data-region='event-item'], div.event, .eventlist .event")
    for b in blocks:
        link = b.find("a", href=re.compile(r"/mod/\w+/view\.php"))
        title_el = b.select_one(".name, h3, .event-name") or link
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue
        due = _find_datetime(b)
        url = _abs(client, link["href"]) if link else ""
        out.append(
            Deadline(
                title=title,
                due=due,
                kind=_kind_from_url(url),
                url=url,
                source="scrape",
            )
        )
    return out


def _find_datetime(node) -> datetime | None:
    # <time datetime="..."> 우선
    t = node.find("time")
    if t and t.get("datetime"):
        try:
            return datetime.fromisoformat(t["datetime"].replace("Z", "+00:00"))
        except ValueError:
            pass
    # 텍스트에서 날짜 패턴 탐색 (예: 2026-09-30, 2026년 9월 30일)
    text = node.get_text(" ", strip=True)
    m = re.search(r"(\d{4})[-.년\s]+(\d{1,2})[-.월\s]+(\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        hm = re.search(r"(\d{1,2}):(\d{2})", text)
        hour, minute = (int(hm.group(1)), int(hm.group(2))) if hm else (23, 59)
        return datetime(y, mo, d, hour, minute, tzinfo=timezone.utc)
    return None


def _activity_title(a) -> str:
    """Moodle 활동 링크에서 활동명만 추출한다.

    Moodle 은 활동명 뒤에 모듈 종류를 숨김 라벨로 붙인다:
      <span class="instancename">중간 퀴즈<span class="accesshide"> 퀴즈</span></span>
    따라서 .accesshide(숨김 라벨)를 제거하고 instancename 텍스트를 쓴다.
    이렇게 하면 '중간 퀴즈' 같은 이름의 ' 퀴즈'를 실수로 자르지 않는다.
    """
    name_el = a.select_one(".instancename") or a
    # 복제본에서 숨김 라벨 제거
    import copy
    el = copy.copy(name_el)
    for hide in el.select(".accesshide, .visually-hidden, .sr-only"):
        hide.extract()
    title = el.get_text(" ", strip=True)
    # instancename 이 없을 때의 폴백: 끝의 '공백+모듈라벨'만 보수적으로 제거
    if name_el is a:
        title = re.sub(r"\s+(과제|퀴즈|Assignment|Quiz)$", "", title).strip()
    return title


def fetch_course_deadlines(client: EcampusClient, course: Course) -> list[Deadline]:
    """강좌 페이지의 모든 과제/퀴즈 활동을 찾아 각 페이지에서
    정확한 종료일시와 제출여부를 수집한다 (정밀 경로, 로그인 필요)."""
    r = client.get(f"/course/view.php?id={course.course_id}")
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    seen: set[str] = set()
    out: list[Deadline] = []
    for a in soup.find_all("a", href=re.compile(r"/mod/(assign|quiz)/view\.php\?id=\d+")):
        href = _abs(client, a["href"])
        if href in seen:
            continue
        seen.add(href)
        title = _activity_title(a)
        detail = _fetch_activity_detail(client, href)
        out.append(
            Deadline(
                title=title or detail.get("title", ""),
                due=detail.get("due"),
                course=course.name,
                kind=_kind_from_url(href),
                url=href,
                source="scrape",
                submitted=detail.get("submitted"),
                time_known=detail.get("due") is not None,
                description=detail.get("description", ""),
            )
        )
    return out


# 라벨은 공백을 무시하고 비교한다('종료 일시' == '종료일시').
_LABELS_DUE = ("종료일시", "마감일시", "제출마감", "응시마감", "닫는시간")
_LABELS_SUB = ("제출여부", "완료상황", "시도상황")

# 퀴즈 등 문장형 페이지용: '종료일시 : 2026-10-21 00:00'
_DUE_TEXT_RE = re.compile(
    r"(?:종료\s*일시|마감\s*일시|닫는\s*시간|응시\s*마감)\s*[:：]?\s*"
    r"(\d{4}[-.]\s?\d{1,2}[-.]\s?\d{1,2}(?:[^0-9]{0,4}\d{1,2}:\d{2})?)"
)


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _fetch_activity_detail(client: EcampusClient, url: str) -> dict:
    r = client.get(url)
    if r.status_code != 200:
        return {}
    soup = BeautifulSoup(r.text, "lxml")
    detail: dict = {}
    # 1) 표 구조 (과제 페이지)
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(("th", "td"))]
        if len(cells) < 2:
            continue
        label, value = _nospace(cells[0]), cells[1]
        if "due" not in detail and any(k in label for k in _LABELS_DUE):
            dt = _parse_kdate(value)
            if dt:
                detail["due"] = dt
        if "submitted" not in detail and any(k in label for k in _LABELS_SUB):
            detail["submitted"] = ("제출 완료" in value) or ("완료" in value and "안 함" not in value)
    # 2) 문장형 (퀴즈 페이지) — 표에서 못 찾았으면 전체 텍스트에서 종료일시 추출
    if "due" not in detail:
        m = _DUE_TEXT_RE.search(soup.get_text(" ", strip=True))
        if m:
            dt = _parse_kdate(m.group(1))
            if dt:
                detail["due"] = dt
    # 과제 설명(인트로) 추출
    intro = soup.select_one("#intro, .activity-description, .box.generalbox, .no-overflow")
    if intro:
        detail["description"] = intro.get_text(" ", strip=True)[:1000]
    return detail


def _parse_kdate(text: str) -> datetime | None:
    """'2026-09-30 14:40' / '2026년 9월 30일 14:40' 형태 파싱 (KST 기준)."""
    m = re.search(r"(\d{4})[-.년\s]+(\d{1,2})[-.월\s]+(\d{1,2})", text)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    hm = re.search(r"(\d{1,2}):(\d{2})", text)
    hour, minute = (int(hm.group(1)), int(hm.group(2))) if hm else (23, 59)
    return datetime(y, mo, d, hour, minute, tzinfo=timezone(timedelta(hours=9)))


def _kind_from_url(url: str) -> str:
    m = re.search(r"/mod/(\w+)/", url)
    if not m:
        return "event"
    mod = m.group(1)
    return {"assign": "assign", "quiz": "quiz", "lesson": "lesson"}.get(mod, mod)


def _abs(client: EcampusClient, href: str) -> str:
    if href.startswith("http"):
        return href
    return client.base + (href if href.startswith("/") else "/" + href)
