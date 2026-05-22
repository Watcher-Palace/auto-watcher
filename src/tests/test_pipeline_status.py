import pytest
from pathlib import Path

from src.utils.pipeline import record_selected, record_aborted


def _events_dir(tmp_path: Path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    return d


# ---- record_selected ----

def test_record_selected_creates_file_if_missing(tmp_path):
    _events_dir(tmp_path)
    record_selected("260326", 3, pipeline_dir=tmp_path)
    assert (tmp_path / "events" / "260326-status.txt").read_text() == "3:selected\n"


def test_record_selected_idempotent(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:selected\n")
    record_selected("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:selected\n"


def test_record_selected_raises_if_published(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    with pytest.raises(RuntimeError, match="published"):
        record_selected("260326", 3, pipeline_dir=tmp_path)


def test_record_selected_raises_if_abort(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:abort\n")
    with pytest.raises(RuntimeError, match="abort"):
        record_selected("260326", 3, pipeline_dir=tmp_path)


def test_record_selected_keeps_other_events_sorted(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("10:published\n1:abort\n")
    record_selected("260326", 5, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == (
        "1:abort\n5:selected\n10:published\n"
    )


# ---- record_aborted ----

def test_record_aborted_creates_file_if_missing(tmp_path):
    _events_dir(tmp_path)
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (tmp_path / "events" / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_idempotent(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:abort\n")
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_overwrites_selected(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:selected\n")
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_raises_if_published(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    with pytest.raises(RuntimeError, match="published"):
        record_aborted("260326", 3, pipeline_dir=tmp_path)
