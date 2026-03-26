import pytest
from pathlib import Path
from datetime import date, timedelta

from src.utils.pipeline import (
    events_path, approved_path, research_path,
    next_draft_path, latest_draft, latest_review,
    review_path, next_review_path,
    get_event_titles, find_research_file,
    get_state, set_state, set_last_tracked_date,
    get_untracked_dates, pipeline_summary,
)

REPO = Path(__file__).parent.parent.parent.parent  # scripts/tests/utils/ → repo root


def test_events_path():
    p = events_path("260325")
    assert p == REPO / "_pipeline" / "events" / "260325.md"


def test_approved_path():
    p = approved_path("260325")
    assert p == REPO / "_pipeline" / "events" / "260325-approved.txt"


def test_research_path():
    p = research_path("260325", 1, "兰州铁路 女性事件")
    assert p.name == "260325-1-兰州铁路 女性事件.md"
    assert p.parent == REPO / "_pipeline" / "research"


def test_next_draft_path_initial(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "draft").mkdir(parents=True)
    path, v = next_draft_path("260325", 1, "兰州铁路 女性事件")
    assert v == 1
    assert path.name == "260325-1-兰州铁路 女性事件-v1.md"


def test_next_draft_path_increments(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    draft_dir = tmp_path / "_pipeline" / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "260325-1-兰州铁路 女性事件-v1.md").touch()
    path, v = next_draft_path("260325", 1, "兰州铁路 女性事件")
    assert v == 2
    assert path.name == "260325-1-兰州铁路 女性事件-v2.md"


def test_latest_draft_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "draft").mkdir(parents=True)
    assert latest_draft("260325", 1) is None


def test_latest_draft_returns_highest_version(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    d = tmp_path / "_pipeline" / "draft"
    d.mkdir(parents=True)
    (d / "260325-1-测试-v1.md").touch()
    (d / "260325-1-测试-v2.md").touch()
    path, v = latest_draft("260325", 1)
    assert v == 2
    assert "v2" in path.name


def test_review_path():
    p = review_path("260325", 1, "兰州铁路 女性事件", 2)
    assert p.name == "260325-1-兰州铁路 女性事件-v2.md"
    assert p.parent == REPO / "_pipeline" / "review"


def test_pipeline_summary_missing_subdirs(tmp_path, monkeypatch):
    # On first run, pipeline subdirs don't exist yet — must not crash
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr("src.utils.pipeline.STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    # research/, draft/, review/ intentionally absent
    result = pipeline_summary()
    assert isinstance(result, str)


def test_get_state_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.STATE_FILE", tmp_path / ".state")
    assert get_state() is None


def test_get_state_reads_date(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    state.write_text("20260325\n")
    monkeypatch.setattr("src.utils.pipeline.STATE_FILE", state)
    assert get_state() == "20260325"


def test_set_state_writes(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    monkeypatch.setattr("src.utils.pipeline.STATE_FILE", state)
    set_state("20260325")
    assert state.read_text().strip() == "20260325"


def test_set_last_tracked_date(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    monkeypatch.setattr("src.utils.pipeline.STATE_FILE", state)
    set_last_tracked_date(date(2026, 3, 25))
    assert state.read_text().strip() == "20260325"


def test_get_untracked_dates_returns_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    dates = get_untracked_dates(days=3)
    assert len(dates) == 3


def test_get_untracked_dates_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    events_dir = tmp_path / "_pipeline" / "events"
    events_dir.mkdir(parents=True)
    yesterday = (date.today() - timedelta(days=1)).strftime("%y%m%d")
    (events_dir / f"{yesterday}.md").touch()
    dates = get_untracked_dates(days=3)
    assert yesterday not in dates


def test_get_event_titles_parses_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    events_dir = tmp_path / "_pipeline" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "260325.md").write_text(
        "# Events\n\n## 1. 测试事件\n**Brief**: 描述\n\n## 2. 另一事件\n**Brief**: 描述2\n"
    )
    titles = get_event_titles("260325")
    assert titles[1] == "测试事件"
    assert titles[2] == "另一事件"


def test_find_research_file_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "research").mkdir(parents=True)
    assert find_research_file("260325", 1) is None


def test_find_research_file_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    d = tmp_path / "_pipeline" / "research"
    d.mkdir(parents=True)
    f = d / "260325-1-测试.md"
    f.touch()
    assert find_research_file("260325", 1) == f
