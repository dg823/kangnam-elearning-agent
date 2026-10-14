"""LLM 추상화 계층.

백엔드를 바꿔 끼울 수 있도록 인터페이스를 두고, 로컬 Ollama 를 우선한다.
Ollama 가 없으면 규칙 기반(NullLLM)으로 자동 폴백하여 기능 자체는 항상 동작한다.

환경변수:
  LLM_BACKEND = ollama | none   (기본: 자동 감지)
  OLLAMA_HOST = http://localhost:11434
  OLLAMA_MODEL = qwen2.5:7b (예시)
"""

from __future__ import annotations

import os

import requests


class BaseLLM:
    available: bool = False
    name: str = "none"

    def generate(self, prompt: str, system: str = "") -> str:
        raise NotImplementedError


class NullLLM(BaseLLM):
    """LLM 미설치 환경용 폴백. generate 는 빈 문자열을 반환하며,
    상위 로직이 규칙 기반 경로로 처리하도록 한다."""

    available = False
    name = "none(rule-based)"

    def generate(self, prompt: str, system: str = "") -> str:
        return ""


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model
        self.available = self._ping()

    def _ping(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, system: str = "") -> str:
        try:
            r = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=120,
            )
            r.raise_for_status()
            return (r.json().get("response") or "").strip()
        except Exception as e:  # 실패 시 폴백 유도
            return ""


def get_llm() -> BaseLLM:
    backend = os.getenv("LLM_BACKEND", "auto").strip().lower()
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()

    if backend in ("none", "off", "rule"):
        return NullLLM()
    if backend in ("auto", "ollama", ""):
        llm = OllamaLLM(host, model)
        if llm.available:
            return llm
    return NullLLM()
