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
