from __future__ import annotations
import re
from pathlib import Path
from datetime import date, timedelta

REPO_ROOT = Path(__file__).parent.parent.parent
PIPELINE = REPO_ROOT / "_pipeline"
STATE_FILE = PIPELINE / ".state"


def events_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}.md"


def approved_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}-approved.txt"


def research_path(date_str: str, n: int, title: str) -> Path:
    return PIPELINE / "research" / f"{date_str}-{n}-{title}.md"


def find_research_file(date_str: str, n: int) -> Path | None:
    d = PIPELINE / "research"
    if not d.exists():
        return None
    matches = list(d.glob(f"{date_str}-{n}-*.md"))
    return matches[0] if matches else None


def next_draft_path(date_str: str, n: int, title: str) -> tuple[Path, int]:
    # Raw title — matches existing file convention (e.g. 260325-1-兰州铁路…-v1.md)
    existing = sorted((PIPELINE / "draft").glob(f"{date_str}-{n}-{title}-v*.md"))
    v = len(existing) + 1
    return PIPELINE / "draft" / f"{date_str}-{n}-{title}-v{v}.md", v


def latest_draft(date_str: str, n: int) -> tuple[Path, int] | None:
    d = PIPELINE / "draft"
    if not d.exists():
        return None
    matches = sorted(d.glob(f"{date_str}-{n}-*-v*.md"))
    if not matches:
        return None
    p = matches[-1]
    v = int(p.stem.rsplit("-v", 1)[-1])
    return p, v


def review_path(date_str: str, n: int, title: str, v: int) -> Path:
    return PIPELINE / "review" / f"{date_str}-{n}-{title}-v{v}.md"


def next_review_path(date_str: str, n: int) -> tuple[Path, int] | None:
    draft = latest_draft(date_str, n)
    if not draft:
        return None
    draft_path, v = draft
    title = draft_path.stem.rsplit("-v", 1)[0].split(f"{date_str}-{n}-", 1)[-1]
    return PIPELINE / "review" / f"{date_str}-{n}-{title}-v{v}.md", v


def latest_review(date_str: str, n: int) -> tuple[Path, int] | None:
    d = PIPELINE / "review"
    if not d.exists():
        return None
    matches = sorted(d.glob(f"{date_str}-{n}-*-v*.md"))
    if not matches:
        return None
    p = matches[-1]
    v = int(p.stem.rsplit("-v", 1)[-1])
    return p, v


def get_event_titles(date_str: str) -> dict[int, str]:
    p = events_path(date_str)
    if not p.exists():
        return {}
    content = p.read_text(encoding="utf-8")
    titles = {}
    for m in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
        titles[int(m.group(1))] = m.group(2).strip()
    return titles


def get_state() -> str | None:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip() or None
    return None


def set_state(date_yyyymmdd: str) -> None:
    STATE_FILE.write_text(date_yyyymmdd + "\n")


def set_last_tracked_date(d: date) -> None:
    set_state(d.strftime("%Y%m%d"))


def get_untracked_dates(days: int = 7) -> list[str]:
    today = date.today()
    result = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        yymmdd = d.strftime("%y%m%d")
        if not events_path(yymmdd).exists():
            result.append(yymmdd)
    return result


def pipeline_summary() -> str:
    state = get_state()
    untracked = get_untracked_dates()
    lines = [f"Last tracked: {state or 'never'}"]
    if untracked:
        lines.append(f"Untracked dates (last 7 days): {', '.join(untracked)}")
    else:
        lines.append("All dates tracked (last 7 days)")

    def _count(subdir: str) -> int:
        d = PIPELINE / subdir
        return len(list(d.glob("*.md"))) if d.exists() else 0

    lines.append(
        f"Pipeline: {_count('research')} research, "
        f"{_count('draft')} drafts, {_count('review')} reviews"
    )
    return "\n".join(lines)
