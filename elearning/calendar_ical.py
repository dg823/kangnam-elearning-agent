"""iCal 캘린더 export 를 통한 마감일 수집 (1차 소스).

Moodle 의 calendar/export.php 폼을 제출하면 authtoken 이 포함된
export_execute.php(.ics) URL 이 생성된다. 그 URL 을 받아 파싱한다.
로그인 세션이 있어야 authtoken 생성이 가능하다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

from bs4 import BeautifulSoup

try:
    from icalendar import Calendar
except Exception:  # pragma: no cover
    Calendar = None

from .client import EcampusClient
from .models import Deadline


def fetch_ical_url(client: EcampusClient) -> str | None:
    """export.php 폼을 제출해 .ics export URL 을 얻는다."""
    r = client.get("/calendar/export.php")
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    form = soup.find("form")
    if not form:
        return None

    payload: dict[str, str] = {}
    for inp in form.find_all(("input",)):
        name = inp.get("name")
        if name:
            payload[name] = inp.get("value", "")
    # 프리셋: 전체 이벤트 + 최근/예정
    payload.setdefault("preset_what", "all")
    payload.setdefault("preset_time", "recentupcoming")
    if "generateurl" not in payload:
        payload["generateurl"] = "예"

    action = form.get("action") or "/calendar/export.php"
    resp = client.session.post(
        action if action.startswith("http") else client.base + action,
        data=payload,
        timeout=20,
    )
    if resp.status_code != 200:
        return None

    m = re.search(r'https?://[^\s"\'<>]*export_execute\.php[^\s"\'<>]*', resp.text)
    return m.group(0).replace("&amp;", "&") if m else None


def fetch_deadlines_via_ical(client: EcampusClient, ical_url: str = "") -> list[Deadline]:
    """ical_url 이 주어지면 그 URL 을 직접 사용(로그인 불필요),
    없으면 로그인 세션으로 export 폼을 제출해 URL 을 생성한다."""
    if Calendar is None:
        return []
    url = ical_url or fetch_ical_url(client)
    if not url:
        return []
    r = client.session.get(url, timeout=25)
    if r.status_code != 200 or b"BEGIN:VCALENDAR" not in r.content:
        return []
    return parse_ical(r.content)


def parse_ical(data: bytes) -> list[Deadline]:
    cal = Calendar.from_ical(data)
    out: list[Deadline] = []
    for comp in cal.walk("VEVENT"):
        summary = str(comp.get("summary", "")).strip()
        dt = comp.get("dtstart")
        # 날짜만 있는 이벤트(VALUE=DATE)는 그날 마감으로 간주
        is_date_only = bool(dt) and not isinstance(getattr(dt, "dt", None), datetime)
        due = _to_dt(dt.dt, is_date_only) if dt is not None else None
        categories = _raw(comp.get("categories"))
        desc = str(comp.get("description", ""))
        out.append(
            Deadline(
                title=summary,
                due=due,
                course=_extract_course(categories),
                kind=_guess_kind(summary),
                url=_extract_url(desc),
                source="ical",
                time_known=not is_date_only,
                raw_id=str(comp.get("uid", "")),
            )
        )
    return out


def _to_dt(value, is_date_only: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    # date 만 있는 경우: 해당 날짜의 한국시간 23:59 를 마감으로 본다
    if hasattr(value, "year"):
        return datetime(value.year, value.month, value.day, 23, 59, tzinfo=KST)
    return None


# 제목 키워드 기반 종류 판별 (한국어 Coursemos 기준)
_KIND_RULES = [
    ("quiz", ("퀴즈", "quiz", "시험", "중간고사", "기말고사", "테스트")),
    ("assign", ("과제", "실습", "프로젝트", "보고서", "레포트", "리포트", "제출", "assign")),
    ("video", ("동영상", "영상", "출석", "강의", "video", "vod", "주차")),
]


def _guess_kind(summary: str) -> str:
    s = summary.lower()
    for kind, keywords in _KIND_RULES:
        if any(k.lower() in s for k in keywords):
            return kind
    return "event"


def _raw(value) -> str:
    """icalendar 속성 객체에서 원본 텍스트를 안전하게 추출."""
    if value is None:
        return ""
    try:
        return value.to_ical().decode("utf-8", "ignore").replace("\\,", ",").strip()
    except Exception:
        return str(value)


def _extract_url(desc: str) -> str:
    m = re.search(r'https?://[^\s"\'<>]+', desc)
    return m.group(0) if m else ""


def _extract_course(categories: str) -> str:
    """CATEGORIES 예: '컴퓨터비전응용(2026년도, 2학기, EB14210, 00)' → '컴퓨터비전응용'"""
    if not categories:
        return ""
    return categories.split("(", 1)[0].strip()
