import pytest
import shutil
from pathlib import Path

from scripts.publisher import (
    copy_draft, move_assets, read_frontmatter,
    calendar_color, inject_calendar_entry,
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


def test_calendar_color_categories():
    assert calendar_color("A") == "red"
    assert calendar_color("B") == "yellow"
    assert calendar_color("C") == "orange"
    assert calendar_color("D") == "orange"
    assert calendar_color("N") == "black"


def test_inject_calendar_entry_inserts_link(tmp_path):
    index = tmp_path / "index.md"
    index.write_text(
        "## 2026年三月\n<td>25</td>\n",
        encoding="utf-8",
    )
    inject_calendar_entry(
        index_path=index,
        date_str="260325",
        title="测试事件",
        category="A",
        post_slug="260325",
    )
    content = index.read_text(encoding="utf-8")
    assert "260325" in content
    assert "测试" in content
    assert "red" in content


def test_inject_calendar_entry_appends_to_existing_cell(tmp_path):
    index = tmp_path / "index.md"
    index.write_text(
        '## 2026年三月\n<td>25<br>\n<a href="old">old</a>\n</td>\n',
        encoding="utf-8",
    )
    inject_calendar_entry(
        index_path=index,
        date_str="260325",
        title="新事件",
        category="B",
        post_slug="260325-new",
    )
    content = index.read_text(encoding="utf-8")
    assert "old" in content
    assert "新" in content
