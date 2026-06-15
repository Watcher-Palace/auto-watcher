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
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text("---\ntitle: 测试\n---\n## 内容\n", encoding="utf-8")

    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    # isolate from the real _pipeline: stub the pipeline-mutating calls
    monkeypatch.setattr("src.publisher._post_slug", lambda d, n: d)
    monkeypatch.setattr("src.publisher.record_published", lambda d, n: None)
    calls = []
    monkeypatch.setattr(
        "src.publisher.finalize_if_terminal",
        lambda d: calls.append(d) or True,
    )

    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)

    assert calls == ["990101"]
    assert (tmp_path / "source" / "_posts" / "990101.md").exists()
