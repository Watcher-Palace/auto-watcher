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
    # user decision 2026-07-19: standalone 前情/后续 are legal per template — no warning.
    # 2026-07-22 (C7): the section must carry a 站内参见 link per template format —
    # updated fixture accordingly, intent (standalone section, clean lint) unchanged.
    from src.linter import lint_warnings
    draft = make_draft(body="\n## 前情\n2026年5月1日：旧事。参见：[标题](/2026/260501/)\n")
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


def test_em_dash_in_grey_verbatim_quote_not_flagged():
    # 用户裁定 2026-08-04：破折号是文风规则，不管别人文书的原话。
    content = BASE.format(
        TAGS="\n- 性侵",
        BODY='<font color="grey">"本院认为——被告人罪行严重。"</font>\n\n')
    v = lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
    assert not any("破折号" in x for x in v)


def test_em_dash_in_source_line_title_not_flagged():
    # 官方公报标题含「——」，删副标题才能过闸口是本末倒置。
    content = (
        "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:\n- 性侵\n---\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，国家统计局。"
        "*第七次全国人口普查公报（第四号）——人口性别构成情况*。https://example.com/a\n"
    )
    v = lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
    assert not any("破折号" in x for x in v)


def test_em_dash_in_source_line_outside_title_still_flagged():
    # 豁免只覆盖 *标题* 本身，来源名等写手可控部分照旧禁用。
    content = (
        "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:\n- 性侵\n---\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，某台——某频道。*标题*。https://example.com/a\n"
    )
    v = lint_text(content, {"犯罪", "性侵"}, _date(2020, 1, 2))
    assert any("破折号" in x for x in v)


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

from src.linter import lint_warnings, lint_slug_title, TITLE_MAX_LEN


def _doc(body, title="独立成文的标题", cats="B", tags="- 犯罪\n- 未立案"):
    return f"---\ntitle: {title}\ndate: 2026-01-01\ncategories: {cats}\ntags:\n{tags}\n---\n{body}"


BODY_OK = "## 概述\nx<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.01.01，来源。*题*。https://a/\n"


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


def test_grey_quote_matches_through_speaker_prefix_in_excerpt():
    """研究文件把说话人写进引号内（`"邓煜：能与我…"`）时，草稿里同一句灰字仍应命中——
    半角引号原先没被归一化剥掉，整句因此判不命中报假 WARN（260721-3、260726-1）。"""
    from src.linter import crosscheck_research
    body = ('## 概述\n他说<font color="grey">"能与我一直敬仰的那些伟大数学家名字并列。"</font>\n'
            '<font color="blue">2026年1月1日判决</font>\n'
            '## 信息来源\n2026.01.01，来源。*题*。https://a/\n')
    research = ('## 信息来源\n- 2026.01.01，新华网。*题*。https://a/ — '
                '"邓煜：能与我一直敬仰的那些伟大数学家名字并列。""王虹：另一句。"（正文原话）\n')
    _, ws = crosscheck_research(_doc(body), research)
    assert not any("逐字命中" in w for w in ws)


def test_title_passive_warns_through_place_prefix():
    """称谓前带地名/机构限定语时不得漏报——原正则锚在 ^，"吉林女子遭…" 整条逃过
    机械闸口，260725-2 靠人工评审才发现。"""
    for t in ["女子遭前男友杀害", "吉林女子遭丈夫追打", "大连工业大学女生遭网暴"]:
        assert any("受害人被动句" in w for w in lint_warnings(_doc(BODY_OK, title=t))), t


def test_title_passive_not_warned_when_perpetrator_is_subject():
    """限定语里出现施动者称谓或加害动词时，女性称谓是宾语——那是合规标题，
    放宽前缀不能把它们连带误报。"""
    for t in ["医生猥亵女童被开除", "男子砍伤妻子被刑拘", "教师性侵女生被判刑",
              "男子持刀砍伤妻子被刑事拘留"]:
        assert not any("受害人被动句" in w for w in lint_warnings(_doc(BODY_OK, title=t))), t


def test_title_over_length_warns_but_does_not_fail():
    """用户裁定 2026-07-31：标题上限 40 字（含标点），超出只 WARN，不阻断发布。"""
    over = "男" * (TITLE_MAX_LEN + 1)
    ws = lint_warnings(_doc(BODY_OK, title=over))
    assert any(f"超过 {TITLE_MAX_LEN} 字" in w for w in ws)
    # 超长绝不能是 FAIL——publisher 靠 lint_text 的返回值拒发
    assert not any("字" in v and "标题" in v for v in lint_text(_doc(BODY_OK, title=over), None, date(2099, 1, 1)))


def test_title_at_limit_is_silent():
    at_limit = "男" * TITLE_MAX_LEN
    assert not any("超过" in w for w in lint_warnings(_doc(BODY_OK, title=at_limit)))


def test_title_equals_slug_fails(tmp_path):
    d = tmp_path / "draft"; d.mkdir()
    p = d / "990101-1-内部标签-v1.md"
    p.write_text(_doc(BODY_OK, title="内部标签"), encoding="utf-8")
    assert any("内部索引标签" in v for v in lint_slug_title(p, "内部标签"))


# --- C1：草稿 ↔ 研究文件交叉对账（审计裁定 2026-07-22） ---

from src.linter import crosscheck_research

RESEARCH = ("## 事实\n白女士报案。\n## 信息来源\n"
            "- 2026.01.01，澎湃新闻。*真标题*。https://a/b — 摘录\n")


def test_crosscheck_source_url_missing():
    draft = _doc(BODY_OK.replace("https://a/", "https://other/"))
    vs, _ = crosscheck_research(draft, RESEARCH)
    assert any("URL" in v for v in vs)


def test_crosscheck_source_title_date_mismatch():
    draft = _doc("## 概述\nx<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.01.01，澎湃新闻。*错标题*。https://a/b\n")
    vs, _ = crosscheck_research(draft, RESEARCH)
    assert any("标题" in v or "日期" in v for v in vs)


def test_crosscheck_names_warn():
    draft = _doc("## 概述\n林悦（化名）与高某某。<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.01.01，澎湃新闻。*真标题*。https://a/b\n")
    _, ws = crosscheck_research(draft, RESEARCH)
    assert any("林悦" in w for w in ws) and any("高某某" in w for w in ws)
    assert not any("白女士" in w for w in ws)


def test_crosscheck_names_no_false_positive_after_role_noun():
    # research phrases 王某某 without a preceding "人" so the literal 4-char
    # "人王某某" (NAME_RE's greedy capture including the role noun) is absent
    # from research_text even though the real name 王某某 is present.
    research = RESEARCH.replace("白女士报案。", "白女士报案。经查，嫌疑人系王某某。")
    draft = _doc("## 概述\n加害人王某某被拘留。<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.01.01，澎湃新闻。*真标题*。https://a/b\n")
    _, ws = crosscheck_research(draft, research)
    assert not any("王某某" in w for w in ws)


# --- C7：前情/后续须带站内参见链接（审计裁定 2026-07-22） ---


def test_prequel_section_requires_site_link():
    body = "## 前情\n1月1日：无链接描述。\n" + BODY_OK
    vs = lint_text(_doc(body), None, date(2099, 1, 1))
    assert any("前情" in v and "参见" in v for v in vs)


def test_prequel_with_link_ok():
    body = "## 前情\n1月1日：简述。参见：[题](/2026/260101/)\n" + BODY_OK
    vs = lint_text(_doc(body), None, date(2099, 1, 1))
    assert not any("前情" in v for v in vs)


# --- 注意力型规则的机械面（2026-08-05）：被动句标题、date≠蓝字日、灰字逐字命中 ---


def test_title_passive_subject_warns():
    from src.linter import lint_warnings
    draft = make_draft().replace("title: 测试", "title: 女子遭男同事跟踪骚扰")
    assert any("被动句" in w for w in lint_warnings(draft))


def test_title_perpetrator_bei_verdict_no_warn():
    from src.linter import lint_warnings
    draft = make_draft().replace("title: 测试", "title: 男子杀害女儿被判死刑")
    assert not any("被动句" in w for w in lint_warnings(draft))


def test_frontmatter_date_mismatch_blue_line_warns():
    from src.linter import lint_warnings
    draft = make_draft(date_str="2026-06-02")   # 蓝字行日期为 2026年6月1日
    assert any("蓝字进展所在行" in w for w in lint_warnings(draft))
    assert not any("蓝字进展所在行" in w for w in lint_warnings(make_draft()))


def test_grey_quote_must_hit_research_sources():
    from src.linter import crosscheck_research
    research = ("## 信息来源\n"
                "- 2026.06.01，来源。*标题*。https://example.com/a — 「官方原话内容」（正文原话）\n")
    hit = make_draft(body="\n<font color=\"grey\">「官方原话内容」</font>\n")
    _, ws = crosscheck_research(hit, research)
    assert not any("灰字引文" in w for w in ws)
    miss = make_draft(body="\n<font color=\"grey\">「编造的另一句话」</font>\n")
    _, ws2 = crosscheck_research(miss, research)
    assert any("灰字引文" in w for w in ws2)


# --- 红字不得「近乎逐字又改写」（2026-08-07 落为 WARN；规则见 blog-writer） ---

RED_RESEARCH = (
    "## 信息来源\n- 2026.06.01，来源。*标题*。https://example.com/a — "
    "通报称，经查，该民警在执行职务过程中存在违规使用警械的行为，已被停止执行职务\n"
)


def test_red_echoing_source_warns():
    # 逐字照抄一长段、只把首尾改掉几个字 = 规则要打的「近乎逐字又改写」
    draft = make_draft(body="\n<font color=\"red\">该民警在执行职务过程中存在违规使用警械</font>\n")
    _, ws = crosscheck_research(draft, RED_RESEARCH)
    assert any("红字与来源逐字重合" in w for w in ws)


def test_red_genuine_paraphrase_no_warn():
    draft = make_draft(body="\n<font color=\"red\">通报认定该警员违规动用警械并将其停职</font>\n")
    _, ws = crosscheck_research(draft, RED_RESEARCH)
    assert not any("红字与来源逐字重合" in w for w in ws)


def test_red_short_overlap_no_warn():
    draft = make_draft(body="\n<font color=\"red\">违规使用警械</font>\n")
    _, ws = crosscheck_research(draft, RED_RESEARCH)
    assert not any("红字与来源逐字重合" in w for w in ws)


def test_red_nonchinese_identifier_no_warn():
    # 案号/金额/外文原句本就只能逐字，非汉字占比高则排除
    research = ("## 信息来源\n- 2026.06.01，来源。*标题*。https://example.com/a — "
                "（2026）京0105民初12345号，赔偿 1,250,000 元\n")
    draft = make_draft(body="\n<font color=\"red\">（2026）京0105民初12345号，赔偿 1,250,000 元</font>\n")
    _, ws = crosscheck_research(draft, research)
    assert not any("红字与来源逐字重合" in w for w in ws)


# --- 新格式：灰字/红字逐字基准搬到 ## 摘录 节（## 信息来源 退化为纯书目） ---

RESEARCH_NEW = """## 事实
- 略[E1]。

## 信息来源
- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）

## 摘录
[E1] 信源1 · 正文原话 · 2026-08-07
他一直都没道歉，他欠我一个道歉
"""


def _draft(grey):
    return (
        "---\ntitle: 标题\n---\n\n"
        f'<font color="grey">{grey}</font>\n\n'
        "## 信息来源\n- 2026.07.31，极目新闻。*甲*。https://a.example/1\n"
    )


def test_grey_quote_checked_against_extract_section_in_new_format():
    _vs, ws = crosscheck_research(_draft("他一直都没道歉，他欠我一个道歉"), RESEARCH_NEW)
    assert not [w for w in ws if "灰字引文未在研究文件" in w]


def test_grey_quote_absent_from_extracts_warns_in_new_format():
    _vs, ws = crosscheck_research(_draft("他从来没有跟我说过一句对不起"), RESEARCH_NEW)
    assert any("灰字引文未在研究文件" in w for w in ws)
