import pytest
from pathlib import Path

from src.utils.pipeline import (
    ARCHIVE, REPO_ROOT,
    _read_done_dates, mark_done,
)


# ---- ARCHIVE constant ----

def test_archive_constant_is_sibling_of_pipeline():
    assert ARCHIVE == REPO_ROOT / "_pipeline_archive"


# ---- done-dates helpers ----

def test_read_done_dates_skips_comments_and_blanks(tmp_path):
    (tmp_path / "done-dates.txt").write_text(
        "# header comment\n\n260501\n260502\n", encoding="utf-8"
    )
    assert _read_done_dates(pipeline_dir=tmp_path) == {"260501", "260502"}


def test_read_done_dates_missing_file_is_empty_set(tmp_path):
    assert _read_done_dates(pipeline_dir=tmp_path) == set()


def test_mark_done_appends_new_date(tmp_path):
    (tmp_path / "done-dates.txt").write_text("# header\n260501\n", encoding="utf-8")
    added = mark_done("260502", pipeline_dir=tmp_path)
    assert added is True
    assert (tmp_path / "done-dates.txt").read_text(encoding="utf-8") == (
        "# header\n260501\n260502\n"
    )


def test_mark_done_is_dedup_noop(tmp_path):
    (tmp_path / "done-dates.txt").write_text("# header\n260501\n", encoding="utf-8")
    added = mark_done("260501", pipeline_dir=tmp_path)
    assert added is False
    assert (tmp_path / "done-dates.txt").read_text(encoding="utf-8") == (
        "# header\n260501\n"
    )


from src.utils.pipeline import is_date_terminal


def _pipeline_with_events(tmp_path: Path, date_str: str, indexes: list[int]) -> Path:
    """Create events/{date}.md with the given event indexes. Returns pipeline root."""
    (tmp_path / "events").mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"## {i}. 标题{i}\n**Brief**: x" for i in indexes)
    (tmp_path / "events" / f"{date_str}.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_is_date_terminal_true_when_all_terminal(tmp_path):
    _pipeline_with_events(tmp_path, "260601", [1, 2])
    (tmp_path / "events" / "260601-status.txt").write_text(
        "1:published\n2:abort\n", encoding="utf-8"
    )
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is True


def test_is_date_terminal_false_when_one_pending(tmp_path):
    _pipeline_with_events(tmp_path, "260601", [1, 2])
    # event 2 has no terminal status → derived state "candidate"
    (tmp_path / "events" / "260601-status.txt").write_text(
        "1:published\n", encoding="utf-8"
    )
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is False


def test_is_date_terminal_false_when_events_file_missing(tmp_path):
    (tmp_path / "events").mkdir(parents=True, exist_ok=True)
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is False
