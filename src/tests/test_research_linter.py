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

def test_assets_bidirectional(tmp_path):
    listed = GOOD.replace("## 资产\n无\n", "## 资产\n- 990101-1-图.jpg — https://a — 2026.1.1 — 通报截图\n")
    vs = lint_research(_mk(tmp_path, listed, assets=[]))          # 登记了但文件不存在
    assert any("不存在" in v for v in vs)
    vs2 = lint_research(_mk(tmp_path, GOOD, assets=["990101-1-孤儿.jpg"]))  # 存在但未登记
    assert any("未登记" in v for v in vs2)
