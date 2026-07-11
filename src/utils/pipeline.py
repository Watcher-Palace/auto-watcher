from __future__ import annotations
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PIPELINE = REPO_ROOT / "_pipeline"
ARCHIVE = REPO_ROOT / "_pipeline_archive"


def events_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}.md"


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
