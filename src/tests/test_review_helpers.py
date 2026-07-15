import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import pipeline as pl


REVIEW = """STATUS: ISSUES

## 问题 1
类型：事实
原文：`a`
处理：

## 问题 2
类型：格式
原文：`b`
处理：
"""


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PIPELINE", tmp_path)
    for d in ("review", "draft", "research"):
        (tmp_path / d).mkdir()


def test_review_fact_items(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert pl.review_fact_items("260701", 1) == []
    (tmp_path / "draft" / "260701-1-t-v1.md").write_text("x", encoding="utf-8")
    (tmp_path / "review" / "260701-1-t-v1.md").write_text(REVIEW, encoding="utf-8")
    assert pl.review_fact_items("260701", 1) == [1]


def test_research_age_days(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert pl.research_age_days("260701", 1) is None
    p = tmp_path / "research" / "260701-1-t.md"
    p.write_text("x", encoding="utf-8")
    old = time.time() - 3 * 86400
    os.utime(p, (old, old))
    assert pl.research_age_days("260701", 1) == 3
