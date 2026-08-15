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
    # 研究文件落在 tmp_path/"research"/（与旧格式的 _mk 一致），不是 tmp_path/ 根上——
    # _lint_assets/_lint_extracts 按 path.parent.parent 推资产目录，落在 tmp_path/ 根
    # 上会让 path.parent.parent 变成 pytest 整场共享的 basetemp，不是本用例私有的
    # tmp_path。评审证实这会打爆用同一事件号、断言"零 FAIL"且排在污染源之后的用例
    # （已确认会打中 Task 6 计划里写死的 4 个测试）。
    _snap(tmp_path, monkeypatch, "https://a.example/1", snap)
    d = tmp_path / "research"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "260731-1-标题.md"
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
    # fix 轮 2 起 _new_doc 把研究文件落进 tmp_path/"research"/，path.parent.parent
    # 变成本用例私有的 tmp_path，不再是跨用例共享的 pytest basetemp，不需要再用
    # 独立事件号绕开污染——直接用 _new_doc 的默认事件即可。
    assert lint_research(_new_doc(tmp_path, monkeypatch)) == []


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


# ==================== fix 轮 2（评审 task-5-review.md）====================

def test_drifted_摘录_heading_with_parenthetical_suffix_is_not_downgraded(tmp_path, monkeypatch):
    # C-1（Critical，结转第 4 项的另一半）：## 摘录 标题只要不是恰好"摘录"两个字，
    # is_new_format 判 False，文件整个掉进 _lint_legacy——摘录层闸口连跑都没跑，
    # 而 _lint_legacy 既没有"缺少 ## 摘录"检查也没有未知节标题检查，零违规通过。
    # 分派处必须兜底：命中"节标题含摘录"或"全文出现 [E数字]"任一条就不许降级。
    doc = NEW_DOC.replace("## 摘录\n", "## 摘录（补充）\n").replace(
        "被给予行政拘留五日", "被给予行政拘留十年"  # 摘录正文换成编的，证明不是碰巧过关
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert vs != []
    assert any("摘录" in v for v in vs)


def test_drifted_摘录_heading_missing_space_variant_is_not_downgraded(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("## 摘录\n", "##摘录\n")  # 缺一个空格
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert vs != []
    assert any("摘录" in v for v in vs)


def test_extract_section_entirely_missing_but_e_refs_remain_is_not_downgraded(tmp_path, monkeypatch):
    # 整个 ## 摘录 节缺失，但 ## 事实/## 当事方 仍挂着 [E1][E2] 引用——
    # 判据取全文而不是只取这两节，兜的正是"节标题缺空格且事实层恰好没挂 [E]"这类变体，
    # 这里反过来验证"节没了但 [E] 还在"同样触发
    doc = NEW_DOC.split("## 摘录\n")[0] + "## 资产\n无 —— 本案无可抓证据图。\n"
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert vs != []
    assert any("摘录" in v for v in vs)


def test_consistency_gate_catches_source_lines_that_pass_format_but_fail_to_parse(tmp_path, monkeypatch):
    # I-1 结转的第二件（一致性闸，不变量）：过了格式闸（SRC_RE 匹配或含"发布日期查证
    # 失败"旁路）的来源行条数必须等于 doc_sources() 实际解析出的信源数——这条不依赖
    # 任何具体脏行样式，SRC_RE 与 SRC_PARSE_RE 今后任何一侧单独改动导致的分歧都会响。
    # 这里构造一种因半角逗号（应为全角"，"）导致 SRC_PARSE_RE 解析失败、但因含
    # "发布日期查证失败"字样而被判"过了格式闸"的行。
    doc = NEW_DOC.replace(
        "## 信息来源\n- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）",
        "## 信息来源\n"
        "- 发布日期查证失败,极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("信源编号会整体错位" in v for v in vs)


def test_unverified_date_marker_no_longer_triggers_the_consistency_gate(tmp_path, monkeypatch):
    # 反证：I-1 结转第一件（放宽 SRC_PARSE_RE 的日期组）落地后，规范写法的
    # "发布日期查证失败（…）" 不应该再触发第二件的一致性闸——它现在能被正常解析。
    doc = NEW_DOC.replace(
        "## 信息来源\n- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）",
        "## 信息来源\n"
        "- 发布日期查证失败（页面未展示可核实日期），极目新闻。*甲*。"
        "https://a.example/1 — 快照 2026-08-07（900字）",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("信源编号会整体错位" in v for v in vs)


def test_new_format_source_tail_with_embedded_quote_is_flagged(tmp_path, monkeypatch):
    # I-2：新格式的逐字通道只有 ## 摘录 一条，_lint_new 连 _verify_quotes 一起丢了，
    # 但没有任何检查强制"来源行尾不能带引文"——同一条伪造引文写在来源行尾，旧格式
    # FAIL、新格式零违规，比它取代的旧闸口更松且无声。行尾出现够长的引号跨度必须
    # 报违规，逼着把引文挪进 ## 摘录（不在这里核对内容——_verify_quotes 不接回
    # _lint_new，那会造出第二条逐字通道）。真·内嵌长引文（10 字）必须仍被拦下——
    # 只加放行测试而不钉住拦截行为，等于把闸口拆了没人知道（F-2 收工要求）。
    doc = NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1 — 「我当时真的撑不下去了」（正文原话）",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("来源行尾带着长引文" in v for v in vs)


def test_source_tail_column_name_in_brackets_not_flagged(tmp_path, monkeypatch):
    # F-2 假阳性 1：「深度报道」是栏目名不是引文，跨度只有 4 字，< QUOTE_MIN(8)
    doc = NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1 — 快照 2026-08-07（900字），系「深度报道」栏目稿",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("来源行尾带着长引文" in v for v in vs)


def test_source_tail_inch_marks_not_flagged(tmp_path, monkeypatch):
    # F-2 假阳性 2：12"／15" 是英寸符，两个 ASCII 双引号凑够 count>=2 的旧判据会
    # 误报；跨度（"与 15" 去空白后）远小于 QUOTE_MIN
    doc = NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1 — 快照 2026-08-07（900字），涉案显示器 12\" 与 15\" 两款",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("来源行尾带着长引文" in v for v in vs)


def test_source_tail_short_fullwidth_quote_not_flagged(tmp_path, monkeypatch):
    # F-2 假阳性 3（复审补试，原评审没试全角引号）："回应"二字，跨度 2 字
    doc = NEW_DOC.replace(
        "https://a.example/1 — 快照 2026-08-07（900字）",
        "https://a.example/1 — 快照 2026-08-07（900字），标题含“回应”二字",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("来源行尾带着长引文" in v for v in vs)


def test_duplicate_摘录_section_heading_is_flagged(tmp_path, monkeypatch):
    # I-3：sections() 是 dict，同名节后者覆盖前者。两个 ## 摘录 节时，前一节的全部
    # 摘录从 extracts()/malformed_extract_heads() 里同时消失——与结转第 4 项描述的
    # 失败模式一模一样，但因为标题是已知的，未知节标题闸口拦不住。
    doc = NEW_DOC.replace(
        "## 资产\n无 —— 本案无可抓证据图。\n",
        "## 资产\n无 —— 本案无可抓证据图。\n\n## 摘录\n[E9] 信源1 · 正文原话 · 2026-08-07\n又一条编的\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("重复" in v and "摘录" in v for v in vs)


def test_duplicate_legacy_section_heading_is_also_flagged(tmp_path):
    # I-3 顺带覆盖旧格式：评审只要求新格式，但"同名节静默覆盖"在旧格式里是同一个坑，
    # 覆盖旧格式是免费的（存量语料里同名重复节 0 份，检查放在 lint_research 分派前，
    # 新旧两条路径都走）
    text = GOOD + "\n## 信息来源\n- 2026.01.02，另一报。*另一题*。https://c/d — 摘录\n"
    vs = lint_research(_mk(tmp_path, text))
    assert any("重复" in v and "信息来源" in v for v in vs)


def test_filename_without_event_prefix_is_a_lint_violation_not_a_traceback(tmp_path):
    # M-3：event_of 在新旧两条路径上都无保护地调用，文件名不含 YYMMDD-N- 前缀时
    # 原本会抛裸 ValueError traceback——main() 是给人跑的，崩出 traceback 会让人
    # 以为是环境坏了，应该是一条正常的 LINT FAIL 而不是程序崩溃。
    p = tmp_path / "题目.md"  # 没有 YYMMDD-N- 前缀
    p.write_text(GOOD, encoding="utf-8")
    vs = lint_research(p)
    assert any("事件标识" in v for v in vs)


# ==================== fix 轮 3（复审 task-5-rereview2.md）====================

def test_drifted_title_with_fullwidth_e_refs_is_not_downgraded(tmp_path, monkeypatch):
    # F-1（C-1 残余）：复审复现的复合绕过——标题改成不含"摘录"子串的 ## 引文摘编，
    # 且全文所有 [E] 引用（含事实/当事方叙述句里的）都写成全角 ［E1］／［E2］，
    # 两个兜底判据同时落空（标题不含"摘录"、E_REF_RE 只认半角）。改用
    # E_REF_LOOSE_RE（收全半角方括号，只给这条兜底用，不放宽 E_REF_RE 本身）后
    # 必须重新被拦下。
    doc = (
        NEW_DOC.replace("## 摘录\n", "## 引文摘编\n")
        .replace("[E1]", "［E1］")
        .replace("[E2]", "［E2］")
        .replace("被给予行政拘留五日", "被给予行政拘留十年")  # 正文也换成编的
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert vs != []
    assert any("摘录" in v for v in vs)


def test_duplicate_section_message_points_at_flush_left_line_in_excerpt(tmp_path, monkeypatch):
    # F-3：逻辑不改（摘录正文里顶格的 ## 事实 确实会被 sections() 切开、吞掉其后
    # 内容，检测和严重度都是对的），只在消息里补一句诊断线索：这也可能来自摘录
    # 正文里的顶格 ## 行，处理办法是让该行不顶格，不是改引文的字（摘录必须逐字）。
    doc = NEW_DOC.replace(
        "被给予行政拘留五日",
        "被给予行政拘留五日\n## 事实\n（判决书原文摘录，顶格小标题）",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("重复" in v and "摘录" in v and "顶格" in v for v in vs)


# ==================== Task 6：事实层 [E] 覆盖闸口 ====================

def test_sentence_without_any_extract_ref_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。",
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头。她连续三年为该中心销售冠军[E2]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


def test_short_fragment_is_not_treated_as_a_sentence(tmp_path, monkeypatch):
    # 小标题、分组行不该误报——去掉 [E] 与标记后不足 8 个汉字的不算句子
    doc = NEW_DOC.replace("## 当事方\n", "## 当事方\n**两组报道不一：**\n")
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_reference_to_undefined_extract_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("自述曾有轻生念头[E2]", "自述曾有轻生念头[E2][E9]")
    assert any("不存在的 [E9]" in v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc)))


def test_verification_failure_mark_is_exempt(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**查证失败（评审v3-问题2）**：男子是否道歉过，多方检索无法证实。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_search_record_mark_is_exempt(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "## 事实\n",
        "## 事实\n**检索记录**：检索至2026年8月9日未见后续实质性进展报道。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_snapshot_failed_source_may_not_solely_back_a_fact(tmp_path, monkeypatch):
    doc = (NEW_DOC.replace("— 快照 2026-08-07（900字）", "— 快照失败：25s 无响应")
                  .replace("[E2] 信源1 · 正文原话", "[E2] 信源1 · 标题"))
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("快照失败" in v and "单独支撑" in v for v in vs)


def test_quote_span_must_hit_an_extract(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我当时真的撑不下去了」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_quote_span_present_in_an_extract_passes(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我有一度想从这个楼上我就直接跳下去了」[E2]",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


# ==================== fix 轮 1（评审 task-6-review.md）====================

def test_exempt_marker_line_without_terminal_punctuation_does_not_swallow_next_fact(
    tmp_path, monkeypatch
):
    # F-1：豁免标记行没有句末标点时（语料里 17 条豁免行有 4 条是这个形态），后面
    # 紧跟的独立事实句不能被一并放过——豁免只摘掉标记所在的那一行
    doc = NEW_DOC.replace(
        "## 当事方\n**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
        "## 当事方\n**查证失败（评审v2-问题3）**：男子是否曾出面道歉未能确认\n"
        "另有一名同案人员已因该事件被警方处以行政拘留十日。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v and "另有一名同案人员" in v for v in vs)


def test_exempt_marker_line_still_exempts_itself_when_followed_by_a_sourced_fact(
    tmp_path, monkeypatch
):
    # 正例：豁免标记行（无句末标点）本身仍不需要 [E]；紧跟的事实句如果确实挂了 [E]，
    # 不该被 F-1 的行级摘除误伤
    doc = NEW_DOC.replace(
        "## 当事方\n**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
        "## 当事方\n**查证失败（评审v2-问题3）**：男子是否曾出面道歉未能确认\n"
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_exempt_marker_bare_form_without_parenthetical_is_recognized(tmp_path, monkeypatch):
    # F-2：语料实测 73% 的「查证失败」标记没有精确的（评审vN-问题K）括注——裸
    # **查证失败** 必须也被认出，不能只认最初那一种精确写法
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**查证失败**：男子是否道歉过，多方检索无法证实。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_exempt_marker_with_trailing_note_is_recognized(tmp_path, monkeypatch):
    # F-2：标记内跟着别的说明文字（"，写手不得使用该细节"）也要认
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**查证失败，写手不得使用该细节**：所谓十五人漏罪一说未见任何可核实来源。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_bare_unbolded_verification_failure_word_is_not_exempt(tmp_path, monkeypatch):
    # 正例（F-2 边界 1）：豁免必须锚在加粗上——散文里裸写"查证失败"三个字不算标记，
    # 该句仍需要 [E]，否则就是把 F-3 的成因复制到这一侧
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n赔偿金额查证失败，另据报道她已委托律师提起上诉。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


def test_correction_marker_is_not_accidentally_exempted(tmp_path, monkeypatch):
    # 正例（F-2 边界 2）：**更正（…）** 不在 EXEMPT_RE 的豁免范围内——更正说明本身
    # 带事实主张，必须继续挂 [E]
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**更正（评审v2-问题1）**：经核实，牟倩文实际为该门店销售季军。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


def test_verification_failure_word_embedded_mid_bold_span_is_not_treated_as_a_label(
    tmp_path, monkeypatch
):
    # 设计选择记录：EXEMPT_RE 要求"查证失败/检索记录"紧跟在 ** 之后（标记式用法），
    # 不匹配它出现在加粗片段中段的叙述性结论（"**判定为查证失败**"这类，语料真实存在）——
    # 这类写法常嵌在很长的整行叙述里，若也认，会连累同一行里其余未核实的内容一起被
    # F-1 的整行摘除放过，比原问题更糟
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n经多方检索，网传她已离职并自杀未遂一说**判定为查证失败**，不予采信。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


def test_bare_verification_failure_word_no_longer_exempts_a_fabricated_quote(
    tmp_path, monkeypatch
):
    # F-3：CORRECTION_RE 词面裸匹配曾让"查证失败"三个字（不加粗）就能豁免其后 60 字内
    # 任意引文的逐字核对——新格式必须要求加粗的正式标记，裸词不再生效
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]。",
        "自述曾有轻生念头[E2]，警方称身份查证失败后她告诉记者「他根本没有资格评价我的人生」。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_formal_correction_marker_still_exempts_the_quoted_old_text(tmp_path, monkeypatch):
    # 正例：真正的更正说明（加粗、带评审编号）引用被推翻的旧错句，仍应豁免逐字核对——
    # 这是这条豁免窗口最初的设计场景，F-3 收紧后不能连它一起拦下
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**更正（评审v2-问题1）**：原稿将\"我不认识他，他欠我一个道歉\"误标"
        "正文原话，经核实该句不存在[E2]。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


# ==================== fix 轮 2（评审复验后新增 F-4）====================

def test_markdown_subheading_is_not_treated_as_a_sentence(tmp_path, monkeypatch):
    # F-4：`### 姓名（角色）` 这类小标题不是事实主张——语料 25 份文件、155 处用它给
    # 事实/当事方分节，标题行本身通常不带句末标点，落成独立残留片段时被误报"无出处"
    doc = NEW_DOC.replace(
        "## 当事方\n**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
        "## 当事方\n**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n"
        "### 曹某某（被告人，本案核心当事人）\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("无 [E] 出处" in v for v in vs)


def test_markdown_subheading_followed_by_a_sourced_fact_still_checked(tmp_path, monkeypatch):
    # 正例：小标题被摘掉后，紧跟的事实句仍要照常核——不是把整片一并放过
    doc = NEW_DOC.replace(
        "## 当事方\n**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
        "## 当事方\n### 牟倩文（女方，当事人）\n"
        "青岛保时捷中心销售，自述曾有轻生念头[E2]。\n",
    )
    assert [v for v in lint_research(_new_doc(tmp_path, monkeypatch, doc))
            if not v.startswith("WARN：")] == []


def test_bold_label_line_is_not_treated_as_a_markdown_heading(tmp_path, monkeypatch):
    # 正例（F-4 边界，同 F-2 第二条）：`**加粗小标题**：` 是另一种写法，不该被
    # HEADING_LINE_RE 顺手放过——后面常跟着需要出处的事实主张，缺了 [E] 仍要报
    doc = NEW_DOC.replace(
        "## 当事方\n",
        "## 当事方\n**曹某某（被告人）**：本案核心当事人，涉嫌寻衅滋事罪被提起公诉。\n",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


# ==================== final-review fix 轮 1 ====================


def test_fact_quote_of_title_form_extract_fails(tmp_path, monkeypatch):
    # F-2：事实层的逐字凭据只认 正文原话／图上转录——标题惯把第三人称改写成第一
    # 人称，把 标题 形态的摘录当直接引语引用必须 FAIL（此前 base 不分形态会静默放行）
    doc = NEW_DOC.replace(
        "[E1] 信源1 · 第三人称转述 · 2026-08-07",
        "[E1] 信源1 · 标题 · 2026-08-07",
    ).replace(
        "自述曾有轻生念头[E2]。",
        "自述「被给予行政拘留五日」[E2]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_fact_quote_of_verbatim_form_extract_passes(tmp_path, monkeypatch):
    # 正例：同一句改标 正文原话，仍应放行
    doc = NEW_DOC.replace(
        "[E1] 信源1 · 第三人称转述 · 2026-08-07",
        "[E1] 信源1 · 正文原话 · 2026-08-07",
    ).replace(
        "自述曾有轻生念头[E2]。",
        "自述「被给予行政拘留五日」[E2]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_quote_span_violation_message_gives_a_legal_alternative(tmp_path, monkeypatch):
    # F-7c：只说"未命中任何摘录"会让 agent 以为只能补一条假摘录——消息须给出
    # 两条合法出路（去掉引号写成转述，或补一条摘录）
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我当时真的撑不下去了」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    msg = next(v for v in vs if "未命中任何摘录" in v)
    assert "转述" in msg and "补一条摘录" in msg


def test_quote_span_with_markdown_emphasis_still_matches_extract(tmp_path, monkeypatch):
    # F-7a：叙述节引用摘录内容时若混进了 markdown 强调符（真实语料：**合成聊天记录**
    # 并散布至互联网），整串比对若不剥 ** 必然落空——摘录/快照原文没有这层 markdown，
    # 问题出在叙述节引用时手滑带上了，不是编造
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「**我有一度想从这个楼上我就直接跳下去了**」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_quote_span_with_ellipsis_elision_still_matches_by_segment(tmp_path, monkeypatch):
    # F-7b：省略号节略的逐字引文——转述时用「……」跳过中间内容是正常写法，整串
    # 比对必然落空，不是编造。按省略号切段，每段单独达到 QUOTE_MIN 且命中即算命中。
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我有一度想从这个楼上……我就直接跳下去了」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_quote_span_with_ellipsis_but_fabricated_segment_still_fails(tmp_path, monkeypatch):
    # 正例边界：省略号回退只在"每段都命中"时生效——若某一段本身是编的，仍要 FAIL，
    # 不能因为整句挂了个省略号就整体免检
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我有一度想从这个楼上……哭着说都是他逼的」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


# ==================== final-review fix 轮 2（controller 复核 Critical） ====================


def test_ellipsis_segments_must_come_from_the_same_extract_not_stitched_across_two(
    tmp_path, monkeypatch
):
    # F-7b 的分段回退此前允许各段各自命中不同摘录（各段分别在 base——所有摘录拼起来
    # 的整串——里各找各的），省略号闸口本是防拼接的，这样反而把跨摘录拼接的伪引用
    # 放回来了。真实复现：E1 支撑前半段、E2 支撑后半段，两段各自为真，合起来是从未
    # 出现过的一句话。改成要求全部分段命中同一条摘录后，必须 FAIL。
    doc = NEW_DOC.replace(
        "[E1] 信源1 · 第三人称转述 · 2026-08-07\n被给予行政拘留五日",
        "[E1] 信源1 · 正文原话 · 2026-08-07\n以名誉权纠纷为由，起诉一名对她造黄谣的男子",
    ).replace(
        "自述曾有轻生念头[E2]",
        "自述「以名誉权纠纷为由，起诉一名对她造黄谣的男子……"
        "我有一度想从这个楼上我就直接跳下去了」[E1][E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_ellipsis_segments_from_the_same_extract_still_pass(tmp_path, monkeypatch):
    # 正例：两段都出自同一条摘录时（F-7b 本来的场景）仍应放行——修复不能连这个也拦下
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我有一度想从这个楼上……我就直接跳下去了」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_ellipsis_segment_with_markdown_emphasis_still_passes(tmp_path, monkeypatch):
    # R-1 复核：分段回退此前比对时漏了 norm_quote(seg)——段内混进 markdown 强调
    # （F-7a 刚修过的那一类）会被原样拿去和已归一化的 body 比，必然落空，等于把
    # F-7a 从省略号这一侧又打回去了。两段仍出自同一条摘录（E2），只是其中一段
    # 带了 ** 强调符。
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「**我有一度想从这个楼上**……我就直接跳下去了」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_ellipsis_segment_with_embedded_quote_mark_still_passes(tmp_path, monkeypatch):
    # R-1 复核：同一个漏归一化的坑，换成段内嵌引号壳（“”）——同样出自同一条摘录 E2。
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]",
        "自述「我有一度想从这个楼上……“我就直接跳下去了”」[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_footnote_style_marks_are_attributed_to_the_correct_sentence(tmp_path, monkeypatch):
    # F-3：脚注式写法（[E] 挂在句末标点之后）此前会让标记随下一句被切走，出处整体
    # 错位一位——第一句因此显得"没有出处"，真正的坏引用（不存在的 [E9]）反而落进
    # 过短的残留片段被悄悄漏检。切句前把标记搬到标点之前后，三句应各自正确归因：
    # 句 1/2 的合法引用不受影响，句 3 的坏引用被正确报出、且报的是句 3 的内容。
    doc = NEW_DOC.replace(
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。",
        "青岛保时捷中心销售一职多年负责该品牌门店业务。[E1]"
        "她自述曾经产生过轻生的念头并非虚言。[E2]"
        "另据其本人陈述遭遇过多次言语侮辱行为。[E9]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("无 [E] 出处" in v for v in vs)
    assert any("不存在的 [E9]" in v and "侮辱行为" in v for v in vs)


def test_inline_style_marks_unaffected_by_reordering(tmp_path, monkeypatch):
    # 正例：行内式（[E] 挂在句末标点之前，NEW_DOC 默认写法）不受这次改动影响
    assert lint_research(_new_doc(tmp_path, monkeypatch)) == []


def test_mixed_footnote_and_inline_style_do_not_crash(tmp_path, monkeypatch):
    # 混写不炸：相邻两句一句行内式、一句脚注式，都应正确归因
    doc = NEW_DOC.replace(
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。",
        "青岛保时捷中心销售一职多年负责该品牌门店业务[E1]。"
        "她自述曾经产生过轻生的念头并非虚言。[E2]",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("无 [E] 出处" in v for v in vs)


def test_missing_snapshot_warn_message_has_runnable_command(tmp_path, monkeypatch):
    # F-5：WARN 消息此前漏了 --event，实跑会直接打 usage 退出 2；命令须是绝对路径、
    # 能照抄直接跑
    from src import srcfetch

    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "empty")
    text = GOOD.replace(" — 摘录", " — 「我不认识他，他欠我一个道歉」（正文原话）")
    vs = lint_research(_mk(tmp_path, text, event="260731-1"))
    msg = next(v for v in vs if "无原文快照" in v)
    assert "--event 260731-1" in msg
    assert "/home/jc/Projects/auto-watcher/src/venv/bin/python" in msg


def test_new_format_source_line_format_hint_matches_new_format_tail(tmp_path, monkeypatch):
    # F-5：新格式的来源行提示语此前照抄旧格式的"— 摘录"结尾——新格式行尾禁止长
    # 引文（见 _lint_new_source_quotes），照它写会立刻撞上另一条闸口
    doc = NEW_DOC.replace(
        "- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（900字）",
        "- 2026.07.31，极目新闻报道了",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    msg = next(v for v in vs if "来源行格式不符" in v)
    assert "摘录" not in msg
    assert "快照" in msg


# ==================== 受控演练（260731-1）暴露的两处闸口缺口 ====================


def test_fact_quote_of_third_person_extract_passes(tmp_path, monkeypatch):
    # 演练发现（12/29 条违规）：事实层要引的大量是行政处罚决定书措辞与记者叙述，
    # 它们逐字躺在快照里、摘录层也照收了，但形态是 第三人称转述 → 此前一律判"未
    # 命中任何摘录"，没有合法出路（去掉引号＝把文书原文降格成转述，补摘录＝同一条
    # 再抄一遍改标 正文原话，等于教 agent 伪造形态）。
    # 人称篡改由逐字比对本身挡住：转述摘录里没有的第一人称引文照样落空，不需要
    # 再拿形态白名单挡一道。标题另论（见下一个用例）——媒体惯把第三人称改写成第
    # 一人称当标题，标题文本本身就可能是被制造出来的"原话"。
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]。",
        "自述「被给予行政拘留五日」[E1]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_fact_quote_of_title_extract_still_fails_after_widening(tmp_path, monkeypatch):
    # 放宽到 第三人称转述 之后，标题 必须仍然拦住——这是 F-2 当初唯一站得住的那半。
    doc = NEW_DOC.replace(
        "[E1] 信源1 · 第三人称转述 · 2026-08-07",
        "[E1] 信源1 · 标题 · 2026-08-07",
    ).replace(
        "自述曾有轻生念头[E2]。",
        "自述「被给予行政拘留五日」[E1]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_ellipsis_segments_from_third_person_extract_pass(tmp_path, monkeypatch):
    # 省略号分段回退走的是同一份 verbatim_bodies，演练里两条节略引文因此连带落空。
    doc = NEW_DOC.replace(
        "[E1] 信源1 · 第三人称转述 · 2026-08-07\n被给予行政拘留五日",
        "[E1] 信源1 · 第三人称转述 · 2026-08-07\n"
        "转发牟某文照片图文并搭配不雅视频，对其侮辱，被给予行政拘留五日",
    ).replace(
        "自述曾有轻生念头[E2]。",
        "自述「转发牟某文照片图文……对其侮辱」[E1]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_correction_trail_quote_past_sixty_chars_is_exempt(tmp_path, monkeypatch):
    # 演练发现（3/29 条）：豁免窗口 60 字符与文档规定的更正格式对不上——
    # `**更正（评审vN-问题K）**：正确表述（原错误信息：原句）` 里被推翻的旧错句
    # 结构上就排在正确表述之后，距离天然超过 60（实测 63／81／105）。旧错句按
    # 定义查不到（查得到就不叫错），窗口没盖住＝逼 agent 删掉留痕。
    trail = (
        "**更正（评审v2-问题1）**：该说法应以信源1正文为准，此前把两句掐头去尾"
        "拼接成一句并误标形态，经重新核对原文，该合并句在任何来源中均不存在"
        "（原错误信息：「我不认识他，他欠我一个道歉」）[E2]。"
    )
    doc = NEW_DOC.replace("自述曾有轻生念头[E2]。", trail)
    # 本用例要压住的是"落在标记窗口之外、靠留痕提示词豁免"这一段——距离必须真的
    # 超出 CORRECTION_LOOKBEHIND，否则测的是旧窗口、放宽与否都能过
    mark_end = trail.index("**：") + 2
    dist = trail.index("「我不认识他") - mark_end
    assert dist > 60, f"用例失去意义：距离 {dist} 仍在标记窗口内"
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("未命中任何摘录" in v for v in vs)


def test_quote_far_beyond_correction_mark_still_fails(tmp_path, monkeypatch):
    # 放宽不等于取消：标记之后隔着一大段叙述才出现的引文仍须命中摘录，否则
    # "本行开头挂过一个更正标记"就成了整行的逐字豁免。
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]。",
        "**更正（评审v2-问题1）**：该说法应以信源1正文为准。" + "补充说明。" * 32
        + "她说「我当时真的撑不下去了」[E2]。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("未命中任何摘录" in v for v in vs)


def test_quote_near_correction_mark_without_trail_cue_still_fails(tmp_path, monkeypatch):
    # 演练实测：把标记窗口放宽到 150 会顺带豁免掉挨着更正标记的标签化引号（研究者
    # 拿引号当标注用的那类，本该拦）。豁免改挂"留痕提示词"而不是字符数，就是为了
    # 分开这两者——同样距标记 60~150 字符、但前面没有提示词的引文必须仍然 FAIL。
    trail = (
        "**更正（评审v2-问题1）**：该说法应以信源1正文为准，此处的处置意见与本站既有"
        "表述一致，经复核无需改动，相关判断已在评审第三轮记录在案，另附一句说明"
        "「我当时真的撑不下去了」[E2]。"
    )
    # 距离必须落在 (60, 150]：60 以内会被原有的标记窗口豁免（测不到本用例的点），
    # 超过 150 则连被否掉的"放宽到 150"方案也能过，同样测不出两者的差别
    mark_end = trail.index("**：") + 2
    dist = trail.index("「我当时") - mark_end
    assert 60 < dist <= 150, f"用例失去意义：距离 {dist} 不在区分区间内"
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc := NEW_DOC.replace(
        "自述曾有轻生念头[E2]。", trail)))
    assert any("未命中任何摘录" in v for v in vs)


def test_multi_sentence_quote_is_not_split_apart(tmp_path, monkeypatch):
    # 演练发现（剩余 2/29 条）：切句用 (?<=[。！？]) 不认引号嵌套，跨句的逐字引语
    # 会被切成两半，前半截判"无 [E] 出处"。两条出路都不通——把 [E] 焊进引语内部
    # ＝污染原文（演练里 agent 先这么干了，被自己发现改回），把长引语拆成两段各挂
    # 一个 [E] ＝伪造出两句从未分开说过的话。逐字引语跨句是常态，不该由它买单。
    quote = "我正常的工作都已经没有办法去进行了。我有一度想从这个楼上我就直接跳下去了"
    doc = NEW_DOC.replace(
        "[E2] 信源1 · 正文原话 · 2026-08-07\n我有一度想从这个楼上我就直接跳下去了",
        f"[E2] 信源1 · 正文原话 · 2026-08-07\n{quote}",
    ).replace("自述曾有轻生念头[E2]。", f"她说「{quote}」[E2]。")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc, snap=f"她说 {quote}"))
    assert not any("无 [E] 出处" in v for v in vs)


def test_plain_second_sentence_without_mark_still_fails(tmp_path, monkeypatch):
    # 守护：不许因为上一条就把句级归因整个关掉——引号外的第二句缺 [E] 仍须 FAIL
    doc = NEW_DOC.replace(
        "自述曾有轻生念头[E2]。",
        "自述曾有轻生念头[E2]。她随后向警方报案并提交了相关证据材料。",
    )
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("无 [E] 出处" in v for v in vs)


def test_empty_narrative_section_fails_new_format(tmp_path, monkeypatch):
    # 260804-3 实测：`## 当事方` 整节留空仍拿 LINT OK——REQUIRED 只核标题在不在，
    # 孤儿检查按 [E] 编号算（E2 只要在 `## 事实` 里被引用过就不算孤儿），两道闸口
    # 叠起来盖不住空节。后果是家属表态一类只在摘录里逐字躺着的材料整批不进草稿：
    # 写手的叙述只取 `## 事实`／`## 当事方` 两节。
    doc = NEW_DOC.replace(
        "**牟倩文**：青岛保时捷中心销售，自述曾有轻生念头[E2]。", "")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("当事方" in v and "空节" in v for v in vs)


def test_empty_narrative_section_fails_legacy(tmp_path):
    vs = lint_research(_mk(tmp_path, GOOD.replace("## 当事方\n某人\n", "## 当事方\n")))
    assert any("当事方" in v and "空节" in v for v in vs)


def test_whitespace_only_narrative_section_fails(tmp_path):
    vs = lint_research(_mk(tmp_path, GOOD.replace("## 当事方\n某人\n", "## 当事方\n   \n")))
    assert any("当事方" in v and "空节" in v for v in vs)


def test_whole_page_dumped_as_one_extract_fails(tmp_path, monkeypatch):
    # 260804-3 实测：5 条摘录就是 5 篇整文（占各自快照 73%–98%），一个 [E] 覆盖整篇。
    # 叙述层挂 [E2][E4] 时并没有定位到具体段落，逐字闸口只能核"在不在这篇文章里"。
    long_body = "他表示这是一起生活琐事引发的连续冲突，两次冲突升级间隔极短，应当整体评判。" * 12
    doc = NEW_DOC.replace("被给予行政拘留五日", long_body)
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc, snap=long_body + "另有少量无关内容。"))
    assert any("[E1]" in v and "整篇" in v for v in vs)


def test_long_extract_that_is_a_small_part_of_the_page_passes(tmp_path, monkeypatch):
    # 守护：长引文本身不是错——占比低说明它是从长文里摘的一段，正是要的形态
    long_body = "他表示这是一起生活琐事引发的连续冲突，两次冲突升级间隔极短，应当整体评判。" * 12
    doc = NEW_DOC.replace("被给予行政拘留五日", long_body)
    snap = long_body + "无关内容。" * 400
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc, snap=snap))
    assert not any("整篇" in v for v in vs)


def test_short_page_quoted_in_full_passes(tmp_path, monkeypatch):
    # 守护：短通报/短帖逐字全引是正当写法，不该因"占比高"被拦
    vs = lint_research(_new_doc(tmp_path, monkeypatch))
    assert not any("整篇" in v for v in vs)


def test_all_sources_reposts_without_note_fails(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("极目新闻。", "赣南日报（转载自极目新闻）。")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert any("原件未取" in v for v in vs)


def test_all_sources_reposts_with_note_passes(tmp_path, monkeypatch):
    doc = NEW_DOC.replace("极目新闻。", "赣南日报（转载自极目新闻）。").replace(
        "## 事实", "原件未取：极目新闻原页面已下架，仅存转载版。\n\n## 事实")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("原件未取" in v for v in vs)


def test_one_primary_source_among_reposts_passes(tmp_path, monkeypatch):
    doc = NEW_DOC.replace(
        "## 摘录",
        "- 2026.07.31，赣南日报（转载自极目新闻）。*乙*。https://a.example/2 — 快照失败：反爬\n\n## 摘录")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("原件未取" in v for v in vs)


def test_no_original_note_accepts_bold_house_style(tmp_path, monkeypatch):
    # 留痕惯例是把冒号放在加粗之外（`**补充（评审vN-问题K）**：`），闸口不能被一对星号卡死
    doc = NEW_DOC.replace("极目新闻。", "赣南日报（转载自极目新闻）。").replace(
        "## 事实", "**原件未取**：原页面已下架，仅存转载版。\n\n## 事实")
    vs = lint_research(_new_doc(tmp_path, monkeypatch, doc))
    assert not any("原件未取" in v for v in vs)
