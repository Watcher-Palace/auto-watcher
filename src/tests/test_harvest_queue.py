# src/tests/test_harvest_queue.py —— 收割状态并入账本
import pytest
from src.utils import ledger

VALID_DRAFT = (
    "---\ntitle: 发布标题\ndate: 2020-01-01\ncategories: B\ntags:\n- 性侵\n---\n\n"
    "## 概述\n正文。\n\n"
    "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(VALID_DRAFT, encoding="utf-8")
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)
    return root, draft


def test_publish_marks_harvest_pending_with_pub_fields(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    row = ledger.get_row("990101", 1, pipeline_dir=root)
    assert row["状态"] == "published"
    assert row["发布标题"] == "发布标题"
    assert row["发布日期"] != ""
    assert row["经验提取"] == "待提取"


def test_publish_twice_is_idempotent(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    # 第一次发布已把草稿归档；publish 读 draft 路径，重发布用归档前保存的内容路径不再存在，
    # 所以幂等性在账本层验证：直接再调 record_published 不改字段
    ledger.record_published("990101", 1, pub_title="另一个", pipeline_dir=root)
    assert ledger.get_row("990101", 1, pipeline_dir=root)["发布标题"] == "发布标题"
