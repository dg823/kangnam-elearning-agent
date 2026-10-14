"""설정 로딩: .env 에서 자격증명과 기본 주소를 읽는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Config:
    username: str = ""
    password: str = ""
    ical_url: str = ""
    base_url: str = "https://ecampus.kangnam.ac.kr"
    cookie_file: Path = PROJECT_ROOT / ".session_cookies.json"

    @property
    def has_login(self) -> bool:
        return bool(self.username and self.password)

    @classmethod
    def load(cls) -> "Config":
        username = os.getenv("KNU_USERNAME", "").strip()
        password = os.getenv("KNU_PASSWORD", "").strip()
        ical_url = os.getenv("ECAMPUS_ICAL_URL", "").strip()
        base = os.getenv("ECAMPUS_BASE", "https://ecampus.kangnam.ac.kr").strip().rstrip("/")
        if not ical_url and not (username and password):
            raise SystemExit(
                "설정이 없습니다. .env.example 을 복사해 .env 를 만들고, "
                "ECAMPUS_ICAL_URL(권장) 또는 KNU_USERNAME/KNU_PASSWORD 를 채워주세요."
            )
        return cls(username=username, password=password, ical_url=ical_url, base_url=base)
