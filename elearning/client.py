"""이러닝캠퍼스 로그인 및 세션 관리.

Moodle 표준 로그인 폼(login/index.php)에 대응한다.
- 로그인 페이지에서 hidden 필드(logintoken 등)를 파싱해 함께 전송
- 성공 시 MoodleSession 쿠키를 로컬에 캐시해 재사용
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import Config

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class EcampusClient:
    def __init__(self, config: Config):
        self.cfg = config
        self.base = config.base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ------------------------------------------------------------------ #
    # 세션 캐시
    # ------------------------------------------------------------------ #
    def _load_cookies(self) -> bool:
        p: Path = self.cfg.cookie_file
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for name, value in data.items():
                self.session.cookies.set(name, value, domain=_host(self.base))
            return True
        except Exception:
            return False

    def _save_cookies(self) -> None:
        data = {c.name: c.value for c in self.session.cookies}
        self.cfg.cookie_file.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 로그인
    # ------------------------------------------------------------------ #
    def is_logged_in(self) -> bool:
        """/my/ 접근 시 로그인 페이지로 튕기지 않으면 로그인 상태로 간주."""
        r = self.session.get(f"{self.base}/my/", allow_redirects=False, timeout=15)
        return r.status_code == 200

    def login(self, force: bool = False) -> None:
        if not force and self._load_cookies() and self.is_logged_in():
            return

        login_url = f"{self.base}/login/index.php"
        r = self.session.get(login_url, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        form = _find_login_form(soup)
        if form is None:
            raise RuntimeError(
                "로그인 폼을 찾지 못했습니다. SSO 전용으로 바뀌었을 수 있습니다."
            )

        payload: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                payload[name] = inp.get("value", "")
        payload["username"] = self.cfg.username
        payload["password"] = self.cfg.password

        action = form.get("action") or login_url
        if action.startswith("/"):
            action = self.base + action

        resp = self.session.post(action, data=payload, timeout=15)
        resp.raise_for_status()

        if not self.is_logged_in():
            raise RuntimeError(
                "로그인에 실패했습니다. 아이디/비밀번호를 확인하거나, "
                "SSO 인증이 필요한 계정인지 확인하세요."
            )
        self._save_cookies()

    # ------------------------------------------------------------------ #
    def get(self, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base}{path}"
        return self.session.get(url, timeout=20, **kwargs)


def _host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def _find_login_form(soup: BeautifulSoup):
    # 우선순위: password 필드를 가진 form
    for form in soup.find_all("form"):
        if form.find("input", {"type": "password"}):
            return form
    return soup.find("form", {"id": "login"}) or soup.find("form")
