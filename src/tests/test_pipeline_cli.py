import pytest
from src.utils import ledger
from src.pipeline_cli import main


@pytest.fixture
def pipe(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    root.mkdir()
    (tmp_path / "_pipeline_archive").mkdir()
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    return root


def test_select_and_abort_roundtrip(pipe, capsys):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    ledger.add_event("990101", 2, "二", pipeline_dir=pipe)
    assert main(["select", "990101", "1", "2"]) == 0
    assert ledger.get_row("990101", 1, pipeline_dir=pipe)["状态"] == "selected"
    assert main(["abort", "990101", "2"]) == 0
    assert ledger.get_row("990101", 2, pipeline_dir=pipe)["状态"] == "abort"


def test_add_creates_selected_row(pipe):
    assert main(["add", "990102", "1", "手工事件"]) == 0
    row = ledger.get_row("990102", 1, pipeline_dir=pipe)
    assert row["状态"] == "selected" and row["标题"] == "手工事件"


def test_status_lists_open_events_and_harvest(pipe, capsys):
    ledger.add_event("990101", 1, "进行中", pipeline_dir=pipe)
    ledger.add_event("990101", 2, "已发", pipeline_dir=pipe)
    ledger.record_published("990101", 2, pub_title="t", pipeline_dir=pipe)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "进行中" in out and "candidate" in out
    assert "已发" not in out          # 终态行不进在途表
    assert "990101-2" in out          # 待提取经验列出


def test_archive_subcommand_sweeps(pipe):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    (pipe / "draft").mkdir()
    (pipe / "draft" / "990101-1-一-v1.md").write_text("x", encoding="utf-8")
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert main(["archive"]) == 0
    assert not (pipe / "draft" / "990101-1-一-v1.md").exists()


def test_harvest_list_and_done(pipe, capsys):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert main(["harvest"]) == 0
    assert "990101-1" in capsys.readouterr().out
    assert main(["harvest", "done", "990101", "1"]) == 0
    assert ledger.pending_harvest(pipeline_dir=pipe) == []


def test_staged_subcommand_parks_draft(pipe, tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.SOURCE_DRAFTS",
                        tmp_path / "source" / "_drafts")
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    (pipe / "draft").mkdir()
    (pipe / "draft" / "990101-1-一-v1.md").write_text("x", encoding="utf-8")
    assert main(["staged", "990101", "1"]) == 0
    assert ledger.get_row("990101", 1, pipeline_dir=pipe)["状态"] == "staged"
    assert (tmp_path / "source" / "_drafts" / "990101-1-一-v1.md").exists()
    assert not (pipe / "draft" / "990101-1-一-v1.md").exists()


def test_ping_due_lists_stale_ping_posts(pipe, tmp_path, monkeypatch, capsys):
    posts = tmp_path / "posts"; posts.mkdir()
    monkeypatch.setattr("src.utils.pipeline.POSTS", posts)
    (posts / "250101.md").write_text(
        "---\ntitle: 旧案\ndate: 2025-01-01\ntags:\n- PING\n---\n", encoding="utf-8")
    (posts / "990101.md").write_text(
        "---\ntitle: 新案\ndate: 2099-01-01\ntags:\n- PING\n---\n", encoding="utf-8")
    assert main(["ping-due"]) == 0
    out = capsys.readouterr().out
    assert "旧案" in out and "新案" not in out


def test_dedup_scans_ledger_posts_research(pipe, tmp_path, monkeypatch, capsys):
    posts = tmp_path / "posts"; posts.mkdir()
    monkeypatch.setattr("src.utils.pipeline.POSTS", posts)
    (posts / "250101.md").write_text("---\ntitle: 张某案宣判\n---\n正文", encoding="utf-8")
    (pipe / "research").mkdir()
    (pipe / "research" / "990101-1-张某案.md").write_text("张某", encoding="utf-8")
    ledger.add_event("990102", 1, "李某案", pipeline_dir=pipe)
    assert main(["dedup", "张某"]) == 0
    out = capsys.readouterr().out
    assert "250101" in out and "990101-1" in out and "李某" not in out
