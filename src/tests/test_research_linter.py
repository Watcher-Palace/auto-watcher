import pytest
from pathlib import Path
from src.research_linter import lint_research

GOOD = ("# Research: 题 (990101, #1)\n\n## 事实\n"
        "<font color=\"blue\">2026年1月1日宣判</font>\n\n## 当事方\n某人\n\n"
        "## 信息来源\n- 2026.01.01，澎湃新闻。*真标题*。https://a/b — 摘录\n\n## 资产\n无\n")

def _mk(tmp_path, text, assets: list[str] | None = None):
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "research" / "990101-1-题.md"
    p.write_text(text, encoding="utf-8")
    if assets is not None:
        d = tmp_path / "draft" / "990101-1-assets"
        d.mkdir(parents=True, exist_ok=True)
        for name in assets:
            (d / name).write_text("x", encoding="utf-8")
    return p

def test_good_file_passes(tmp_path):
    assert lint_research(_mk(tmp_path, GOOD)) == []

def test_missing_section_and_bad_source_line(tmp_path):
    text = GOOD.replace("## 当事方\n某人\n\n", "").replace(
        "- 2026.01.01，澎湃新闻。*真标题*。https://a/b — 摘录", "- 澎湃新闻报道了")
    vs = lint_research(_mk(tmp_path, text))
    assert any("当事方" in v for v in vs) and any("来源行" in v for v in vs)

def test_source_line_allows_unverified_date_marker(tmp_path):
    text = GOOD.replace("- 2026.01.01，澎湃新闻。*真标题*。https://a/b — 摘录",
                        "- 澎湃新闻。*真标题*。https://a/b — 摘录（发布日期查证失败）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_source_date_must_be_zero_padded(tmp_path):
    # 来源行日期必须补零（2026.01.01），不接受 2026.1.1：
    # 两种写法此前都放行，研究阶段随手选一种，再经 linter.py --research 的
    # 逐字比对变成对写手的硬约束——写手照 template 的补零惯例写反而 LINT FAIL，
    # 只能倒回去迁就研究文件，格式污染就此进入草稿并发布上线。
    for bad in ("2026.1.1", "2026.1.01", "2026.01.1"):
        text = GOOD.replace("2026.01.01，澎湃新闻", f"{bad}，澎湃新闻")
        vs = lint_research(_mk(tmp_path, text))
        assert any("来源行" in v for v in vs), f"{bad} 应被拦下，实际放行"

def test_blue_mark_rules(tmp_path):
    no_date = GOOD.replace("2026年1月1日宣判", "已经宣判")
    stale = GOOD.replace("2026年1月1日宣判", "截至2026年1月1日暂无进展")
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, no_date)))
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, stale)))

def test_bare_platform_brand_fails(tmp_path):
    text = GOOD.replace("澎湃新闻", "新浪新闻")
    vs = lint_research(_mk(tmp_path, text))
    assert any("平台品牌" in v for v in vs)

def test_platform_brand_with_attribution_passes(tmp_path):
    text = GOOD.replace("澎湃新闻", "腾讯新闻（栏目\"文娱没有圈\"）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_quoted_excerpt_requires_form_tag(tmp_path):
    bad = GOOD.replace(" — 摘录", " — 「官方原话」")
    assert any("形态标注" in v for v in lint_research(_mk(tmp_path, bad)))
    good = GOOD.replace(" — 摘录", " — 「官方原话」（正文原话）")
    assert lint_research(_mk(tmp_path, good)) == []

def test_slug_identical_title_warns_not_fatal(tmp_path):
    text = GOOD.replace("*真标题*。https://a/b",
                        "*Man jailed for life*。https://x/news/man-jailed-for-life-498512")
    vs = lint_research(_mk(tmp_path, text))
    assert any(v.startswith("WARN：") and "slug" in v for v in vs)
    assert all(v.startswith("WARN：") for v in vs)   # WARN 不阻断：无其他违规

def test_real_title_differing_from_slug_no_warn(tmp_path):
    # 站点 slug 常剥虚词——真标题与 slug 不同时不告警（含 for 的真标题 vs 无 for 的 slug）
    text = GOOD.replace("*真标题*。https://a/b",
                        "*Man jailed for drugging women*。https://x/news/man-jailed-drugging-women")
    assert lint_research(_mk(tmp_path, text)) == []

def test_tracked_uid_in_sources_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKED_UIDS", "1234567890")
    text = GOOD.replace("https://a/b", "https://weibo.com/1234567890/AbCdE")
    vs = lint_research(_mk(tmp_path, text))
    assert any("追踪账号" in v for v in vs)

def test_title_wording_quoted_as_body_speech_fails(tmp_path):
    # 叙述节的引文若只在某条来源的 *标题* 里出现、任何摘录里都没有，就是把标题措辞
    # 当成了当事人原话——标题惯把第三人称改写成第一人称，写手无网络只能照单全收。
    # （blog-researcher「形态标注」条已明文禁止，四次复现后落成机械闸口）
    text = GOOD.replace(
        "## 当事方\n某人\n", "## 当事方\n她表示：\"我不认识他，他欠我一个道歉\"（正文原话）\n"
    ).replace("*真标题*", "*女销冠回应：\"我不认识他，他欠我一个道歉\"*")
    vs = lint_research(_mk(tmp_path, text))
    assert any("只见于来源标题" in v for v in vs)

def test_same_quote_present_in_an_excerpt_passes(tmp_path):
    # 同一句在某条摘录里有逐字登记 → 有正文原话依据，不拦
    text = GOOD.replace(
        "## 当事方\n某人\n", "## 当事方\n她表示：\"我不认识他，他欠我一个道歉\"（正文原话）\n"
    ).replace("*真标题*", "*女销冠回应：\"我不认识他，他欠我一个道歉\"*").replace(
        " — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）"
    )
    # 无快照时那句摘录另带一条 WARN（机械核不了），但不阻断
    assert all(v.startswith("WARN：") for v in lint_research(_mk(tmp_path, text)))

def test_quote_explicitly_marked_as_title_passes(tmp_path):
    # 标好形态「标题」的照收（agent 规则就是"照收但必须标形态"）
    text = GOOD.replace(
        "## 当事方\n某人\n", "## 当事方\n报道标题作\"我不认识他，他欠我一个道歉\"（标题措辞）\n"
    ).replace("*真标题*", "*女销冠回应：\"我不认识他，他欠我一个道歉\"*")
    assert lint_research(_mk(tmp_path, text)) == []

def test_correction_note_quoting_the_bad_line_passes(tmp_path):
    # update 模式的更正说明要原样引回被推翻的错句，否则读者看不出改了什么——
    # 那是留痕不是主张，不能被自己的闸口拦住
    text = GOOD.replace(
        "## 当事方\n某人\n",
        "## 当事方\n**更正（评审v2-问题1）**：原稿将两句拼接为\"我不认识他，他欠我一个道歉\""
        "并误标\"正文原话\"，经核实该合并句不存在\n",
    ).replace("*真标题*", "*女销冠回应：\"我不认识他，他欠我一个道歉\"*")
    assert lint_research(_mk(tmp_path, text)) == []

def test_short_quoted_term_not_flagged(tmp_path):
    # 短词（案由、状态等）在标题里撞上不算伪引用
    text = GOOD.replace("## 当事方\n某人\n", "## 当事方\n案件状态\"待审核\"\n").replace(
        "*真标题*", "*立案\"待审核\"*")
    assert lint_research(_mk(tmp_path, text)) == []

def _snap(tmp_path, monkeypatch, url, body):
    from src import srcfetch
    monkeypatch.setattr(srcfetch, "CACHE", tmp_path / ".srccache")
    if body is not None:
        (tmp_path / ".srccache").mkdir(parents=True, exist_ok=True)
        srcfetch.snapshot_path(url).write_text(
            f"# SOURCE: {url}\n# FETCHED: x\n\n{body}", encoding="utf-8")

def test_verbatim_quote_absent_from_snapshot_fails(tmp_path, monkeypatch):
    # 摘录自称 `正文原话`，但原文快照里根本没有这句 —— 拼接/改写/张冠李戴，
    # 这是唯一能机械核出"内容"而非"形状"的检查（WebFetch 的模型转述做不到）
    _snap(tmp_path, monkeypatch, "https://a/b", "她告诉记者，自己并不认识对方。")
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    vs = lint_research(_mk(tmp_path, text))
    assert any("不在原文快照里" in v for v in vs)

def test_verbatim_quote_present_in_snapshot_passes(tmp_path, monkeypatch):
    # 快照里逐字有（空白/引号差异不算），照过
    _snap(tmp_path, monkeypatch, "https://a/b", '她说：“我不认识他， 他欠我一个道歉”。')
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_missing_snapshot_warns_not_fails(tmp_path, monkeypatch):
    # 抓不到快照的信源（JS 壳/反爬/付费墙）是常态，机械核不了是事实——WARN，不阻断
    _snap(tmp_path, monkeypatch, "https://a/b", None)
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    vs = lint_research(_mk(tmp_path, text))
    assert any(v.startswith("WARN：") and "无原文快照" in v for v in vs)
    assert all(v.startswith("WARN：") for v in vs)

def test_non_verbatim_form_not_checked_against_snapshot(tmp_path, monkeypatch):
    # 标题/转述照收，本来就不承诺逐字 —— 不核，也不该 WARN
    _snap(tmp_path, monkeypatch, "https://a/b", None)
    text = GOOD.replace(" — 摘录", " — 「女销冠回应造谣者」（标题）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_assets_bidirectional(tmp_path):
    listed = GOOD.replace("## 资产\n无\n", "## 资产\n- 990101-1-图.jpg — https://a — 2026.1.1 — 通报截图\n")
    vs = lint_research(_mk(tmp_path, listed, assets=[]))          # 登记了但文件不存在
    assert any("不存在" in v for v in vs)
    vs2 = lint_research(_mk(tmp_path, GOOD, assets=["990101-1-孤儿.jpg"]))  # 存在但未登记
    assert any("未登记" in v for v in vs2)
