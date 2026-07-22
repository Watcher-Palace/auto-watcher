import pytest
from pathlib import Path
from src.research_linter import lint_research

GOOD = ("# Research: 题 (990101, #1)\n\n## 事实\n"
        "<font color=\"blue\">2026年1月1日宣判</font>\n\n## 当事方\n某人\n\n"
        "## 信息来源\n- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录\n\n## 资产\n无\n")

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
        "- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录", "- 澎湃新闻报道了")
    vs = lint_research(_mk(tmp_path, text))
    assert any("当事方" in v for v in vs) and any("来源行" in v for v in vs)

def test_source_line_allows_unverified_date_marker(tmp_path):
    text = GOOD.replace("- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录",
                        "- 澎湃新闻。*真标题*。https://a/b — 摘录（发布日期查证失败）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_blue_mark_rules(tmp_path):
    no_date = GOOD.replace("2026年1月1日宣判", "已经宣判")
    stale = GOOD.replace("2026年1月1日宣判", "截至2026年1月1日暂无进展")
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, no_date)))
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, stale)))

def test_assets_bidirectional(tmp_path):
    listed = GOOD.replace("## 资产\n无\n", "## 资产\n- 990101-1-图.jpg — https://a — 2026.1.1 — 通报截图\n")
    vs = lint_research(_mk(tmp_path, listed, assets=[]))          # 登记了但文件不存在
    assert any("不存在" in v for v in vs)
    vs2 = lint_research(_mk(tmp_path, GOOD, assets=["990101-1-孤儿.jpg"]))  # 存在但未登记
    assert any("未登记" in v for v in vs2)
