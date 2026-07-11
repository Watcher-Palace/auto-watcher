import pytest
from datetime import date
from src.linter import lint_text

REGISTRY = {"犯罪", "性侵", "AI", "PING", "TODO"}
TODAY = date(2026, 7, 3)


def make_draft(body="", date_str="2026-06-01", categories="B", tags=("犯罪",)):
    tag_lines = "\n".join(f"- {t}" for t in tags)
    return (
        f"---\ntitle: 测试\ndate: {date_str}\ncategories: {categories}\n"
        f"tags:\n{tag_lines}\n---\n\n## 概述\n正文。\n\n"
        f"## 信息来源\n2026.06.01，来源。*标题*。https://example.com/a\n" + body
    )


def test_clean_draft_passes():
    assert lint_text(make_draft(), REGISTRY, TODAY) == []


def test_em_dash_flagged():
    v = lint_text(make_draft(body="\n他说——这样。\n"), REGISTRY, TODAY)
    assert any("破折号" in x for x in v)


def test_yulun_without_numbers_flagged():
    v = lint_text(make_draft(body="\n## 舆论\n网友纷纷表示愤怒。\n"), REGISTRY, TODAY)
    assert any("舆论" in x for x in v)


def test_yulun_with_metric_passes():
    body = "\n## 舆论\n### 微博词条\n#某某案# 访问日期：2026.6.1。阅读量：1.2亿。\n"
    assert lint_text(make_draft(body=body), REGISTRY, TODAY) == []


def test_bad_source_line_flagged():
    draft = make_draft().replace(
        "2026.06.01，来源。*标题*。https://example.com/a", "来源：某新闻网 2026年6月"
    )
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("信息来源" in x for x in v)


def test_unknown_tag_flagged():
    v = lint_text(make_draft(tags=("不存在的标签",)), REGISTRY, TODAY)
    assert any("不存在的标签" in x for x in v)


def test_standalone_qianqing_is_warning_not_error():
    # user decision 2026-07: 前情/后续 is reviewer-waivable — warn, don't block
    from src.linter import lint_warnings
    draft = make_draft(body="\n## 前情\n旧事。\n")
    assert lint_text(draft, REGISTRY, TODAY) == []
    assert any("前情" in x for x in lint_warnings(draft))


def test_future_date_flagged():
    v = lint_text(make_draft(date_str="2026-07-04"), REGISTRY, TODAY)
    assert any("未来" in x for x in v)


def test_missing_required_section_flagged():
    draft = make_draft().replace("## 概述\n正文。\n\n", "")
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("概述" in x for x in v)


def test_bad_category_flagged():
    v = lint_text(make_draft(categories="X"), REGISTRY, TODAY)
    assert any("categories" in x for x in v)


def test_date_with_time_component_flagged():
    v = lint_text(make_draft(date_str="2026-06-01 20:00:00"), REGISTRY, TODAY)
    assert any("时间" in x for x in v)


def test_empty_tags_flagged():
    # every published post carries tags; v1 drafts repeatedly shipped without
    draft = make_draft().replace("tags:\n- 犯罪\n", "tags: []\n")
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("tags" in x for x in v)


def test_publish_blocks_on_lint_failure(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(
        "---\ntitle: 测试\ndate: 2026-06-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
        "## 概述\n此事沉寂数月后——再起波澜。\n\n"
        "## 信息来源\n2026.06.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)

    from src.publisher import publish
    with pytest.raises(SystemExit) as ei:
        publish("990101", 1, "测试", draft, deploy=False)
    assert "破折号" in str(ei.value)
