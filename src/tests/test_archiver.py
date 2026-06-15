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


from src.utils.pipeline import archive_date


def _make(p: Path, name: str, is_dir: bool = False) -> Path:
    """Create a file (or dir with one file) named `name` under directory p."""
    p.mkdir(parents=True, exist_ok=True)
    target = p / name
    if is_dir:
        target.mkdir()
        (target / "img.jpg").write_bytes(b"x")
    else:
        target.write_text("x", encoding="utf-8")
    return target


def _full_pipeline(tmp_path: Path) -> tuple[Path, Path]:
    """Return (pipeline_dir, archive_dir) with empty stage dirs created."""
    root = tmp_path / "_pipeline"
    archive = tmp_path / "_pipeline_archive"
    for sub in ("events", "research", "draft", "review"):
        (root / sub).mkdir(parents=True)
    return root, archive


def test_archive_date_moves_all_per_date_files(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")
    _make(root / "events", "260601-status.txt")
    _make(root / "research", "260601-1-标题.md")
    _make(root / "draft", "260601-1-标题-v1.md")
    _make(root / "draft", "260601-1-assets", is_dir=True)
    _make(root / "review", "260601-1-标题-v1.md")

    moved = archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert len(moved) == 6
    assert (archive / "events" / "260601.md").exists()
    assert (archive / "events" / "260601-status.txt").exists()
    assert (archive / "research" / "260601-1-标题.md").exists()
    assert (archive / "draft" / "260601-1-标题-v1.md").exists()
    assert (archive / "draft" / "260601-1-assets" / "img.jpg").exists()
    assert (archive / "review" / "260601-1-标题-v1.md").exists()
    # originals gone
    assert not (root / "events" / "260601.md").exists()
    assert not (root / "draft" / "260601-1-assets").exists()


def test_archive_date_leaves_other_dates_untouched(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")
    _make(root / "events", "260602.md")
    _make(root / "draft", "260602-1-x-v1.md")

    archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert (root / "events" / "260602.md").exists()
    assert (root / "draft" / "260602-1-x-v1.md").exists()
    assert not (archive / "events" / "260602.md").exists()


def test_archive_date_is_idempotent(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")

    first = archive_date("260601", pipeline_dir=root, archive_dir=archive)
    second = archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert len(first) == 1
    assert second == []  # nothing left to move
    assert (archive / "events" / "260601.md").exists()


from src.utils.pipeline import finalize_if_terminal


def test_finalize_if_terminal_archives_and_marks_done(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n", encoding="utf-8")
    _make(root / "events", "260601.md")
    (root / "events" / "260601.md").write_text(
        "## 1. 标题1\n**Brief**: x", encoding="utf-8"
    )
    (root / "events" / "260601-status.txt").write_text("1:published\n", encoding="utf-8")

    result = finalize_if_terminal("260601", pipeline_dir=root, archive_dir=archive)

    assert result is True
    assert "260601" in _read_done_dates(pipeline_dir=root)
    assert (archive / "events" / "260601.md").exists()
    assert not (root / "events" / "260601.md").exists()


def test_finalize_if_terminal_noop_when_not_terminal(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n", encoding="utf-8")
    (root / "events" / "260601.md").write_text(
        "## 1. 标题1\n## 2. 标题2", encoding="utf-8"
    )
    (root / "events" / "260601-status.txt").write_text("1:published\n", encoding="utf-8")

    result = finalize_if_terminal("260601", pipeline_dir=root, archive_dir=archive)

    assert result is False
    assert "260601" not in _read_done_dates(pipeline_dir=root)
    assert (root / "events" / "260601.md").exists()  # not moved
