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
