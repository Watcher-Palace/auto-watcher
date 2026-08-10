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


from src.utils.research_doc import Extract, extracts, is_new_format

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
