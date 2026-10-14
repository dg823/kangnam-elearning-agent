"""데이터 모델: 과제/마감일 등 수집 대상을 표현한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Deadline:
    """하나의 마감 이벤트 (과제, 퀴즈, 영상 등)."""

    title: str
    due: Optional[datetime]          # 마감 일시 (tz-aware). 없으면 None
    course: str = ""                 # 강좌명
    kind: str = "unknown"            # assign / quiz / lesson / video / event ...
    url: str = ""                    # 바로가기 링크
    source: str = ""                 # 수집 출처 (ical / scrape)
    submitted: Optional[bool] = None  # 제출 완료 여부 (알 수 있을 때)
    time_known: bool = True          # 마감 '시각'이 확정인지 (iCal 날짜형은 False)
    description: str = ""            # 과제 설명 (요약용, 정밀 스크래핑 시)
    raw_id: str = ""                 # 중복 제거용 원본 식별자

    def dedup_key(self) -> str:
        if self.raw_id:
            return self.raw_id
        stamp = self.due.isoformat() if self.due else "no-due"
        return f"{self.course}|{self.title}|{stamp}"

    @property
    def days_left(self) -> Optional[float]:
        if not self.due:
            return None
        now = datetime.now(timezone.utc)
        return (self.due - now).total_seconds() / 86400.0

    @property
    def is_overdue(self) -> bool:
        dl = self.days_left
        return dl is not None and dl < 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "due": self.due.isoformat() if self.due else None,
            "course": self.course,
            "kind": self.kind,
            "url": self.url,
            "source": self.source,
            "submitted": self.submitted,
            "time_known": self.time_known,
            "description": self.description,
            "raw_id": self.raw_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Deadline":
        due = datetime.fromisoformat(d["due"]) if d.get("due") else None
        return cls(
            title=d.get("title", ""), due=due, course=d.get("course", ""),
            kind=d.get("kind", "unknown"), url=d.get("url", ""),
            source=d.get("source", ""), submitted=d.get("submitted"),
            time_known=d.get("time_known", True), description=d.get("description", ""),
            raw_id=d.get("raw_id", ""),
        )


@dataclass
class Course:
    """수강 강좌."""

    name: str
    course_id: str = ""
    url: str = ""
    deadlines: list[Deadline] = field(default_factory=list)
