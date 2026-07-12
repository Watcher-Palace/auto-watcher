import pytest
import shutil
from pathlib import Path

from src.publisher import (
    copy_draft, move_assets, read_frontmatter,
)


def test_copy_draft(tmp_path):
    src = tmp_path / "draft.md"
    src.write_text("content")
    dst = tmp_path / "out.md"
    copy_draft(src, dst)
    assert dst.read_text() == "content"


def test_move_assets_directory(tmp_path):
    assets_src = tmp_path / "src-assets"
    assets_src.mkdir()
    (assets_src / "img.jpg").write_bytes(b"data")
    assets_dst = tmp_path / "dst"
    move_assets(assets_src, assets_dst)
    assert (assets_dst / "img.jpg").exists()
    assert not assets_src.exists()


def test_move_assets_noop_if_missing(tmp_path):
    # Should not raise if source doesn't exist
    move_assets(tmp_path / "nonexistent", tmp_path / "dst")


def test_read_frontmatter_extracts_fields():
    content = "---\ntitle: 测试\ncategories: A\n---\n## 内容"
    fm = read_frontmatter(content)
    assert fm["title"] == "测试"
    assert fm["categories"] == "A"


def test_publish_finalizes_terminal_date(tmp_path, monkeypatch):
    from src.utils import ledger

    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    # minimal draft that passes the lint gate
    draft.write_text(
        "---\ntitle: 测试\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)

    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)

    assert (tmp_path / "source" / "_posts" / "990101.md").exists()
    assert (tmp_path / "_pipeline_archive" / "draft" / "990101-1-测试-v1.md").exists()
    events_archive = tmp_path / "_pipeline_archive" / "events"
    # 单事件日期收尾时 events md 不存在也不报错——目录甚至可能未被创建
    assert not events_archive.exists() or list(events_archive.iterdir()) == []


def test_publish_refuses_missing_ledger_row(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(
        "---\ntitle: 测试\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    # 注意：这里没有调用 ledger.add_event ——账本中没有该 (date, n) 行

    from src.publisher import publish
    with pytest.raises(SystemExit, match="账本中无"):
        publish("990101", 1, "测试", draft, deploy=False)
    # 预检必须在任何拷贝/构建/发布副作用之前发生
    assert not (tmp_path / "source" / "_posts" / "990101.md").exists()


def test_publish_refuses_unresolved_tag_proposal(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(
        "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
        "<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8")
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    from src.utils import ledger
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)
    from src.publisher import publish
    with pytest.raises(SystemExit, match="TAG-PROPOSAL"):
        publish("990101", 1, "测试", draft, deploy=False)
