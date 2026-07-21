import pytest
from pathlib import Path
from src.utils import ledger
from src.utils.archive import archive_event, archive_date, finalize_event, sweep


def _mk(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith("/"):
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.write_text("x", encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path):
    pipe = tmp_path / "_pipeline"
    arch = tmp_path / "_pipeline_archive"
    pipe.mkdir()
    _mk(pipe, "events/990101.md")
    _mk(pipe, "research/990101-1-标题一.md")
    _mk(pipe, "draft/990101-1-标题一-v1.md")
    (pipe / "draft" / "990101-1-assets").mkdir()
    _mk(pipe, "review/990101-1-标题一-v1.md")
    _mk(pipe, "research/990101-10-十.md")     # 前缀陷阱：1 不得匹配 10
    ledger.add_event("990101", 1, "标题一", pipeline_dir=pipe)
    ledger.add_event("990101", 10, "十", pipeline_dir=pipe)
    return pipe, arch


def test_archive_event_moves_only_target_event(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    moved = archive_event("990101", 1, pipeline_dir=pipe, archive_dir=arch)
    assert (arch / "draft" / "990101-1-assets").is_dir()
    assert (arch / "review" / "990101-1-标题一-v1.md").exists()
    assert (pipe / "research" / "990101-10-十.md").exists()      # 未被误搬
    assert (pipe / "events" / "990101.md").exists()               # 共享文件不动
    assert len(moved) == 4
    assert archive_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) == []  # 幂等


def test_finalize_event_noop_when_not_terminal(env):
    pipe, arch = env
    assert finalize_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) is False
    assert (pipe / "draft" / "990101-1-标题一-v1.md").exists()


def test_finalize_event_archives_and_finalizes_date_when_all_terminal(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert finalize_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) is False
    assert (pipe / "events" / "990101.md").exists()   # 事件 10 未终态，md 保留
    ledger.record_aborted("990101", 10, pipeline_dir=pipe)
    assert finalize_event("990101", 10, pipeline_dir=pipe, archive_dir=arch) is True
    assert (arch / "events" / "990101.md").exists()   # 整日期收尾


def test_sweep_archives_all_terminal_events(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    ledger.record_aborted("990101", 10, pipeline_dir=pipe)
    moved = sweep(pipeline_dir=pipe, archive_dir=arch)
    assert (arch / "events" / "990101.md").exists()
    assert moved and not (pipe / "review" / "990101-1-标题一-v1.md").exists()


def test_assets_dir_archived_with_event(tmp_path, monkeypatch):
    """附件目录 {date}-{n}-assets/ 随事件一起归档（用户裁定 2026-07-21）。"""
    pipeline = tmp_path / "_pipeline"
    (pipeline / "draft").mkdir(parents=True)
    (pipeline / "draft" / "260716-5-测试案-v1.md").write_text("x", encoding="utf-8")
    assets = pipeline / "draft" / "260716-5-assets"
    assets.mkdir()
    (assets / "260716-5-通报.jpg").write_bytes(b"x")
    archive_dir = tmp_path / "_pipeline_archive"

    archive_event("260716", 5, pipeline, archive_dir)

    assert not assets.exists()
    assert (archive_dir / "draft" / "260716-5-assets" / "260716-5-通报.jpg").exists()
