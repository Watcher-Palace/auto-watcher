"""Tests for src/review_linter.py — hermetic, fixture strings only."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.review_linter import (
    parse_review, validate_format, validate_anchors,
    check_marks, check_dispositions,
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
