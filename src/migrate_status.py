"""One-shot migration: merge YYMMDD-approved.txt into YYMMDD-status.txt and rename aborted→abort.

Run from repo root: `src/venv/bin/python src/migrate_status.py`

Deleted in the same commit that lands the migrated sidecars.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVENTS_DIR = REPO_ROOT / "_pipeline" / "events"

STORED = ("selected", "abort", "published")
# Precedence for conflict resolution (higher value wins).
PRECEDENCE = {"abort": 3, "published": 2, "selected": 1}


def parse_status_file(path: Path) -> dict[int, str]:
    entries: dict[int, str] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        idx_str, _, state = line.partition(":")
        if not state:
            raise RuntimeError(f"Malformed line in {path}: {raw!r}")
        if state == "aborted":
            state = "abort"
        if state not in STORED:
            raise RuntimeError(f"Unknown state {state!r} in {path}: {raw!r}")
        entries[int(idx_str)] = state
    return entries


def parse_approved_file(path: Path) -> list[int]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        out.append(int(line))
    return out


def merge(status_entries: dict[int, str], approved_indexes: list[int]) -> dict[int, str]:
    merged = dict(status_entries)
    for n in approved_indexes:
        existing = merged.get(n)
        if existing is None:
            merged[n] = "selected"
            continue
        if PRECEDENCE[existing] >= PRECEDENCE["selected"]:
            print(f"  conflict on {n}: keeping {existing!r} over selected")
            continue
        merged[n] = "selected"
    return merged


def write_status(path: Path, entries: dict[int, str]) -> None:
    if not entries:
        if path.exists():
            path.unlink()
        return
    lines = [f"{n}:{entries[n]}\n" for n in sorted(entries)]
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    if not EVENTS_DIR.exists():
        print(f"No events dir at {EVENTS_DIR}", file=sys.stderr)
        return 1
    dates = sorted({p.stem for p in EVENTS_DIR.glob("*.md")})
    print(f"Found {len(dates)} tracked dates: {', '.join(dates)}")
    for date_str in dates:
        status_path = EVENTS_DIR / f"{date_str}-status.txt"
        approved_path = EVENTS_DIR / f"{date_str}-approved.txt"
        if not status_path.exists() and not approved_path.exists():
            continue
        status_entries = parse_status_file(status_path)
        approved_indexes = parse_approved_file(approved_path)
        merged = merge(status_entries, approved_indexes)
        print(f"  {date_str}: {merged}")
        write_status(status_path, merged)
        if approved_path.exists():
            approved_path.unlink()
            print(f"  removed {approved_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
