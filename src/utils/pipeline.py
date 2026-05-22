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


_STORED_STATES = ("selected", "abort", "published")


def _status_path(date_str: str, pipeline_dir: Path) -> Path:
    return pipeline_dir / "events" / f"{date_str}-status.txt"


def _read_status_entries(status_path: Path) -> dict[int, str]:
    if not status_path.exists():
        return {}
    entries: dict[int, str] = {}
    for raw in status_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        idx_str, _, state = line.partition(":")
        if not state:
            raise RuntimeError(f"Malformed status line in {status_path}: {raw!r}")
        if state not in _STORED_STATES:
            raise RuntimeError(
                f"Unknown status value in {status_path}: {raw!r} "
                f"(allowed: {', '.join(_STORED_STATES)})"
            )
        n = int(idx_str)
        if n in entries:
            raise RuntimeError(f"Duplicate event index {n} in {status_path}")
        entries[n] = state
    return entries


def _write_status_entries(status_path: Path, entries: dict[int, str]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{n}:{entries[n]}\n" for n in sorted(entries)]
    status_path.write_text("".join(lines), encoding="utf-8")


def record_selected(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = _status_path(date_str, pipeline_dir)
    entries = _read_status_entries(status_path)
    prior = entries.get(n)
    if prior == "selected":
        return
    if prior == "published":
        raise RuntimeError(
            f"Event {date_str}-{n} is already published in {status_path}; "
            "edit the sidecar by hand if you really mean to revert it."
        )
    if prior == "abort":
        raise RuntimeError(
            f"Event {date_str}-{n} is already marked abort in {status_path}; "
            "edit the sidecar by hand if you really mean to revert it."
        )
    entries[n] = "selected"
    _write_status_entries(status_path, entries)


def record_aborted(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = _status_path(date_str, pipeline_dir)
    entries = _read_status_entries(status_path)
    prior = entries.get(n)
    if prior == "abort":
        return
    if prior == "published":
        raise RuntimeError(
            f"Event {date_str}-{n} is already published in {status_path}; "
            "edit the sidecar by hand if you really mean to abort it."
        )
    entries[n] = "abort"
    _write_status_entries(status_path, entries)


def event_status(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> str:
    entries = _read_status_entries(_status_path(date_str, pipeline_dir))
    stored = entries.get(n)
    if stored == "abort":
        return "abort"
    if stored == "published":
        return "published"
    if (pipeline_dir / "review").exists() and any(
        (pipeline_dir / "review").glob(f"{date_str}-{n}-*-v*.md")
    ):
        return "reviewed"
    if (pipeline_dir / "draft").exists() and any(
        (pipeline_dir / "draft").glob(f"{date_str}-{n}-*-v*.md")
    ):
        return "drafted"
    if (pipeline_dir / "research").exists() and any(
        (pipeline_dir / "research").glob(f"{date_str}-{n}-*.md")
    ):
        return "researched"
    if stored == "selected":
        return "selected"
    return "candidate"


def event_statuses(date_str: str, pipeline_dir: Path = PIPELINE) -> dict[int, str]:
    events_file = pipeline_dir / "events" / f"{date_str}.md"
    if not events_file.exists():
        return {}
    indexes = []
    for raw in events_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\.\s", raw)
        if m:
            indexes.append(int(m.group(1)))
    return {n: event_status(date_str, n, pipeline_dir=pipeline_dir) for n in indexes}


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
