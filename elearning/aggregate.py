"""수집 결과 집계: iCal + 스크래핑 병합, 중복 제거, 정렬/필터."""

from __future__ import annotations

from datetime import datetime, timezone

from .calendar_ical import fetch_deadlines_via_ical
from .client import EcampusClient
from .models import Deadline
from .scraper import fetch_course_deadlines, fetch_courses, fetch_upcoming


def collect_deadlines(
    client: EcampusClient, ical_url: str = "", scrape: bool = True, progress=None
) -> list[Deadline]:
    """마감일을 모아 병합한다. 정확도 우선순위:

    1) 강좌별 활동 페이지 스크래핑 — 정확한 종료시각 + 제출여부 (로그인 필요)
    2) iCal export — 날짜만(시각 미정)일 수 있으나 로그인 없이 가능

    같은 과제가 두 소스에 모두 있으면 (1)의 정확한 정보를 우선한다.
    progress: 선택적 콜백 progress(msg) — 진행상황 출력용.
    """
    def _log(msg):
        if progress:
            progress(msg)

    precise: list[Deadline] = []
    if scrape:
        courses = fetch_courses(client)
        _log(f"강좌 {len(courses)}개 발견")
        for i, course in enumerate(courses, 1):
            items = fetch_course_deadlines(client, course)
            _log(f"  [{i}/{len(courses)}] {course.name} · 과제/퀴즈 {len(items)}건")
            precise.extend(items)

    ical_items = fetch_deadlines_via_ical(client, ical_url=ical_url)

    # 스크래핑(정밀)을 정본으로 삼고, 그와 매칭되는 iCal 항목은 모두 버린다.
    # (iCal 은 퀴즈를 시작/종료 두 건으로 쪼개지만 스크래핑은 한 건에 정확한
    #  종료시각을 담으므로, 매칭되는 iCal 중복을 제거해야 한다.)
    final: list[Deadline] = list(precise)
    for it in ical_items:
        if not any(_same_activity(it, s) for s in precise):
            final.append(it)
    return final


def _same_activity(a: Deadline, b: Deadline) -> bool:
    """같은 강좌이고 제목 핵심이 겹치면 동일 활동으로 본다."""
    if _norm_course(a.course) != _norm_course(b.course):
        return False
    na, nb = _norm(a.title), _norm(b.title)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _norm(s: str) -> str:
    import re
    return re.sub(r"\s+", "", s or "")


def _norm_course(s: str) -> str:
    """'컴퓨터비전응용[00]' 과 '컴퓨터비전응용' 을 같게 본다."""
    import re
    s = re.sub(r"[\[\(].*?[\]\)]", "", s or "")
    return re.sub(r"\s+", "", s)


def upcoming_sorted(
    deadlines: list[Deadline],
    include_overdue: bool = False,
    within_days: float | None = None,
) -> list[Deadline]:
    now = datetime.now(timezone.utc)
    result = []
    for dl in deadlines:
        if dl.due is None:
            continue
        dleft = (dl.due - now).total_seconds() / 86400.0
        if not include_overdue and dleft < 0:
            continue
        if within_days is not None and dleft > within_days:
            continue
        result.append(dl)
    result.sort(key=lambda d: d.due)  # type: ignore[arg-type]
    return result


__all__ = ["collect_deadlines", "upcoming_sorted", "fetch_courses"]
