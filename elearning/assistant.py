"""마감 데이터 위에서 동작하는 어시스턴트 기능.

각 기능은 LLM 이 있으면 자연스러운 문장으로, 없으면 규칙 기반으로 동작한다.
따라서 Ollama 미설치 환경에서도 모든 기능이 '동작'은 한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .llm import BaseLLM
from .models import Deadline

KST = timezone(timedelta(hours=9))


def _fmt(dl: Deadline) -> str:
    if not dl.due:
        return "(마감 미정)"
    local = dl.due.astimezone(KST)
    when = local.strftime("%m/%d %H:%M") if dl.time_known else local.strftime("%m/%d(시각미정)")
    sub = ""
    if dl.submitted is True:
        sub = " [제출완료]"
    elif dl.submitted is False:
        sub = " [미제출]"
    d = dl.days_left
    dd = f"D{int(d):+d}" if d is not None else ""
    return f"- {when} {dd} · {dl.kind} · {dl.course} · {dl.title}{sub}"


def _context(deadlines: list[Deadline]) -> str:
    lines = [_fmt(d) for d in sorted(deadlines, key=lambda x: (x.due or datetime.max.replace(tzinfo=KST)))]
    return "\n".join(lines)


# --------------------------------------------------------------------- #
# 1) 오늘/내일 브리핑 (규칙 기반, LLM 선택적)
# --------------------------------------------------------------------- #
def build_digest(deadlines: list[Deadline], llm: BaseLLM | None = None) -> str:
    now = datetime.now(KST)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    def bucket(pred):
        return [d for d in deadlines if d.due and pred(d.due.astimezone(KST).date())]

    due_today = bucket(lambda dt: dt == today)
    due_tomorrow = bucket(lambda dt: dt == tomorrow)
    overdue_unsub = [
        d for d in deadlines
        if d.due and d.due.astimezone(KST).date() < today and d.submitted is False
    ]

    parts = [f"📅 {today:%Y-%m-%d} 마감 브리핑\n"]
    parts.append(_section("⏰ 오늘 마감", due_today))
    parts.append(_section("🔜 내일 마감", due_tomorrow))
    if overdue_unsub:
        parts.append(_section("⚠️ 기한 지난 미제출", overdue_unsub))
    text = "\n".join(p for p in parts if p)

    if llm and llm.available and (due_today or due_tomorrow or overdue_unsub):
        phrased = llm.generate(
            prompt=PHRASE_RULES + "\n\n[정리해서 전달할 내용]\n" + text +
                   "\n\n위 내용을 학생에게 알려주는 친근한 한국어 브리핑 3~4문장으로 만들어줘.",
            system="너는 학생의 과제 마감을 챙겨주는 비서다. 주어진 사실만 전달한다.",
        )
        if phrased:
            return phrased
    return text


# LLM 이 날짜·숫자를 멋대로 바꾸지 못하게 하는 공통 규칙
PHRASE_RULES = (
    "규칙: 각 항목의 '마감'과 '남은일수'는 주어진 값만 그대로 써라. "
    "'과제명'은 「」 안의 글자 그대로 부르고, 그 안의 괄호 숫자를 남은 기간으로 착각하지 마라. "
    "항목을 새로 만들거나 빠뜨리지 말고, 날짜를 스스로 계산하지 마라."
)


def _fact_for_llm(dl: Deadline) -> str:
    """LLM 에게 줄 모호함 없는 한 줄. 제목을 「」로 감싸 이름임을 명시."""
    if dl.due:
        local = dl.due.astimezone(KST)
        when = local.strftime("%m월 %d일") + ("" if dl.time_known else "(시각미정)")
        if dl.time_known:
            when = local.strftime("%m월 %d일 %H:%M")
        d = dl.days_left
        if d is not None:
            di = int(d)
            left = "오늘 마감" if di == 0 else (f"{di}일 남음" if di > 0 else f"{-di}일 지남")
        else:
            left = ""
    else:
        when, left = "마감 미정", ""
    sub = " · 제출완료" if dl.submitted is True else (" · 미제출" if dl.submitted is False else "")
    kind = {"assign": "과제", "quiz": "퀴즈", "video": "영상", "lesson": "강의"}.get(dl.kind, dl.kind)
    return f"- 마감 {when}({left}) · {kind} · 강좌 {dl.course} · 과제명 「{dl.title}」{sub}"


def _section(title: str, items: list[Deadline]) -> str:
    if not items:
        return ""
    body = "\n".join(_fmt(d) for d in sorted(items, key=lambda x: x.due))
    return f"{title}\n{body}\n"


# --------------------------------------------------------------------- #
# 2) 자연어 질문 응답
# --------------------------------------------------------------------- #
def answer_question(question: str, deadlines: list[Deadline], llm: BaseLLM | None = None) -> str:
    # 1) 선별은 항상 규칙으로 (날짜/조건 필터를 정확하게)
    sel = _select(question, deadlines)
    if not sel:
        return "해당하는 마감이 없습니다."
    facts = "\n".join(_fact_for_llm(d) for d in sel)
    # 2) LLM 이 있으면 '선별된 사실'만 자연스럽게 표현
    if llm and llm.available:
        ans = llm.generate(
            prompt=f"{PHRASE_RULES}\n\n학생 질문: {question}\n\n[답에 사용할 사실 목록]\n{facts}\n\n"
                   f"이 목록만 사용해 질문에 한국어로 자연스럽게 답해줘.",
            system="너는 학생의 과제 마감을 관리하는 비서다. 주어진 목록의 사실만 사용한다.",
        )
        if ans:
            return ans
    # 3) 폴백: 사실 목록 그대로
    return f"{len(sel)}건 찾음:\n{facts}"


def _select(question: str, deadlines: list[Deadline]) -> list[Deadline]:
    q = question.replace(" ", "")
    now = datetime.now(KST)
    today = now.date()
    sel = list(deadlines)

    if "오늘" in q:
        sel = [d for d in sel if d.due and d.due.astimezone(KST).date() == today]
    elif "내일" in q:
        tomorrow = today + timedelta(days=1)
        sel = [d for d in sel if d.due and d.due.astimezone(KST).date() == tomorrow]
    elif "이번주" in q or "금주" in q:
        end = today + timedelta(days=(6 - today.weekday()))
        sel = [d for d in sel if d.due and today <= d.due.astimezone(KST).date() <= end]

    if "미제출" in q or "안낸" in q or "안한" in q:
        sel = [d for d in sel if d.submitted is False]
    elif "제출" in q and "미제출" not in q:
        sel = [d for d in sel if d.submitted is True]

    if "과제" in q:
        sel = [d for d in sel if d.kind == "assign"]
    elif "퀴즈" in q or "시험" in q:
        sel = [d for d in sel if d.kind == "quiz"]

    # 강좌명 부분일치
    for d in deadlines:
        key = d.course.split("[")[0].replace(" ", "")
        if key and key in q:
            sel = [x for x in sel if x.course == d.course]
            break

    sel = [d for d in sel if d.due]
    sel.sort(key=lambda x: x.due)
    return sel


# --------------------------------------------------------------------- #
# 3) 과제 요약
# --------------------------------------------------------------------- #
def summarize_deadline(dl: Deadline, description: str = "", llm: BaseLLM | None = None) -> str:
    if llm and llm.available and description.strip():
        s = llm.generate(
            prompt=f"강좌: {dl.course}\n과제: {dl.title}\n설명:\n{description}\n\n"
                   f"이 과제가 무엇을 언제까지 하라는 건지 학생이 이해하기 쉽게 2~3줄 한국어로 요약해줘.",
            system="너는 과제 설명을 간결히 요약하는 조교다.",
        )
        if s:
            return s
    # 폴백: 설명 앞부분 발췌
    desc = " ".join(description.split())
    snippet = (desc[:120] + "…") if len(desc) > 120 else desc
    return snippet or "(과제 설명이 없습니다.)"
