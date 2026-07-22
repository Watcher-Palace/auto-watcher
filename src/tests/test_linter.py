import pytest
from datetime import date
from src.linter import lint_text

REGISTRY = {"犯罪", "性侵", "AI", "PING", "TODO"}
TODAY = date(2026, 7, 3)


def make_draft(body="", date_str="2026-06-01", categories="B", tags=("性侵",)):
    tag_lines = "\n".join(f"- {t}" for t in tags)
    return (
        f"---\ntitle: 测试\ndate: {date_str}\ncategories: {categories}\n"
        f"tags:\n{tag_lines}\n---\n\n"
        f"## 概述\n正文。<font color=\"blue\">2026年6月1日通报</font>\n\n"
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


def test_standalone_qianqing_is_legal():
    # user decision 2026-07-19: standalone 前情/后续 are legal per template — no warning
    from src.linter import lint_warnings
    draft = make_draft(body="\n## 前情\n旧事。\n")
    assert lint_text(draft, REGISTRY, TODAY) == []
    assert lint_warnings(draft) == []


def test_future_date_flagged():
    v = lint_text(make_draft(date_str="2026-07-04"), REGISTRY, TODAY)
    assert any("未来" in x for x in v)


def test_missing_required_section_flagged():
    draft = make_draft().replace(
        "## 概述\n正文。<font color=\"blue\">2026年6月1日通报</font>\n\n", ""
    )
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
    draft = make_draft().replace("tags:\n- 性侵\n", "tags: []\n")
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("tags" in x for x in v)


def test_publish_blocks_on_lint_failure(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(
        "---\ntitle: 测试\ndate: 2026-06-01\ncategories: B\ntags:\n- 性侵\n---\n\n"
        "## 概述\n此事沉寂数月后——再起波澜。\n\n"
        "## 信息来源\n2026.06.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    from src.utils import ledger
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)

    from src.publisher import publish
    with pytest.raises(SystemExit) as ei:
        publish("990101", 1, "测试", draft, deploy=False)
    assert "破折号" in str(ei.value)


from datetime import date as _date

BASE = (
    "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:{TAGS}\n---\n\n"
    "{BODY}## 概述\n正文。\n\n"
    "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n"
)


def test_empty_tags_with_proposal_passes():
    content = BASE.format(TAGS=" []", BODY="<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n\n")
    assert not [v for v in lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
                if "tags" in v]


def test_empty_tags_without_proposal_fails():
    content = BASE.format(TAGS=" []", BODY="")
    assert any("tags" in v for v in lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2)))


def test_unregistered_tag_still_fails_even_with_proposal():
    content = BASE.format(TAGS="\n- 未注册", BODY="<!-- [TAG-PROPOSAL]: x — y -->\n\n")
    assert any("未注册" in v for v in lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2)))


def test_em_dash_only_in_html_comment_not_flagged():
    # TAG-PROPOSAL's em dash (标签名 — 理由) lives in an HTML comment, not prose —
    # it must not trip the 破折号 style rule.
    content = BASE.format(TAGS="\n- 性侵", BODY="<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n\n")
    v = lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
    assert not any("破折号" in x for x in v)


def test_em_dash_in_prose_outside_comment_still_flagged():
    content = BASE.format(TAGS="\n- 性侵", BODY="他说——这样。\n\n")
    v = lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
    assert any("破折号" in x for x in v)


def test_crime_tag_without_charge_flagged():
    # user decision 2026-07-20: 犯罪 tag must be paired with a concrete charge,
    # or with 未立案 / 罪名未公开 explaining why there is none.
    v = lint_text(make_draft(tags=("犯罪", "性侵")), REGISTRY | {"犯罪"}, TODAY)
    assert any("具体罪名" in x for x in v)


def test_crime_tag_with_charge_passes():
    v = lint_text(make_draft(tags=("犯罪", "强奸罪")), REGISTRY | {"犯罪", "强奸罪"}, TODAY)
    assert v == []


def test_crime_tag_with_gap_tag_passes():
    v = lint_text(make_draft(tags=("犯罪", "未立案")), REGISTRY | {"犯罪", "未立案"}, TODAY)
    assert v == []


# --- 资产引用（用户裁定 2026-07-21：附件要配套 lint） ---

from src.linter import lint_assets


def _write_draft(tmp_path, body, name="260716-5-测试案-v1.md"):
    d = tmp_path / "draft"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text(make_draft(body=body), encoding="utf-8")
    return p


def test_asset_reference_without_file_flagged(tmp_path):
    body = '\n<img src="{% asset_path 260716-5-通报.jpg %}" width="300" alt="通报">\n'
    p = _write_draft(tmp_path, body)
    violations, _ = lint_assets(p, p.read_text(encoding="utf-8"))
    assert any("260716-5-通报.jpg" in v for v in violations)


def test_asset_reference_with_file_passes(tmp_path):
    body = '\n<img src="{% asset_path 260716-5-通报.jpg %}" width="300" alt="通报">\n'
    p = _write_draft(tmp_path, body)
    assets = p.parent / "260716-5-assets"
    assets.mkdir()
    (assets / "260716-5-通报.jpg").write_bytes(b"x")
    violations, _ = lint_assets(p, p.read_text(encoding="utf-8"))
    assert violations == []


def test_unreferenced_asset_warns(tmp_path):
    p = _write_draft(tmp_path, "")
    assets = p.parent / "260716-5-assets"
    assets.mkdir()
    (assets / "260716-5-未用.jpg").write_bytes(b"x")
    violations, warnings = lint_assets(p, p.read_text(encoding="utf-8"))
    assert violations == []
    assert any("260716-5-未用.jpg" in w for w in warnings)


def test_published_post_asset_dir_resolved(tmp_path):
    posts = tmp_path / "_posts"
    posts.mkdir()
    p = posts / "260716-5.md"
    body = '\n<img src="{% asset_path 260716-5-通报.jpg %}" width="300" alt="通报">\n'
    p.write_text(make_draft(body=body), encoding="utf-8")
    (posts / "260716-5").mkdir()
    (posts / "260716-5" / "260716-5-通报.jpg").write_bytes(b"x")
    violations, _ = lint_assets(p, p.read_text(encoding="utf-8"))
    assert violations == []


# --- C3：填充语 / 蓝字进展 / 标题舆论反应词 / 标题与内部标签同（审计裁定 2026-07-22） ---

from src.linter import lint_warnings, lint_slug_title


def _doc(body, title="独立成文的标题", cats="B", tags="- 犯罪\n- 未立案"):
    return f"---\ntitle: {title}\ndate: 2026-01-01\ncategories: {cats}\ntags:\n{tags}\n---\n{body}"


BODY_OK = "## 概述\nx<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.1.1，来源。*题*。https://a/\n"


def test_filler_phrases_fail():
    vs = lint_text(_doc(BODY_OK.replace("x", "此事沉寂数月后，")), None, date(2099, 1, 1))
    assert any("填充语" in v for v in vs)


def test_blue_font_exactly_one():
    no_blue = lint_text(_doc(BODY_OK.replace('<font color="blue">2026年1月1日判决</font>', "")), None, date(2099, 1, 1))
    two_blue = lint_text(_doc(BODY_OK + '<font color="blue">又一进展</font>'), None, date(2099, 1, 1))
    stale = lint_text(_doc(BODY_OK.replace("2026年1月1日判决", "截至目前暂无进展")), None, date(2099, 1, 1))
    assert any("蓝" in v for v in no_blue) and any("蓝" in v for v in two_blue) and any("蓝" in v for v in stale)


def test_title_opinion_words_warn():
    ws = lint_warnings(_doc(BODY_OK, title="某案宣判引发关注"))
    assert any("舆论反应词" in w for w in ws)


def test_opinion_filler_warn_not_fail():
    content = _doc(BODY_OK.replace("x", "该事件引发广泛关注。"))
    assert not any("填充语" in v for v in lint_text(content, None, date(2099, 1, 1)))
    assert any("舆论" in w for w in lint_warnings(content))


def test_title_equals_slug_fails(tmp_path):
    d = tmp_path / "draft"; d.mkdir()
    p = d / "990101-1-内部标签-v1.md"
    p.write_text(_doc(BODY_OK, title="内部标签"), encoding="utf-8")
    assert any("内部索引标签" in v for v in lint_slug_title(p, "内部标签"))
