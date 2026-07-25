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


def test_stage_event_parks_latest_draft_and_archives_rest(tmp_path):
    from src.utils.archive import stage_event
    pipe, arch = tmp_path / "_pipeline", tmp_path / "_arch"
    drafts = tmp_path / "source" / "_drafts"
    for rel in ("draft", "research", "events"):
        (pipe / rel).mkdir(parents=True)
    (pipe / "draft" / "990101-1-题-v1.md").write_text("v1", encoding="utf-8")
    (pipe / "draft" / "990101-1-题-v2.md").write_text("v2", encoding="utf-8")
    (pipe / "draft" / "990101-1-assets").mkdir()
    (pipe / "research" / "990101-1-题.md").write_text("r", encoding="utf-8")
    (pipe / "events" / "990101.md").write_text("e", encoding="utf-8")
    ledger.add_event("990101", 1, "题", pipeline_dir=pipe)
    ledger.record_staged("990101", 1, pipeline_dir=pipe)
    parked, date_done = stage_event("990101", 1, pipeline_dir=pipe,
                                    archive_dir=arch, drafts_dir=drafts)
    assert parked == drafts / "990101-1-题-v2.md"
    assert parked.read_text(encoding="utf-8") == "v2"
    assert (arch / "draft" / "990101-1-题-v1.md").exists()
    assert (arch / "draft" / "990101-1-assets").exists()
    assert (arch / "research" / "990101-1-题.md").exists()
    assert date_done and (arch / "events" / "990101.md").exists()


def test_archive_date_merges_new_event_into_existing_archived_md(tmp_path):
    """给已归档日期补录新事件后再终态：新 ## N 段并入归档 md，live 删除（不再跳过留孤儿）。"""
    pipe = tmp_path / "_pipeline"
    arch = tmp_path / "_pipeline_archive"
    (pipe / "events").mkdir(parents=True)
    (arch / "events").mkdir(parents=True)
    # 归档里已有该日期的 events md（旧事件 1、2，日期先前已全终态收尾）
    (arch / "events" / "990101.md").write_text(
        "# Events — 9901-01\n\n## 1. 甲\n**Brief**: 甲内容\n\n"
        "## 2. 乙\n**Brief**: 乙内容\n", encoding="utf-8")
    # live 是事后补录的新事件 3
    (pipe / "events" / "990101.md").write_text(
        "# Events — 9901-01\n\n## 3. 丙\n**Brief**: 丙内容\n", encoding="utf-8")

    moved = archive_date("990101", pipeline_dir=pipe, archive_dir=arch)

    merged = (arch / "events" / "990101.md").read_text(encoding="utf-8")
    assert "## 1. 甲" in merged
    assert "## 2. 乙" in merged
    assert "## 3. 丙" in merged
    assert merged.index("## 1.") < merged.index("## 3.")     # 按事件号排序
    assert not (pipe / "events" / "990101.md").exists()       # live 不再是孤儿
    assert (arch / "events" / "990101.md") in moved


def test_archive_date_leaves_live_when_event_number_conflicts(tmp_path):
    """撞同号但正文不同＝冲突：不合并、不删 live（留人工），归档 md 不被污染。"""
    pipe = tmp_path / "_pipeline"
    arch = tmp_path / "_pipeline_archive"
    (pipe / "events").mkdir(parents=True)
    (arch / "events").mkdir(parents=True)
    (arch / "events" / "990101.md").write_text(
        "# Events — 9901-01\n\n## 1. 甲\n**Brief**: 原始甲\n", encoding="utf-8")
    (pipe / "events" / "990101.md").write_text(
        "# Events — 9901-01\n\n## 1. 甲改\n**Brief**: 冲突甲\n", encoding="utf-8")

    archive_date("990101", pipeline_dir=pipe, archive_dir=arch)

    assert (pipe / "events" / "990101.md").exists()           # live 保留给人工
    arch_txt = (arch / "events" / "990101.md").read_text(encoding="utf-8")
    assert "冲突甲" not in arch_txt and "原始甲" in arch_txt   # 归档未被污染


def test_archive_date_removes_redundant_identical_live(tmp_path):
    """live 段与归档完全一致＝冗余：删 live，归档内容不变。"""
    pipe = tmp_path / "_pipeline"
    arch = tmp_path / "_pipeline_archive"
    (pipe / "events").mkdir(parents=True)
    (arch / "events").mkdir(parents=True)
    section = "# Events — 9901-01\n\n## 1. 甲\n**Brief**: 甲内容\n"
    (arch / "events" / "990101.md").write_text(section, encoding="utf-8")
    (pipe / "events" / "990101.md").write_text(section, encoding="utf-8")

    archive_date("990101", pipeline_dir=pipe, archive_dir=arch)

    assert not (pipe / "events" / "990101.md").exists()       # 冗余 live 删除
    assert (arch / "events" / "990101.md").read_text(encoding="utf-8") == section


def test_stage_event_without_draft(tmp_path):
    from src.utils.archive import stage_event
    pipe = tmp_path / "_pipeline"
    pipe.mkdir()
    ledger.add_event("990101", 1, "题", pipeline_dir=pipe)
    ledger.record_staged("990101", 1, pipeline_dir=pipe)
    parked, date_done = stage_event("990101", 1, pipeline_dir=pipe,
                                    archive_dir=tmp_path / "_arch",
                                    drafts_dir=tmp_path / "drafts")
    assert parked is None and date_done
