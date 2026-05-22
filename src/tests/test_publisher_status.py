import pytest
from pathlib import Path

from src.publisher import record_published


def _events_dir(tmp_path: Path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    return d


def test_creates_file_if_missing(tmp_path):
    pipeline = tmp_path
    _events_dir(tmp_path)
    record_published("260326", 3, pipeline_dir=pipeline)
    assert (pipeline / "events" / "260326-status.txt").read_text() == "3:published\n"


def test_appends_to_existing_file(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("1:aborted\n")
    record_published("260326", 7, pipeline_dir=pipeline)
    assert (events / "260326-status.txt").read_text() == "1:aborted\n7:published\n"


def test_idempotent_on_duplicate_published(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    record_published("260326", 3, pipeline_dir=pipeline)
    assert (events / "260326-status.txt").read_text() == "3:published\n"


def test_raises_if_already_aborted(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("1:aborted\n")
    with pytest.raises(RuntimeError, match="aborted"):
        record_published("260326", 1, pipeline_dir=pipeline)


def test_ignores_blank_and_comment_lines(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("# notes\n\n3:published\n")
    record_published("260326", 3, pipeline_dir=pipeline)
    assert (events / "260326-status.txt").read_text() == "# notes\n\n3:published\n"
