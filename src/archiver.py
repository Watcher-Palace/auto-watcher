from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import (
    PIPELINE, ARCHIVE,
    archive_date, finalize_if_terminal, _read_done_dates,
)


def backfill(pipeline_dir: Path = PIPELINE, archive_dir: Path = ARCHIVE) -> None:
    """Archive every date already listed in done-dates.txt (idempotent)."""
    for d in sorted(_read_done_dates(pipeline_dir)):
        moved = archive_date(d, pipeline_dir=pipeline_dir, archive_dir=archive_dir)
        print(f"{d}: archived {len(moved)} file(s)" if moved
              else f"{d}: nothing to archive")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python src/archiver.py <YYMMDD> | --backfill")
        return 1
    if argv[0] == "--backfill":
        backfill(PIPELINE, ARCHIVE)
        return 0
    date_str = argv[0]
    if finalize_if_terminal(date_str, PIPELINE, ARCHIVE):
        print(f"{date_str}: complete → archived to _pipeline_archive/")
    else:
        print(f"{date_str}: not fully terminal — nothing archived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
