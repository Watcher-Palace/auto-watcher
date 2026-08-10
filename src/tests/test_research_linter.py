import pytest
from pathlib import Path
from src.research_linter import lint_research

GOOD = ("# Research: 题 (990101, #1)\n\n## 事实\n"
        "<font color=\"blue\">2026年1月1日宣判</font>\n\n## 当事方\n某人\n\n"
        "## 信息来源\n- 2026.01.01，澎湃新闻。*真标题*。https://a/b — 摘录\n\n## 资产\n无\n")

def _mk(tmp_path, text, assets: list[str] | None = None, event="990101-1"):
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "research" / f"{event}-题.md"
    p.write_text(text, encoding="utf-8")
    if assets is not None:
        d = tmp_path / "draft" / f"{event}-assets"
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

def _snap(tmp_path, monkeypatch, url, body, event="260731-1"):
    from src import srcfetch

    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    p = srcfetch.snapshot_path(url, event)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# SOURCE: {url}\n# FETCHED: 2026-08-07\n\n{body}", encoding="utf-8")
    return p

def test_verbatim_quote_absent_from_snapshot_fails(tmp_path, monkeypatch):
    # 摘录自称 `正文原话`，但原文快照里根本没有这句 —— 拼接/改写/张冠李戴，
    # 这是唯一能机械核出"内容"而非"形状"的检查（WebFetch 的模型转述做不到）
    _snap(tmp_path, monkeypatch, "https://a/b", "她告诉记者，自己并不认识对方。")
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    vs = lint_research(_mk(tmp_path, text, event="260731-1"))
    assert any("不在原文快照里" in v for v in vs)

def test_verbatim_quote_present_in_snapshot_passes(tmp_path, monkeypatch):
    # 快照里逐字有（空白/引号差异不算），照过
    _snap(tmp_path, monkeypatch, "https://a/b", '她说：“我不认识他， 他欠我一个道歉”。')
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    assert lint_research(_mk(tmp_path, text, event="260731-1")) == []

def test_missing_snapshot_warns_not_fails(tmp_path, monkeypatch):
    # 抓不到快照的信源（JS 壳/反爬/付费墙）是常态，机械核不了是事实——WARN，不阻断。
    # 不经 _snap：body=None 没有对应"写一份内容为 None 的假快照"的意义，直接把
    # SNAPSHOTS 指到空目录才是"确实没抓到"的真实语义（对齐 Step 2 新格式测试的写法）。
    from src import srcfetch

    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "empty")
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    vs = lint_research(_mk(tmp_path, text, event="260731-1"))
    assert any(v.startswith("WARN：") and "无原文快照" in v for v in vs)
    assert all(v.startswith("WARN：") for v in vs)

def test_non_verbatim_form_not_checked_against_snapshot(tmp_path, monkeypatch):
    # 标题/转述照收，本来就不承诺逐字 —— 不核，也不该 WARN
    from src import srcfetch

    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "empty")
    text = GOOD.replace(" — 摘录", " — 「女销冠回应造谣者」（标题）")
    assert lint_research(_mk(tmp_path, text, event="260731-1")) == []

def test_assets_bidirectional(tmp_path):
    listed = GOOD.replace("## 资产\n无\n", "## 资产\n- 990101-1-图.jpg — https://a — 2026.1.1 — 通报截图\n")
    vs = lint_research(_mk(tmp_path, listed, assets=[]))          # 登记了但文件不存在
    assert any("不存在" in v for v in vs)
    vs2 = lint_research(_mk(tmp_path, GOOD, assets=["990101-1-孤儿.jpg"]))  # 存在但未登记
    assert any("未登记" in v for v in vs2)


# ==================== 新格式（## 摘录）====================

NEW_DOC = """# Research: 标题 (260731, #1)

## 事实
- 2025.10.12：李沧分局对一男子作出行拘5日决定[E1]。
<font color="blue">2026年7月31日：牟倩文提起民事诉讼[E1]。</font>

## 当事方
**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。

## 信息来源
- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）

## 摘录
[E1] 信源1 · 第三人称转述 · 2026-08-07
被给予行政拘留五日
[E2] 信源1 · 正文原话 · 2026-08-07
我有一度想从这个楼上我就直接跳下去了

## 资产
无 —— 本案无可抓证据图。
"""
SNAP_BODY = "决定书显示 被给予行政拘留五日 她说 我有一度想从这个楼上我就直接跳下去了"


def _new_doc(tmp_path, monkeypatch, doc=NEW_DOC, snap=SNAP_BODY):
    _snap(tmp_path, monkeypatch, "https://a.example/1", snap)
    p = tmp_path / "260731-1-标题.md"
    p.write_text(doc, encoding="utf-8")
    return p


def test_new_format_clean_doc_passes(tmp_path, monkeypatch):
    assert lint_research(_new_doc(tmp_path, monkeypatch)) == []


def test_extract_absent_from_snapshot_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("被给予行政拘留五日", "被给予行政拘留十日")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("不在原文快照里" in v and "[E1]" in v for v in vs)


def test_illegal_extract_form_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("· 第三人称转述 ·", "· 大概是这个意思 ·")
    assert any("形态不合法" in v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc)))


def test_extract_pointing_at_missing_source_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("[E1] 信源1 ·", "[E1] 信源7 ·")
    assert any("不存在的信源7" in v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc)))


def test_source_without_snapshot_fails(tmp_path, monkeypatch):
    from src import srcfetch

    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "empty")
    p = tmp_path / "260731-1-标题.md"
    p.write_text(NEW_DOC, encoding="utf-8")
    vs = lint_research(p)
    assert any("无快照" in v and not v.startswith("WARN：") for v in vs)


def test_snapshot_failed_source_may_not_back_a_verbatim_extract(tmp_path, monkeypatch):
    doc = (NEW_DOC.replace("— 快照 2026-08-07（900字）", "— 快照失败：25s 无响应")
                  .replace("[E1] 信源1 · 第三人称转述", "[E1] 信源1 · 正文原话"))
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("快照失败" in v and "正文原话" in v for v in vs)


def test_orphan_extract_only_warns(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("自述曾有轻生念头[E2]", "自述曾有轻生念头[E1]")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any(v.startswith("WARN：") and "[E2]" in v for v in vs)
    assert [v for v in vs if not v.startswith("WARN：")] == []


def test_duplicate_extract_id_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("[E2] 信源1 · 正文原话", "[E1] 信源1 · 正文原话")
    assert any("编号重复" in v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc)))


def test_asset_transcription_skips_snapshot_check(tmp_path, monkeypatch):
    # 图是二进制，字节比对不成立；指针成立即可，不得因此 FAIL
    doc = NEW_DOC.replace(
        "## 资产\n无 —— 本案无可抓证据图。",
        "## 资产\n- 260731-1-立案截图.jpg — https://a.example/1 — 2026.07.31 — 法院立案截图",
    ).replace(
        "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了",
        "[E2] 资产 260731-1-立案截图.jpg · 图上转录 · —\n案由：名誉权纠纷",
    )
    (tmp_path.parent / "draft" / "260731-1-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path.parent / "draft" / "260731-1-assets" / "260731-1-立案截图.jpg").write_bytes(b"x")
    p = tmp_path / "260731-1-标题.md"
    _snap(tmp_path, monkeypatch, "https://a.example/1", SNAP_BODY)
    p.write_text(doc, encoding="utf-8")
    assert [v for v in lint_research(p) if not v.startswith("WARN：")] == []


# ---- 从前序任务结转的四项，本任务必须一并处理（见 brief 开头） ----

def test_source_line_glued_snapshot_failed_tag_is_a_format_violation(tmp_path, monkeypatch):
    # 结转项 1：SRC_PARSE_RE 的 (\S+) 会贪婪吃 URL。" — " 缺空格时"快照失败"整段被吞进
    # url，snapshot_failed 会被静默判成 False（实测复现 https://b.example/2—快照失败：
    # 25s无响应）。SRC_RE 收紧后，缺空格必须在这里就响一条格式违规，不能悄悄放过。
    doc = NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1—快照失败：25s无响应",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("来源行" in v and not v.startswith("WARN：") for v in vs)


def test_glued_snapshot_failed_source_is_recognized_as_failed_not_just_missing(tmp_path, monkeypatch):
    # fix 轮 1：research_doc.SRC_PARSE_RE 的 URL 组也要收紧（与 research_linter.SRC_RE
    # 同形关系，两处必须同改）——它是 doc_sources()/_lint_extracts 走的独立解析路径，
    # 不经过 SRC_RE 这道格式闸。收紧前，即便 _lint_source_lines 已经报了格式违规，
    # 这里解析出的 Source.snapshot_failed 依旧是 False，一条 正文原话 摘录引用它时
    # 只会撞上笼统的"无快照"，而不是更准确、更能提示"这条来源本就抓不到"的
    # "标了 快照失败，不得作 正文原话 依据"。
    doc = (NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1—快照失败：25s无响应",
    ).replace("[E1] 信源1 · 第三人称转述", "[E1] 信源1 · 正文原话"))
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("快照失败" in v and "正文原话" in v and "[E1]" in v for v in vs)


def test_source_line_with_proper_spacing_still_passes(tmp_path, monkeypatch):
    # 收紧 SRC_RE 的同时不能误伤写对了的行——" — " 两侧带空格必须照常放行。
    # 用独立事件号 260731-9（不复用 _new_doc 的 260731-1），避免与
    # test_asset_transcription_skips_snapshot_check 共享 tmp_path.parent/draft/
    # 260731-1-assets/——_lint_assets 按 path.parent.parent 推导资产目录，
    # 那是跨用例共享的 pytest 会话临时根目录，不是每个用例独立的 tmp_path，
    # 该用例真的在那里落过一个文件，顺序在后的用例会看见它。
    _snap(tmp_path, monkeypatch, "https://a.example/1", SNAP_BODY, event="260731-9")
    doc = NEW_DOC.replace("(260731, #1)", "(260731, #9)")
    p = tmp_path / "260731-9-标题.md"
    p.write_text(doc, encoding="utf-8")
    assert lint_research(p) == []


def test_multiline_extract_body_fully_checked_not_just_first_line(tmp_path, monkeypatch):
    # 结转项 2：一个 [E] 标签下若排成多行/多句，必须整段都核对，不能只核第一句就放行——
    # 否则"一个标签管多句"时后半句的伪造会被漏判（Task 3 评审：临时核对脚本 14 条摘录
    # 只覆盖到 3 条，正是这种写法漏的）。此处只有第一句在快照里，第二句是编的。
    doc = NEW_DOC.replace(
        "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了",
        "[E2] 信源1 · 正文原话 · 2026-08-07\n"
        "我有一度想从这个楼上我就直接跳下去了\n随后又被送去了精神病院",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("不在原文快照里" in v and "[E2]" in v for v in vs)


NEW_DOC_3E = NEW_DOC.replace(
    "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了\n",
    "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了\n"
    "[E3] 信源1 · 正文原话 · 2026-08-07\n这句话是编的\n",
).replace("自述曾有轻生念头[E2]。", "自述曾有轻生念头[E2][E3]。")


def test_third_of_three_extracts_is_still_checked_not_sampled_away(tmp_path, monkeypatch):
    # 结转项 2 的另一面：证明没有早停/抽样上限——第三条（也是最后一条）摘录同样要核，
    # 不能因为前两条核过了就放过它
    vs = lint_research(_new_doc(tmp_path, monkeypatch, NEW_DOC_3E))
    assert any("不在原文快照里" in v and "[E3]" in v for v in vs)


def test_malformed_extract_head_is_flagged(tmp_path, monkeypatch):
    # 结转项 3：] 后缺空格这四类手误，原实现会静默丢弃整条摘录、把正文并入上一条——
    # 那是误挂不是漏判（E2 的引文会拿 E1 的身份通过核对）。必须消费
    # research_doc.malformed_extract_heads()，每条畸形标签单独出一条违规。
    doc = NEW_DOC.replace(
        "[E2] 信源1 · 正文原话 · 2026-08-07",
        "[E2]信源1 · 正文原话 · 2026-08-07",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("[E2]" in v and not v.startswith("WARN：") for v in vs)


def test_unknown_section_heading_inside_extracts_is_flagged(tmp_path, monkeypatch):
    # 结转项 4（本重构最危险的静默口子）：sections() 按 ## 切分，## 摘录 节正文里
    # 一旦混入未预期的二级标题，该行之后的一切——含格式完全合规的摘录——会从
    # extracts()/malformed_extract_heads() 同时消失，无报错无痕迹。不能在解析层修
    # （放宽解析＝把异常悄悄吞掉），只能在策略层堵成因：出现已知集合之外的标题即报违规。
    doc = NEW_DOC.replace(
        "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了",
        "## 网友评论区截图说明\n"
        "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("网友评论区截图说明" in v and not v.startswith("WARN：") for v in vs)


def test_legacy_doc_without_extract_section_unaffected_by_unknown_section_check(tmp_path):
    # 未知章节闸口只装在 _lint_new——旧格式在途事件本就不带 ## 摘录，不该被这条新规则误伤
    text = GOOD + "\n## 编辑注\n与本案无关的备注\n"
    vs = lint_research(_mk(tmp_path, text))
    assert not any("未知章节" in v for v in vs)
