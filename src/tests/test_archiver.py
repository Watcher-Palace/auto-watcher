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
