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


from src.utils.pipeline import event_status, event_statuses


def _setup_pipeline(tmp_path: Path) -> Path:
    """Create a fake _pipeline structure under tmp_path. Returns pipeline_dir."""
    for sub in ("events", "research", "draft", "review"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _write_events_file(pipeline_dir: Path, date_str: str, indexes: list[int]) -> None:
    body = "\n".join(f"## {i}. 标题{i}\n**Brief**: x" for i in indexes)
    (pipeline_dir / "events" / f"{date_str}.md").write_text(body, encoding="utf-8")


# ---- event_status ----

def test_event_status_candidate_when_unknown(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [1, 3])
    assert event_status("260326", 1, pipeline_dir=pipeline) == "candidate"


def test_event_status_selected_when_sidecar_says_selected(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "selected"


def test_event_status_researched_when_research_file_exists(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "researched"


def test_event_status_drafted_overrides_researched(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "drafted"


def test_event_status_reviewed_overrides_drafted(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "reviewed"


def test_event_status_published_overrides_review_files(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:published\n")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "published"


def test_event_status_abort_overrides_everything(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:abort\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "abort"


# ---- event_statuses ----

def test_event_statuses_returns_all_indexes_from_events_file(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [1, 3, 7])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n7:published\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    result = event_statuses("260326", pipeline_dir=pipeline)
    assert result == {1: "candidate", 3: "researched", 7: "published"}


def test_event_statuses_empty_when_events_file_missing(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    assert event_statuses("260326", pipeline_dir=pipeline) == {}
