import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import pipeline as pl
from src import publisher


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PIPELINE", tmp_path)
    for d in ("review", "draft"):
        (tmp_path / d).mkdir()


def _write_review(tmp_path, disposition):
    (tmp_path / "draft" / "260701-1-t-v1.md").write_text("x", encoding="utf-8")
    (tmp_path / "review" / "260701-1-t-v1.md").write_text(
        f"STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n处理：{disposition}\n",
        encoding="utf-8")


def test_no_review_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    publisher.check_review_resolved("260701", 1)  # no raise


def test_empty_disposition_blocks(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "")
    with pytest.raises(SystemExit):
        publisher.check_review_resolved("260701", 1)


def test_unresolved_blocks(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "未解决：无裁定")
    with pytest.raises(SystemExit):
        publisher.check_review_resolved("260701", 1)


def test_resolved_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "已修改")
    publisher.check_review_resolved("260701", 1)  # no raise


def test_comment_marker_regex():
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [USER]: keep -->")
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [REVIEWER]: fix -->")
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [WRITER-REJECTED]: no -->")
    assert not publisher.PIPELINE_COMMENT_RE.search("<!-- [TAG-PROPOSAL]: x -->")
    assert not publisher.PIPELINE_COMMENT_RE.search("正文没有注释")


def _write_good_draft(path: Path) -> None:
    path.write_text(
        "---\ntitle: 测试\ndate: 2020-01-01\ncategories: B\ntags:\n- 性侵\n---\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8",
    )


def _setup_publish_env(tmp_path, monkeypatch):
    """完整 publish() 环境：与 test_publisher.py 中的模式一致。"""
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "review").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    return root


def test_publish_blocked_by_unresolved_review_disposition(tmp_path, monkeypatch):
    """驱动 publisher.py:91-94 的预检接线：publish() 应在评审 处理 为空时拒绝发布。"""
    root = _setup_publish_env(tmp_path, monkeypatch)
    draft = root / "draft" / "990101-1-测试-v1.md"
    _write_good_draft(draft)
    (root / "review" / "990101-1-测试-v1.md").write_text(
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n处理：\n",
        encoding="utf-8")
    from src.utils import ledger
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)

    from src.publisher import publish
    with pytest.raises(SystemExit, match="未完全处置"):
        publish("990101", 1, "测试", draft, deploy=False)
    assert not (tmp_path / "source" / "_posts" / "990101.md").exists()


def test_publish_proceeds_past_preflight_with_clean_review(tmp_path, monkeypatch):
    """STATUS: CLEAN（无问题项）+ 草稿无残留流程注释：预检不得阻断 publish()。"""
    root = _setup_publish_env(tmp_path, monkeypatch)
    draft = root / "draft" / "990101-1-测试-v1.md"
    _write_good_draft(draft)
    (root / "review" / "990101-1-测试-v1.md").write_text("STATUS: CLEAN\n", encoding="utf-8")
    from src.utils import ledger
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)

    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)  # must not raise

    assert (tmp_path / "source" / "_posts" / "990101.md").exists()


def test_todo_tag_blocks():
    with pytest.raises(SystemExit):
        publisher.check_todo_tag(["犯罪", "TODO"], allow_todo=False)


def test_todo_tag_allowed_with_flag():
    publisher.check_todo_tag(["犯罪", "TODO"], allow_todo=True)  # no raise


def test_ping_tag_does_not_block():
    publisher.check_todo_tag(["犯罪", "PING"], allow_todo=False)  # no raise


def test_no_tags_does_not_block():
    publisher.check_todo_tag(None, allow_todo=False)  # no raise
