"""CLI 진입점.

하위 명령:
  list      마감 목록 표 (기본)
  digest    오늘/내일 마감 브리핑
  ask "..."  자연어 질문
  summary   과제 요약 (정밀 모드 필요)
"""

from __future__ import annotations

import argparse
from datetime import timedelta, timezone

from rich.console import Console
from rich.table import Table

from .aggregate import collect_deadlines, upcoming_sorted
from .assistant import answer_question, build_digest, summarize_deadline
from .client import EcampusClient
from .config import Config
from .llm import get_llm

KST = timezone(timedelta(hours=9))
console = Console()


def _fmt(dl, tz=KST) -> str:
    if dl.due is None:
        return "-"
    local = dl.due.astimezone(tz)
    if not dl.time_known:
        return local.strftime("%m/%d(%a) ~마감")
    return local.strftime("%m/%d(%a) %H:%M")


def _sub(dl) -> str:
    if dl.submitted is True:
        return "[green]제출✓[/green]"
    if dl.submitted is False:
        return "[red]미제출[/red]"
    return "[dim]-[/dim]"


def _load(args) -> tuple[Config, list]:
    cfg = Config.load()
    client = EcampusClient(cfg)
    use_login = cfg.has_login
    verbose = getattr(args, "verbose", False)
    if use_login:
        try:
            with console.status("[cyan]로그인 중..."):
                client.login(force=getattr(args, "relogin", False))
            if verbose:
                console.print(f"[green]✓ 로그인 성공[/green] ({cfg.username})")
        except Exception as e:
            console.print(f"[red]✗ 로그인 실패:[/red] {e}")
            console.print("[dim]  아이디/비밀번호 확인, 또는 SSO 전용 계정인지 확인하세요. "
                          "iCal 모드로 대체합니다.[/dim]")
            use_login = False
    prog = (lambda m: console.print(f"[dim]{m}[/dim]")) if verbose else None
    with console.status("[cyan]마감일 수집 중..."):
        deadlines = collect_deadlines(client, ical_url=cfg.ical_url, scrape=use_login,
                                      progress=prog)
    return cfg, deadlines


def cmd_list(args) -> None:
    cfg, deadlines = _load(args)
    upcoming = upcoming_sorted(
        deadlines, include_overdue=args.all,
        within_days=None if args.all else args.days,
    )
    mode = "정밀(로그인)" if cfg.has_login else "iCal(시각 근사)"
    n_courses = len({d.course for d in deadlines if d.course})
    console.print(f"\n[bold]강좌[/bold] {n_courses}개 · [bold]마감[/bold] {len(deadlines)}건 "
                  f"· 모드: {mode}\n")

    table = Table(header_style="bold magenta")
    for col, kw in [("마감", {"style": "yellow", "no_wrap": True}), ("D-", {"justify": "right"}),
                    ("종류", {}), ("제출", {}), ("제목", {}), ("강좌", {"style": "dim"})]:
        table.add_column(col, **kw)
    for dl in upcoming:
        d = dl.days_left
        dcol = f"D{int(d):+d}" if d is not None else "-"
        style = "red" if d is not None and d < 2 else ""
        table.add_row(_fmt(dl), f"[{style}]{dcol}[/{style}]" if style else dcol,
                      dl.kind, _sub(dl), dl.title, dl.course or "")
    if upcoming:
        console.print(table)
        if not cfg.has_login:
            console.print("\n[dim]※ iCal 모드는 마감 시각이 근사값입니다. .env 에 로그인 정보를 "
                          "넣으면 정확한 시각·제출여부가 표시됩니다.[/dim]")
    else:
        console.print("[dim]표시할 예정 마감이 없습니다. --all 로 지난 마감도 확인하세요.[/dim]")


def cmd_digest(args) -> None:
    cfg, deadlines = _load(args)
    llm = get_llm()
    console.print(f"[dim](AI: {llm.name})[/dim]\n")
    console.print(build_digest(deadlines, llm=llm))


def cmd_ask(args) -> None:
    cfg, deadlines = _load(args)
    llm = get_llm()
    question = " ".join(args.question)
    console.print(f"[dim](AI: {llm.name}) 질문: {question}[/dim]\n")
    console.print(answer_question(question, deadlines, llm=llm))


def cmd_summary(args) -> None:
    cfg, deadlines = _load(args)
    if not cfg.has_login:
        console.print("[yellow]과제 요약은 정밀 모드(로그인)가 필요합니다. .env 에 로그인 정보를 넣어주세요.[/yellow]")
        return
    llm = get_llm()
    console.print(f"[dim](AI: {llm.name})[/dim]")
    upcoming = upcoming_sorted(deadlines, within_days=args.days)
    for dl in upcoming:
        if dl.kind not in ("assign", "quiz"):
            continue
        console.print(f"\n[bold yellow]{_fmt(dl)}[/bold yellow]  [bold]{dl.title}[/bold] "
                      f"[dim]({dl.course})[/dim]")
        console.print("  " + summarize_deadline(dl, dl.description, llm=llm).replace("\n", "\n  "))


def main() -> None:
    ap = argparse.ArgumentParser(prog="elearning", description="강남대 이러닝 과제·마감일 에이전트")
    ap.add_argument("--relogin", action="store_true", help="세션 캐시 무시하고 재로그인")
    ap.add_argument("-v", "--verbose", action="store_true", help="진행상황 자세히 출력")
    sub = ap.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="마감 목록 표 (기본)")
    p_list.add_argument("--days", type=float, default=14)
    p_list.add_argument("--all", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_dig = sub.add_parser("digest", help="오늘/내일 마감 브리핑")
    p_dig.set_defaults(func=cmd_digest)

    p_ask = sub.add_parser("ask", help="자연어 질문")
    p_ask.add_argument("question", nargs="+")
    p_ask.set_defaults(func=cmd_ask)

    p_sum = sub.add_parser("summary", help="과제 AI 요약 (정밀 모드)")
    p_sum.add_argument("--days", type=float, default=14)
    p_sum.set_defaults(func=cmd_summary)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        # 기본: list
        args.days = 14
        args.all = False
        cmd_list(args)
        return
    args.func(args)


if __name__ == "__main__":
    main()
