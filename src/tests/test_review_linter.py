"""Tests for src/review_linter.py — hermetic, fixture strings only."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src import srcfetch
from src.review_linter import (
    parse_review, validate_format, validate_anchors,
    check_marks, check_dispositions, check_tag_proposals, check_snapshots,
)

VALID = """STATUS: ISSUES

## 问题 1
类型：事实
原文：`法院一审判处王某有期徒刑三年`
<!-- [REVIEWER]: 判决为二审，请核对 -->
处理：

## 问题 2
类型：格式
原文：`此事沉寂数月后再度引发关注`
<!-- [REVIEWER]: 删除填充语 -->
处理：
"""

CLEAN = "STATUS: CLEAN\n"

DRAFT = """---
title: test
---
正文开始。法院一审判处王某有期徒刑三年。
此事沉寂数月后再度引发关注。结束。
"""


def test_parse_review_items():
    r = parse_review(VALID)
    assert r.status == "ISSUES"
    assert [i.num for i in r.items] == [1, 2]
    assert r.items[0].type == "事实"
    assert r.items[0].quote == "法院一审判处王某有期徒刑三年"
    assert r.items[0].disposition == ""


def test_validate_format_valid():
    assert validate_format(VALID) == []
    assert validate_format(CLEAN) == []


def test_validate_format_bad_status():
    assert validate_format("STATUS: OK\n") != []
    assert validate_format("## 问题 1\n") != []  # missing STATUS line


def test_validate_format_clean_with_items():
    bad = CLEAN + "\n## 问题 1\n类型：事实\n原文：`x`\n处理：\n"
    assert validate_format(bad) != []


def test_validate_format_issues_with_zero_items():
    bad = "STATUS: ISSUES\n"
    assert validate_format(bad) != []


def test_validate_format_gap_in_numbering():
    bad = VALID.replace("## 问题 2", "## 问题 3")
    assert any("问题" in v for v in validate_format(bad))


def test_validate_format_missing_type_and_quote():
    bad = "STATUS: ISSUES\n\n## 问题 1\n原文：`x`\n处理：\n"
    assert validate_format(bad) != []  # no 类型
    bad2 = "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n处理：\n"
    assert validate_format(bad2) != []  # no 原文
    bad3 = "STATUS: ISSUES\n\n## 问题 1\n类型：意见\n原文：`x`\n处理：\n"
    assert validate_format(bad3) != []  # invalid 类型 value


def test_validate_anchors():
    assert validate_anchors(VALID, DRAFT) == []
    missing = VALID.replace("法院一审判处王某有期徒刑三年", "不存在的原文")
    assert validate_anchors(missing, DRAFT) != []


def test_check_marks():
    research_ok = "## 事实\n**更正（评审v1-问题1）**：二审改判。（原错误信息：一审判决）\n"
    assert check_marks(VALID, research_ok, 1) == []
    # 问题2 is 格式 — needs no mark; 问题1 unmarked fails:
    assert check_marks(VALID, "## 事实\n无标记\n", 1) != []
    # wrong version does not count:
    assert check_marks(VALID, "**更正（评审v2-问题1）**：x", 1) != []
    # 已删除（用户裁定）的事实项不补研究，不该再要求研究文件标记
    ruled = VALID.replace("处理：\n\n## 问题 2", "处理：已删除（用户裁定）\n\n## 问题 2")
    assert check_marks(ruled, "## 事实\n无标记\n", 1) == []


def test_check_dispositions():
    violations, unresolved = check_dispositions(VALID)
    assert violations != []  # empty 处理 lines
    done = VALID.replace("处理：\n\n## 问题 2", "处理：已修改\n\n## 问题 2")
    done = done[: done.rfind("处理：")] + "处理：拒绝：原文准确\n"
    violations, unresolved = check_dispositions(done)
    assert violations == [] and unresolved is False
    unres = done.replace("处理：已修改", "处理：未解决：研究文件无对应裁定")
    violations, unresolved = check_dispositions(unres)
    assert violations == [] and unresolved is True


def test_check_dispositions_vocabulary():
    # arbitrary string not in the vocabulary → violation
    arb = VALID.replace("处理：\n\n## 问题 2", "处理：随便写\n\n## 问题 2")
    arb = arb[: arb.rfind("处理：")] + "处理：已修改\n"
    violations, unresolved = check_dispositions(arb)
    assert violations != [] and unresolved is False

    # bare 拒绝： without a reason → violation
    bare_reject = VALID.replace("处理：\n\n## 问题 2", "处理：拒绝：\n\n## 问题 2")
    bare_reject = bare_reject[: bare_reject.rfind("处理：")] + "处理：已修改\n"
    violations, _ = check_dispositions(bare_reject)
    assert violations != []

    # bare 未解决： without an explanation → violation, NOT unresolved
    bare_unres = VALID.replace("处理：\n\n## 问题 2", "处理：未解决：\n\n## 问题 2")
    bare_unres = bare_unres[: bare_unres.rfind("处理：")] + "处理：已修改\n"
    violations, unresolved = check_dispositions(bare_unres)
    assert violations != [] and unresolved is False

    # 已删除（查证失败） is valid
    deleted = VALID.replace(
        "处理：\n\n## 问题 2", "处理：已删除（查证失败）\n\n## 问题 2")
    deleted = deleted[: deleted.rfind("处理：")] + "处理：已修改\n"
    violations, unresolved = check_dispositions(deleted)
    assert violations == [] and unresolved is False

    # 已删除（用户裁定） is valid too — 用户裁定删除内容，非查证失败
    ruled = VALID.replace(
        "处理：\n\n## 问题 2", "处理：已删除（用户裁定）\n\n## 问题 2")
    ruled = ruled[: ruled.rfind("处理：")] + "处理：已修改\n"
    violations, unresolved = check_dispositions(ruled)
    assert violations == [] and unresolved is False


def test_cli_exit_codes(tmp_path):
    review_dir = tmp_path / "review"
    draft_dir = tmp_path / "draft"
    review_dir.mkdir(); draft_dir.mkdir()
    rp = review_dir / "260701-1-测试-v1.md"
    (draft_dir / "260701-1-测试-v1.md").write_text(DRAFT, encoding="utf-8")

    rp.write_text(VALID, encoding="utf-8")
    ok = subprocess.run([sys.executable, "src/review_linter.py", str(rp)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr

    rp.write_text(VALID.replace("法院一审判处王某有期徒刑三年", "不存在"),
                  encoding="utf-8")
    bad = subprocess.run([sys.executable, "src/review_linter.py", str(rp)],
                         capture_output=True, text=True)
    assert bad.returncode == 1

    done = VALID.replace("处理：\n\n## 问题 2", "处理：已修改\n\n## 问题 2")
    done = done[: done.rfind("处理：")] + "处理：未解决：无裁定\n"
    rp.write_text(done, encoding="utf-8")
    un = subprocess.run(
        [sys.executable, "src/review_linter.py", str(rp), "--check-dispositions"],
        capture_output=True, text=True)
    assert un.returncode == 2


def test_cli_default_mode_requires_review_dir_bare_filename(tmp_path):
    """回归：裸文件名（路径中无 /review/ 段）此前会让 draft == review_path 本身，
    锚点检查对自身逐字通过，静默放行。修复后必须报违规而非 exit 0。"""
    script = Path(__file__).parent.parent.parent / "src" / "review_linter.py"
    rp = tmp_path / "260701-1-测试-v1.md"  # not nested under a review/ dir
    rp.write_text(VALID, encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(script), rp.name],
        capture_output=True, text=True, cwd=tmp_path)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "review/" in "".join(bad.stdout)


def test_tag_proposals_must_transcribe():
    draft = "---\ntags:\n---\n<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n正文"
    review_missing = "STATUS: CLEAN\n"
    review_ok = "STATUS: CLEAN\n\n## 标签提案\n- 新标签 — 理由\n"
    assert any("新标签" in v for v in check_tag_proposals(review_missing, draft))
    assert check_tag_proposals(review_ok, draft) == []


def test_cli_default_mode_absolute_review_path_still_passes(tmp_path):
    """既有绝对路径调用（review_path.parent.name == "review"）修复后仍应正常通过。"""
    review_dir = tmp_path / "review"
    draft_dir = tmp_path / "draft"
    review_dir.mkdir(); draft_dir.mkdir()
    rp = review_dir / "260701-1-测试-v1.md"
    (draft_dir / "260701-1-测试-v1.md").write_text(DRAFT, encoding="utf-8")
    rp.write_text(VALID, encoding="utf-8")
    ok = subprocess.run([sys.executable, "src/review_linter.py", str(rp)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_source_line_anchor_typed_geshi_warns():
    # 来源行三样错的修复点在研究文件，定成 格式 会绕过补研究闸口 → WARN（2026-08-05）
    text = VALID.replace("原文：`此事沉寂数月后再度引发关注`",
                         "原文：`2026.06.01，搜狐。*标题*。https://a`")
    vs = validate_format(text)
    assert any(v.startswith("WARN：") and "来源行" in v for v in vs)
    assert all(v.startswith("WARN：") for v in vs)   # 仅告警，无阻断违规


def test_source_line_anchor_typed_shishi_no_warn():
    text = VALID.replace(
        "类型：事实\n原文：`法院一审判处王某有期徒刑三年`",
        "类型：事实\n原文：`2026.06.01，搜狐。*标题*。https://a`")
    assert validate_format(text) == []


REVIEW_WITH_COUNTER_SOURCE = """STATUS: ISSUES

## 问题 1
类型：事实
原文：`被行拘后未道歉`
<!-- [REVIEWER]: 羊城晚报原文记载该男子已手写悔过书致歉，见 https://c.example/9 -->
处理：
"""


def test_fact_item_citing_an_external_url_needs_a_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    vs = check_snapshots(REVIEW_WITH_COUNTER_SOURCE, "260731-1")
    assert any("无快照" in v and "c.example/9" in v for v in vs)


def test_snapshotted_counter_source_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    p = srcfetch.snapshot_path("https://c.example/9", "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n手写悔过书", encoding="utf-8")
    assert check_snapshots(REVIEW_WITH_COUNTER_SOURCE, "260731-1") == []


def test_url_in_the_anchor_line_is_not_scanned(tmp_path, monkeypatch):
    # 来源行锚点类事实项的 原文： 本就含 URL（草稿自己的来源），扫它是纯假阳性
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n"
        "原文：`- 2026.07.31，极目新闻。*甲*。https://a.example/1`\n"
        "<!-- [REVIEWER]: 该行署名与页面不符，请回研究阶段核实 -->\n处理：\n"
    )
    assert check_snapshots(review, "260731-1") == []


def test_format_items_are_not_scanned(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = REVIEW_WITH_COUNTER_SOURCE.replace("类型：事实", "类型：格式")
    assert check_snapshots(review, "260731-1") == []


def test_url_followed_by_paren_annotation_is_not_swallowed(tmp_path, monkeypatch):
    # 回归：评审散文里 URL 后常紧跟"（来源名）"标注（如 260731-1 v3 问题 3 的真实写法）。
    # 排除集此前只挡了右括号，左括号不挡时会把"（新浪财经"整段吞进"URL"，快照哈希
    # 从此对不上任何一次真实抓取——不管替那个真 URL 抓多少次快照都无法通过。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
        "<!-- [REVIEWER]: 真实出处为 https://c.example/9（新浪财经）而非此处 -->\n"
        "处理：\n"
    )
    p = srcfetch.snapshot_path("https://c.example/9", "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n手写悔过书", encoding="utf-8")
    assert check_snapshots(review, "260731-1") == []


# fix 轮 1（评审 C-1）：URL 边界判定的形态逐条钉死，不许再退化成"撞一个补一个"的
# 手工排除集。9 条同一干净 URL（https://c.example/9）配不同的中文/通用标点尾巴。
URL_BOUNDARY_TRAILERS = [
    "见 https://c.example/9——现已无法访问",     # 中文破折号 U+2014
    "见《报道》https://c.example/9》",           # 书名号 U+300B
    "见 https://c.example/9；另见其他说法",       # 全角分号 U+FF1B
    "见 https://c.example/9：正文称如此",         # 全角冒号 U+FF1A
    "见 https://c.example/9“原话”如下",           # 弯引号 U+201C/D
    "见 https://c.example/9·补充说明",            # 中点 U+00B7
    "见 https://c.example/9……仍在核实",           # 省略号 U+2026
    "见 https://c.example/9（新浪财经）报道",      # 全角括号标注（上一轮已修，钉住不回归）
    "见 https://c.example/9。到此为止",           # 全角句号 U+3002
    "见 (https://c.example/9) 的记录",           # 半角括号包裹，尾括号不配平须剥
]


def test_url_boundary_trailers_all_extract_the_clean_url(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    p = srcfetch.snapshot_path("https://c.example/9", "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n正文", encoding="utf-8")
    for comment in URL_BOUNDARY_TRAILERS:
        review = (
            "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
            f"<!-- [REVIEWER]: {comment} -->\n处理：\n"
        )
        assert check_snapshots(review, "260731-1") == [], f"应放行：{comment!r}"


def test_bare_paren_wrapped_url_strips_trailing_paren_not_matches_dirty_form(
    tmp_path, monkeypatch
):
    # "(URL)" 场景需双向钉住：上一条测试已证明干净 URL 有快照时放行；这里证明只在
    # 带着尾括号的脏字符串"URL)"下存快照**不能**放行——不然可能是巧合两边都宽松通过，
    # 不是真的在剥括号。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
        "<!-- [REVIEWER]: 见 (https://c.example/9) 的记录 -->\n处理：\n"
    )
    p = srcfetch.snapshot_path("https://c.example/9)", "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n正文", encoding="utf-8")
    vs = check_snapshots(review, "260731-1")
    assert any("无快照" in v for v in vs)


def test_wikipedia_style_balanced_parens_url_preserved_in_full(tmp_path, monkeypatch):
    # 方向①（评审场景2）：URL 内部合法带配平的 (...) 时必须完整保留——上一轮补的
    # ASCII 左括号排除曾把这类 URL 从中间反向截断（.../水星_(行星) → .../水星_）。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    full_url = "https://zh.wikipedia.org/wiki/水星_(行星)"
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
        f"<!-- [REVIEWER]: 见 {full_url} 的条目 -->\n处理：\n"
    )
    p = srcfetch.snapshot_path(full_url, "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n正文", encoding="utf-8")
    assert check_snapshots(review, "260731-1") == []


def test_wikipedia_style_url_not_silently_truncated(tmp_path, monkeypatch):
    # 方向②：即便括号被切掉后的残缺 URL 恰好也存了快照，也不该被那份快照放行——
    # 证明抽取的确实是完整 URL，不是恰好两边都宽松到能通过。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    full_url = "https://zh.wikipedia.org/wiki/水星_(行星)"
    truncated_url = "https://zh.wikipedia.org/wiki/水星_"
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
        f"<!-- [REVIEWER]: 见 {full_url} 的条目 -->\n处理：\n"
    )
    p = srcfetch.snapshot_path(truncated_url, "260731-1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# SOURCE: x\n# FETCHED: y\n\n正文", encoding="utf-8")
    vs = check_snapshots(review, "260731-1")
    assert any("无快照" in v and full_url in v for v in vs)


def test_same_url_across_two_reviewer_comments_in_one_item_reported_once(
    tmp_path, monkeypatch
):
    # fix 轮 1（评审 M-1）：去重范围从"单条注释"提到"整个问题项"。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = (
        "STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n"
        "<!-- [REVIEWER]: 见 https://c.example/9 -->\n"
        "<!-- [REVIEWER]: 另见 https://c.example/9 -->\n处理：\n"
    )
    vs = check_snapshots(review, "260731-1")
    assert len(vs) == 1


def test_same_url_across_two_problem_items_reported_per_item(tmp_path, monkeypatch):
    # 不跨问题项去重：两个问题各自引同一 URL，处理的是不同问题，本来就该各报一条。
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    review = (
        "STATUS: ISSUES\n\n"
        "## 问题 1\n类型：事实\n原文：`x`\n"
        "<!-- [REVIEWER]: 见 https://c.example/9 -->\n处理：\n\n"
        "## 问题 2\n类型：事实\n原文：`y`\n"
        "<!-- [REVIEWER]: 见 https://c.example/9 -->\n处理：\n"
    )
    vs = check_snapshots(review, "260731-1")
    assert len(vs) == 2
    assert any(v.startswith("问题 1:") for v in vs)
    assert any(v.startswith("问题 2:") for v in vs)
