from pathlib import Path

from src.utils.research_doc import Source, event_of, sections, sources

DOC = """# Research: 标题 (260731, #1)

## 事实
- 2025.10.12：李沧分局作出行拘5日决定[E8]。

## 信息来源
- 2026.07.31，极目新闻（记者柳琛琛）。*起诉造黄谣者*。https://a.example/1 — 快照 2026-08-07（4211字）
- 2026.07.31，某站。*另一篇*。https://b.example/2 — 快照失败：25s 无响应

## 摘录
[E8] 信源1 · 第三人称转述 · 2026-08-07
被给予行政拘留五日
"""


def test_sections_splits_on_h2():
    secs = sections(DOC)
    assert set(secs) == {"事实", "信息来源", "摘录"}
    assert "李沧分局" in secs["事实"]


def test_sources_are_numbered_in_document_order():
    ss = sources(DOC)
    assert [s.num for s in ss] == [1, 2]
    assert ss[0].url == "https://a.example/1"
    assert ss[0].name == "极目新闻（记者柳琛琛）"
    assert ss[0].title == "起诉造黄谣者"
    assert ss[0].date == "2026.07.31"


def test_snapshot_failed_is_read_off_the_tail():
    ss = sources(DOC)
    assert ss[0].snapshot_failed is False
    assert ss[1].snapshot_failed is True


def test_sources_empty_when_section_absent():
    assert sources("# Research\n\n## 事实\n无。\n") == []


def test_event_of_strips_title_and_version():
    assert event_of(Path("_pipeline/research/260731-1-保时捷女销冠遭造谣网暴.md")) == "260731-1"
    assert event_of(Path("_pipeline/review/260731-10-某标题-v3.md")) == "260731-10"


from src.utils.research_doc import Extract, extracts, is_new_format, malformed_extract_heads

EXTRACT_DOC = """## 信息来源
- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照 2026-08-07（4211字）

## 摘录
[E1] 信源1 · 正文原话 · 2026-08-07
我不认识他，他从没联系过我
[E2] 信源1 · 第三人称转述 · 2026-08-07
青岛市公安局李沧分局行政处罚决定书显示，
一男子在群内转发牟某文照片搭配不雅视频
[E12] 资产 260731-1-立案截图.jpg · 图上转录 · —
案由：名誉权纠纷　状态：待审核
"""


def test_extracts_parse_header_and_body():
    es = extracts(EXTRACT_DOC)
    assert [e.eid for e in es] == [1, 2, 12]
    assert es[0].ref == "信源1" and es[0].form == "正文原话"
    assert es[0].body == "我不认识他，他从没联系过我"
    assert es[0].fetched == "2026-08-07"


def test_multiline_extract_body_is_joined():
    # 摘录正文可换行排版；比对时要当作一段，否则长引文永远核不过
    e = [x for x in extracts(EXTRACT_DOC) if x.eid == 2][0]
    assert e.body == "青岛市公安局李沧分局行政处罚决定书显示， 一男子在群内转发牟某文照片搭配不雅视频"


def test_asset_transcription_ref_is_kept_verbatim():
    e = [x for x in extracts(EXTRACT_DOC) if x.eid == 12][0]
    assert e.ref == "资产 260731-1-立案截图.jpg" and e.form == "图上转录"


def test_extracts_empty_when_section_absent():
    assert extracts("## 事实\n无。\n") == []


def test_is_new_format_keys_on_the_extract_section():
    # 新旧分派的唯一判据：在途事件不带 ## 摘录，照旧规则收尾
    assert is_new_format(EXTRACT_DOC) is True
    assert is_new_format("## 事实\n无。\n\n## 信息来源\n- 略\n") is False


# ---- 第二轮修复：畸形标签必须响，不能被吞进上一条摘录的 body ----

MISATTACH_DOC = """## 摘录
[E1] 信源1 · 正文原话 · 2026-08-07
她说她不认识对方

[E2]信源2 · 正文原话 · 2026-08-07
警方通报称视频系拼接
"""


def test_malformed_head_does_not_leak_body_into_prior_extract():
    # 最重要的一条：]后缺空格的 [E2] 解析不出来时，它的正文不能被并进 E1——
    # 那样闸口逐字核对会拿 E1 的身份核过 E2 的引文，命中的却是错的一条。
    es = extracts(MISATTACH_DOC)
    assert [e.eid for e in es] == [1]
    assert es[0].body == "她说她不认识对方"
    assert "警方通报称视频系拼接" not in es[0].body


def test_malformed_extract_heads_flags_common_typos():
    doc = """## 摘录
[E1] 信源1·正文原话·2026-08-07
甲
[E2]信源2 · 正文原话 · 2026-08-07
乙
- [E3] 信源3 · 正文原话 · 2026-08-07
丙
[E4a] 信源4 · 正文原话 · 2026-08-07
丁
"""
    heads = malformed_extract_heads(doc)
    assert len(heads) == 4
    assert "[E1]" in heads[0]   # · 两侧缺空格
    assert "[E2]" in heads[1]   # ] 后缺空格
    assert "[E3]" in heads[2]   # 行首多了 "- " 列表前缀
    assert "[E4a]" in heads[3]  # eid 非纯数字


def test_malformed_extract_heads_empty_for_well_formed_doc():
    assert malformed_extract_heads(EXTRACT_DOC) == []


def test_inline_e_reference_in_body_not_flagged_as_malformed_head():
    # 正文里的 [E99] 引用不在行首，不能被 LOOSE_HEAD_RE 误判成畸形标签
    doc = """## 摘录
[E1] 信源1 · 正文原话 · 2026-08-07
参见[E99]相关表述
"""
    assert malformed_extract_heads(doc) == []
    es = extracts(doc)
    assert len(es) == 1
    assert es[0].body == "参见[E99]相关表述"


# ---- fix 轮 1：全角方括号标签、SRC_PARSE_RE 贪婪吃 URL（两处结转的真缺口） ----

def test_fullwidth_bracket_head_is_flagged_not_swallowed_into_prior_body():
    # 中文输入法全角/半角切换下默认敲出的就是全角方括号「［］」，不是边缘输入。
    # LOOSE_HEAD_RE 若只认半角 [，这行既不匹配 EXTRACT_HEAD_RE 也不匹配 LOOSE_HEAD_RE，
    # 会被当成普通正文并入上一条摘录的 body——Task 4 修过的同一种误挂，原样在全角上复现。
    doc = """## 摘录
[E1] 信源1 · 正文原话 · 2026-08-07
她说她不认识对方
［E2］ 信源2 · 正文原话 · 2026-08-07
警方通报称视频系拼接
"""
    es = extracts(doc)
    assert [e.eid for e in es] == [1]
    assert es[0].body == "她说她不认识对方"
    assert "警方通报称视频系拼接" not in es[0].body
    heads = malformed_extract_heads(doc)
    assert len(heads) == 1
    assert "［E2］" in heads[0]


def test_sources_url_stops_before_glued_snapshot_failed_tag():
    # " — " 缺空格时（如 "URL—快照失败：..."）旧正则的 (\S+) 会把破折号后的内容整段
    # 吞进 URL，snapshot_failed 因此被静默判成 False。这里解析出的 Source 直接喂给
    # srcfetch --from-research（研究阶段跑它时文件还没被 research_linter lint 过），
    # 静默口子不能只靠下游 linter 挡。
    doc = ("## 信息来源\n"
           "- 2026.07.31，某站。*标题甲*。https://a.example/1—快照失败：25s无响应\n")
    ss = sources(doc)
    assert ss[0].url == "https://a.example/1"
    assert ss[0].snapshot_failed is True


# ---- fix 轮 2（评审 I-1）：「发布日期查证失败」来源行不再让信源编号整体错位 ----

def test_unverified_date_marker_source_line_parses_as_a_real_source():
    # 日期字段放宽为"日期 或 发布日期查证失败（可带括注）"之前，这种行（agent 文件
    # 明文支持的写法，本仓库存量语料里有 17 条、分布 7 份文件）完全解析不出 Source，
    # 它之后每一条来源的 num 都会集体错一位——摘录写"信源N"引用的其实是下一条来源，
    # 转载为主的语料里"拿错来源的快照去核"极大概率核得过，闸口全程沉默。
    doc = ("## 信息来源\n"
           "- 2026.07.31，甲媒体。*标题甲*。https://a.example/a — 快照 2026-08-07（100字）\n"
           "- 发布日期查证失败（页面未展示可核实日期），乙媒体。*标题乙*。"
           "https://b.example/b — 快照 2026-08-07（100字）\n"
           "- 2026.07.31，丙媒体。*标题丙*。https://c.example/c — 快照 2026-08-07（100字）\n")
    ss = sources(doc)
    assert [s.num for s in ss] == [1, 2, 3]
    assert ss[1].date == "发布日期查证失败（页面未展示可核实日期）"
    assert ss[2].url == "https://c.example/c"  # 第三条编号仍是 3，不是错位后的 2


def test_unverified_date_marker_without_parenthetical_still_parses():
    # 括注是可选的——裸「发布日期查证失败」不带 （…） 也要能解析
    doc = "## 信息来源\n- 发布日期查证失败，甲媒体。*标题甲*。https://a.example/a — 摘录\n"
    ss = sources(doc)
    assert len(ss) == 1 and ss[0].date == "发布日期查证失败"


def test_unverified_date_marker_parenthetical_with_comma_not_truncated():
    # 括注里可能有中文逗号——不能用 [^，]* 之类会在第一个逗号处截断的写法
    doc = ("## 信息来源\n"
           "- 发布日期查证失败（当事方提供，无公开发布记录），甲媒体。*标题甲*。"
           "https://a.example/a — 摘录\n")
    ss = sources(doc)
    assert len(ss) == 1
    assert ss[0].date == "发布日期查证失败（当事方提供，无公开发布记录）"
