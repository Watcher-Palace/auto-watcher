import pytest

VALID_DRAFT = (
    "---\ntitle: 测试\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
    "## 概述\n正文。\n\n"
    "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(VALID_DRAFT, encoding="utf-8")
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher._post_slug", lambda d, n: d)
    monkeypatch.setattr("src.publisher.record_published", lambda d, n: None)
    monkeypatch.setattr("src.publisher.finalize_if_terminal", lambda d: False)
    return root, draft


def test_publish_appends_to_harvest_queue(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    assert (root / "harvest-queue.txt").read_text(encoding="utf-8") == "990101-1\n"


def test_publish_does_not_duplicate_queue_entry(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    publish("990101", 1, "测试", draft, deploy=False)
    assert (root / "harvest-queue.txt").read_text(encoding="utf-8") == "990101-1\n"
