# Single-Owner Fact Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the blog pipeline so the researcher (Sonnet) owns the fact base end-to-end, the writer becomes a web-less pure-prose agent, the review format is hardened and machine-validated, and protocol compliance moves from model discipline into code.

**Architecture:** Three stage roles migrate from skills to self-contained `.claude/agents/` definitions with harness-pinned tools/models. A new `src/review_linter.py` validates the hardened review format (verbatim anchors, fact-base marks, dispositions). The publisher gains pre-flight checks; skills are renamed to verb form.

**Tech Stack:** Python 3 (stdlib + existing repo utils), pytest, Claude Code agents/skills (markdown), JSON settings.

**Spec:** `docs/superpowers/specs/2026-07-15-fact-ownership-design.md`

## Global Constraints

- Repo root: `/home/jc/Projects/auto-watcher`. Solo repo — commit directly to `main` after each task.
- venv lives at `src/venv/` (NOT `.venv/`). Run tests as: `source src/venv/bin/activate && python -m pytest src/tests/ -q`. Tests must stay hermetic (no network, no `claude` CLI).
- Never touch `src/.env`; never commit env files.
- Research files are written entirely in Simplified Chinese (英文仅限专名).
- Naming convention: skills are verb-form (`blog-orchestrate`, `blog-summarize`, `blog-curate`), agents are actor-form (`blog-researcher`, `blog-writer`, `blog-reviewer`).
- Fact-base mark vocabulary (exact strings): `**补充（评审vN-问题K）**：`, `**更正（评审vN-问题K）**：…（原错误信息：…）`, `**查证失败（评审vN-问题K）**：`.
- Disposition vocabulary (exact strings on the `处理：` line): `已修改`, `拒绝：<理由>`, `已删除（查证失败）`, `未解决：<缺口说明>`.
- Review file contract (canonical; used by Tasks 1, 3, 8):
  - Line 1 exactly `STATUS: CLEAN` or `STATUS: ISSUES`.
  - Each issue: `## 问题 K` (K consecutive from 1), then a `类型：事实` or `类型：格式` line, then `原文：` followed by a backtick-wrapped verbatim quote from the draft, then one or more `<!-- [REVIEWER]: ... -->` lines, then a `处理：` line (empty until revision).
  - Other sections (`## 标签提案`, `## 人类意见`) may follow and are ignored by validation.
- Review/draft pairing: review `_pipeline/review/{date}-{n}-{title}-v{V}.md` pairs with draft `_pipeline/draft/{date}-{n}-{title}-v{V}.md` (same filename, `review`→`draft` directory swap).
- Do NOT edit `_pipeline/events.csv` directly and do not change `src/utils/ledger.py`.
- CLAUDE.md's anti-drift rule applies: when this plan changes behavior documented in CLAUDE.md or a SKILL.md, that file is updated in the same task.

---

### Task 1: `src/review_linter.py` — review format validator

**Files:**
- Create: `src/review_linter.py`
- Test: `src/tests/test_review_linter.py`

**Interfaces:**
- Produces (used by Tasks 2, 3, and agent gate commands):
  - `parse_review(text: str) -> Review` where `Review(status: str | None, items: list[Item])`, `Item(num: int, type: str | None, quote: str | None, disposition: str | None)`
  - `validate_format(text: str) -> list[str]` — contract violations (empty = valid)
  - `validate_anchors(text: str, draft_text: str) -> list[str]`
  - `check_marks(text: str, research_text: str, version: int) -> list[str]`
  - `check_dispositions(text: str) -> tuple[list[str], bool]` — (violations, has_unresolved)
  - CLI: `python src/review_linter.py <review-path>` (format+anchors, draft derived by directory swap), `--check-marks <research-path>` (format+marks, version from filename `-vN`), `--check-dispositions` (format+dispositions). Exit 0 = pass, 1 = violations, 2 = dispositions mode only: no violations but `未解决` present.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python -m pytest src/tests/test_review_linter.py -q`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'src.review_linter'`

- [ ] **Step 3: Write the implementation**

```python
"""评审文件校验器 —— 硬化评审格式的机器检查。

模式：默认（格式+原文锚点，草稿路径由 review→draft 目录互换推导）、
--check-marks <research-path>（格式+事实项标记完备性）、
--check-dispositions（格式+处理完备性；无违规但存在 未解决 时退出码 2）。
退出码：0 通过；1 违规；2 仅 dispositions 模式：处理齐全但含 未解决。
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

STATUS_RE = re.compile(r"^STATUS: (CLEAN|ISSUES)$")
ITEM_RE = re.compile(r"^## 问题 (\d+)\s*$", re.MULTILINE)
TYPE_RE = re.compile(r"^类型：(.+?)\s*$", re.MULTILINE)
QUOTE_RE = re.compile(r"^原文：`(.+?)`\s*$", re.MULTILINE | re.DOTALL)
DISP_RE = re.compile(r"^处理：(.*?)\s*$", re.MULTILINE)
VALID_TYPES = {"事实", "格式"}


@dataclass
class Item:
    num: int
    type: str | None = None
    quote: str | None = None
    disposition: str | None = None


@dataclass
class Review:
    status: str | None = None
    items: list[Item] = field(default_factory=list)


def parse_review(text: str) -> Review:
    first = text.splitlines()[0] if text.splitlines() else ""
    m = STATUS_RE.match(first)
    review = Review(status=m.group(1) if m else None)
    # 只解析到下一个 ## 标题为止的块，避免吞掉 标签提案/人类意见 等节
    matches = list(ITEM_RE.finditer(text))
    for i, im in enumerate(matches):
        start = im.end()
        next_heading = re.compile(r"^## ", re.MULTILINE).search(text, start)
        end = next_heading.start() if next_heading else len(text)
        block = text[start:end]
        item = Item(num=int(im.group(1)))
        if (t := TYPE_RE.search(block)):
            item.type = t.group(1)
        if (q := QUOTE_RE.search(block)):
            item.quote = q.group(1)
        if (d := DISP_RE.search(block)):
            item.disposition = d.group(1)
        review.items.append(item)
    return review


def validate_format(text: str) -> list[str]:
    v: list[str] = []
    r = parse_review(text)
    if r.status is None:
        v.append("第 1 行必须是 STATUS: CLEAN 或 STATUS: ISSUES")
    if r.status == "CLEAN" and r.items:
        v.append("STATUS: CLEAN 不得包含 问题 项")
    nums = [it.num for it in r.items]
    if nums != list(range(1, len(nums) + 1)):
        v.append(f"问题编号必须从 1 连续递增，实际为 {nums}")
    for it in r.items:
        if it.type is None:
            v.append(f"问题 {it.num}: 缺少 类型 行")
        elif it.type not in VALID_TYPES:
            v.append(f"问题 {it.num}: 类型 必须是 事实 或 格式，实际为 {it.type}")
        if it.quote is None:
            v.append(f"问题 {it.num}: 缺少 原文：`...` 行")
        if it.disposition is None:
            v.append(f"问题 {it.num}: 缺少 处理： 行")
    return v


def validate_anchors(text: str, draft_text: str) -> list[str]:
    v = []
    for it in parse_review(text).items:
        if it.quote and it.quote not in draft_text:
            v.append(f"问题 {it.num}: 原文引文未在草稿中逐字出现")
    return v


def check_marks(text: str, research_text: str, version: int) -> list[str]:
    v = []
    for it in parse_review(text).items:
        if it.type != "事实":
            continue
        if f"（评审v{version}-问题{it.num}）" not in research_text:
            v.append(f"问题 {it.num}: 研究文件缺少（评审v{version}-问题{it.num}）标记")
    return v


def check_dispositions(text: str) -> tuple[list[str], bool]:
    v, unresolved = [], False
    for it in parse_review(text).items:
        if not it.disposition:
            v.append(f"问题 {it.num}: 处理 行为空")
        elif it.disposition.startswith("未解决"):
            unresolved = True
    return v, unresolved


def main(argv: list[str]) -> int:
    review_path = Path(argv[0])
    text = review_path.read_text(encoding="utf-8")
    violations = validate_format(text)
    exit_code = 0
    if "--check-dispositions" in argv:
        dv, unresolved = check_dispositions(text)
        violations += dv
        if not violations and unresolved:
            exit_code = 2
    elif "--check-marks" in argv:
        research = Path(argv[argv.index("--check-marks") + 1])
        version = int(review_path.stem.rsplit("-v", 1)[-1])
        violations += check_marks(text, research.read_text(encoding="utf-8"), version)
    else:
        draft = Path(str(review_path).replace("/review/", "/draft/"))
        if draft.exists():
            violations += validate_anchors(text, draft.read_text(encoding="utf-8"))
        else:
            violations.append(f"找不到同版本草稿：{draft}")
    for x in violations:
        print(f"  - {x}")
    if violations:
        return 1
    print(f"OK{'（含 未解决 项）' if exit_code == 2 else ''}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_review_linter.py -q`
Expected: all PASS. If a fixture-parsing test fails, fix the implementation, not the contract.

- [ ] **Step 5: Commit**

```bash
git add src/review_linter.py src/tests/test_review_linter.py
git commit -m "feat(review): review_linter validates hardened review format (anchors/marks/dispositions)"
```

---

### Task 2: pipeline helpers `review_fact_items` + `research_age_days`

**Files:**
- Modify: `src/utils/pipeline.py` (append at end)
- Test: `src/tests/test_review_helpers.py` (create)

**Interfaces:**
- Consumes: `latest_review`, `find_research_file` (existing in same module); `parse_review` from Task 1.
- Produces: `review_fact_items(date_str: str, n: int) -> list[int]` (item numbers with 类型：事实 in the latest review; `[]` if no review) and `research_age_days(date_str: str, n: int) -> int | None` (whole days since the research file's mtime; `None` if no file). Used by Task 4 and by the orchestrate skill text (Task 9).

- [ ] **Step 1: Write the failing tests**

```python
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import pipeline as pl


REVIEW = """STATUS: ISSUES

## 问题 1
类型：事实
原文：`a`
处理：

## 问题 2
类型：格式
原文：`b`
处理：
"""


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PIPELINE", tmp_path)
    for d in ("review", "draft", "research"):
        (tmp_path / d).mkdir()


def test_review_fact_items(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert pl.review_fact_items("260701", 1) == []
    (tmp_path / "draft" / "260701-1-t-v1.md").write_text("x", encoding="utf-8")
    (tmp_path / "review" / "260701-1-t-v1.md").write_text(REVIEW, encoding="utf-8")
    assert pl.review_fact_items("260701", 1) == [1]


def test_research_age_days(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert pl.research_age_days("260701", 1) is None
    p = tmp_path / "research" / "260701-1-t.md"
    p.write_text("x", encoding="utf-8")
    old = time.time() - 3 * 86400
    os.utime(p, (old, old))
    assert pl.research_age_days("260701", 1) == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_review_helpers.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'review_fact_items'`

- [ ] **Step 3: Implement (append to `src/utils/pipeline.py`)**

```python
def review_fact_items(date_str: str, n: int) -> list[int]:
    """最新评审中 类型：事实 的问题编号；无评审返回 []。驱动 update-mode 研究分支。"""
    lr = latest_review(date_str, n)
    if lr is None:
        return []
    from src.review_linter import parse_review
    review = parse_review(lr[0].read_text(encoding="utf-8"))
    return [it.num for it in review.items if it.type == "事实"]


def research_age_days(date_str: str, n: int) -> int | None:
    """研究文件距今天数（按 mtime；update 会刷新）；无文件返回 None。"""
    p = find_research_file(date_str, int(n))
    if p is None:
        return None
    from datetime import date, datetime
    return (date.today() - datetime.fromtimestamp(p.stat().st_mtime).date()).days
```

- [ ] **Step 4: Run tests to verify pass**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_review_helpers.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/utils/pipeline.py src/tests/test_review_helpers.py
git commit -m "feat(pipeline): review_fact_items + research_age_days helpers"
```

---

### Task 3: publisher pre-flight — no unresolved comments at publish

**Files:**
- Modify: `src/publisher.py` (add two checks inside `publish()`, after the TAG-PROPOSAL block ending at the `raise SystemExit` around line 71)
- Test: `src/tests/test_publisher_preflight.py` (create; do not modify existing `test_publisher.py`)

**Interfaces:**
- Consumes: `check_dispositions` (Task 1), `latest_review` (existing).
- Produces: `check_review_resolved(date_str, n) -> None` (raises `SystemExit` on undispositioned/未解决 review) and module constant `PIPELINE_COMMENT_RE`; both called from `publish()`.

- [ ] **Step 1: Write the failing tests**

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils import pipeline as pl
from src import publisher


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PIPELINE", tmp_path)
    for d in ("review", "draft"):
        (tmp_path / d).mkdir()


def _write_review(tmp_path, disposition):
    (tmp_path / "draft" / "260701-1-t-v1.md").write_text("x", encoding="utf-8")
    (tmp_path / "review" / "260701-1-t-v1.md").write_text(
        f"STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`x`\n处理：{disposition}\n",
        encoding="utf-8")


def test_no_review_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    publisher.check_review_resolved("260701", 1)  # no raise


def test_empty_disposition_blocks(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "")
    with pytest.raises(SystemExit):
        publisher.check_review_resolved("260701", 1)


def test_unresolved_blocks(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "未解决：无裁定")
    with pytest.raises(SystemExit):
        publisher.check_review_resolved("260701", 1)


def test_resolved_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _write_review(tmp_path, "已修改")
    publisher.check_review_resolved("260701", 1)  # no raise


def test_comment_marker_regex():
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [USER]: keep -->")
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [REVIEWER]: fix -->")
    assert publisher.PIPELINE_COMMENT_RE.search("<!-- [WRITER-REJECTED]: no -->")
    assert not publisher.PIPELINE_COMMENT_RE.search("<!-- [TAG-PROPOSAL]: x -->")
    assert not publisher.PIPELINE_COMMENT_RE.search("正文没有注释")
```

- [ ] **Step 2: Run to verify failure**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_publisher_preflight.py -q`
Expected: FAIL with `AttributeError: module 'src.publisher' has no attribute 'check_review_resolved'`

- [ ] **Step 3: Implement in `src/publisher.py`**

Add near the top (after the imports, before `read_frontmatter`):

```python
import re

PIPELINE_COMMENT_RE = re.compile(r"<!--\s*\[(USER|REVIEWER|WRITER-)")


def check_review_resolved(date_str: str, n: int) -> None:
    """发布前置检查：最新评审（若存在）必须全部处置且无 未解决。"""
    from src.utils.pipeline import latest_review
    lr = latest_review(date_str, n)
    if lr is None:
        return
    from src.review_linter import check_dispositions
    violations, unresolved = check_dispositions(lr[0].read_text(encoding="utf-8"))
    problems = violations + (["存在 未解决 处理项"] if unresolved else [])
    if problems:
        raise SystemExit(
            f"评审 {lr[0].name} 未完全处置，拒绝发布：\n"
            + "\n".join(f"  - {p}" for p in problems))
```

Inside `publish()`, immediately after the TAG-PROPOSAL `raise SystemExit` block (i.e. right before the `from src.linter import lint_text, lint_warnings` line), add:

```python
    if PIPELINE_COMMENT_RE.search(content):
        raise SystemExit(
            "草稿含未消费的流程注释（[USER]/[REVIEWER]/[WRITER-*]），拒绝发布")
    check_review_resolved(date_str, n)
```

- [ ] **Step 4: Run new + existing publisher tests**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_publisher_preflight.py src/tests/test_publisher.py -q`
Expected: all PASS. If an existing `test_publisher.py` fixture draft contains `<!-- [USER]:`-style markers, that is a real conflict with the new gate — strip the marker from the fixture (the gate is intended behavior).

- [ ] **Step 5: Commit**

```bash
git add src/publisher.py src/tests/test_publisher_preflight.py
git commit -m "feat(publisher): pre-flight blocks unresolved review items and lingering pipeline comments"
```

---

### Task 4: `pipeline_cli.py status` shows research-file age

**Files:**
- Modify: `src/pipeline_cli.py` (the `status` subcommand's in-flight event listing)
- Test: `src/tests/test_review_helpers.py` (extend)

**Interfaces:**
- Consumes: `research_age_days` (Task 2).
- Produces: in-flight events whose research file is ≥ 2 days old get a `（research 已 N 天）` suffix in `status` output. The orchestrate skill (Task 9) tells the orchestrator to read this.

- [ ] **Step 1: Read the current implementation**

Run: `grep -n "def cmd_status\|in-flight\|在途" src/pipeline_cli.py` and read the surrounding function. Identify the loop that prints each in-flight event row (it iterates ledger rows with non-terminal states).

- [ ] **Step 2: Write the failing test (append to `src/tests/test_review_helpers.py`)**

```python
def test_status_line_suffix_for_stale_research(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    p = tmp_path / "research" / "260701-1-t.md"
    p.write_text("x", encoding="utf-8")
    old = time.time() - 5 * 86400
    os.utime(p, (old, old))
    from src.pipeline_cli import research_age_suffix
    assert research_age_suffix("260701", 1) == "（research 已 5 天）"
    assert research_age_suffix("260701", 2) == ""   # no research file
    os.utime(p, None)                               # fresh now
    assert research_age_suffix("260701", 1) == ""   # < 2 days → no suffix
```

- [ ] **Step 3: Run to verify failure**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_review_helpers.py -q`
Expected: FAIL with `ImportError: cannot import name 'research_age_suffix'`

- [ ] **Step 4: Implement**

Add to `src/pipeline_cli.py`:

```python
def research_age_suffix(date_str: str, n) -> str:
    """在途事件研究文件年龄提示；≥2 天提醒 orchestrator 建议刷新。"""
    from src.utils.pipeline import research_age_days
    age = research_age_days(date_str, int(n))
    return f"（research 已 {age} 天）" if age is not None and age >= 2 else ""
```

Then, in the `status` in-flight print loop found in Step 1, append `research_age_suffix(row 的收录日期, row 的事件编号)` to each printed event line (adapt variable names to the actual loop).

- [ ] **Step 5: Run tests, then the CLI smoke check**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_review_helpers.py -q && python src/pipeline_cli.py status`
Expected: tests PASS; `status` runs without error against the real ledger.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline_cli.py src/tests/test_review_helpers.py
git commit -m "feat(cli): status flags stale research files (>=2 days)"
```

---

### Task 5: `.claude/settings.json` — auto-approve gate commands

**Files:**
- Modify: `.claude/settings.json` (currently allows only WebFetch/WebSearch)

**Interfaces:**
- Produces: subagent gate commands (`linter.py`, `review_linter.py`) run without permission prompts. Agent bodies (Tasks 6–8) use exactly these command forms.

- [ ] **Step 1: Replace the file content**

```json
{
  "permissions": {
    "allow": [
      "WebFetch",
      "WebSearch",
      "Bash(src/venv/bin/python /home/jc/Projects/auto-watcher/src/linter.py:*)",
      "Bash(src/venv/bin/python /home/jc/Projects/auto-watcher/src/review_linter.py:*)",
      "Bash(cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/linter.py:*)",
      "Bash(cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/review_linter.py:*)"
    ]
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('.claude/settings.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "chore(settings): auto-approve linter and review_linter gate commands"
```

---

### Task 6: agent `blog-researcher` (fact-base owner, Sonnet)

**Files:**
- Create: `.claude/agents/blog-researcher.md`

**Interfaces:**
- Consumes: `review_linter.py --check-marks` (Task 1).
- Produces: subagent type `blog-researcher` dispatched by the orchestrate skill (Task 9) with params `mode/date/index/title/brief/sources` (initial) or `mode/date/index/title/review_path/draft_path` (update).

- [ ] **Step 1: Create the file with this exact content, then append 累积经验**

```markdown
---
name: blog-researcher
description: Research agent for the feminist blog — owns one event's fact base end-to-end; establishes it (initial) and updates it when a review disputes facts (update). Dispatched by the blog-orchestrate skill.
tools: WebSearch, WebFetch, Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

# Blog Researcher

**Write the entire research file in Simplified Chinese** — 中文成文，英文仅限专名。

You own the fact base for one event for its entire lifetime. The research file is the pipeline's single authoritative fact source: the writer has no web access and writes only what your file establishes. A fact you miss cannot appear in the post; a fact you get wrong will be published unless the reviewer catches it.

## Your Inputs

The orchestrator will tell you:
- `mode`: `initial` or `update`
- `date`: YYMMDD (e.g. `260325`)
- `index`: event number N
- `title`: event title in Chinese
- `brief`: one-sentence summary (initial mode)
- `sources`: initial Weibo source URLs, if any (initial mode)
- `review_path`: path to the review file (update mode)
- `draft_path`: path to the current draft — context only, do not edit (update mode)

Repo root: `/home/jc/Projects/auto-watcher`
Research file: `_pipeline/research/{date}-{index}-{title}.md`

## Initial Mode

### Search Strategy

Search in this order:

1. Search the event title in Chinese (exact phrase in quotes) → find news coverage
2. Search each key party's name + "声明" or "回应" → find official responses
3. Search victim/party Weibo handles if mentioned → find direct statements
4. Search title + "判决" or "立案" or "通报" → find case-fact/legal developments (statutes, rulings, official notices)
5. Search title + "微博" or "词条" → find public reaction and hashtag metrics

Use WebFetch on the most relevant URLs to extract verbatim quotes. Prioritise: 澎湃新闻, 新京报, 红星新闻, 极目新闻, 观察者网, official government/court notices.

### Track to today (strictly enforced)

Your search MUST reach today's actual date. Do not stop at the date of the most recent article you found — run at least one search with the current month/year (e.g. "事件名 2026年7月" or "事件名 最新进展") to confirm nothing newer exists. Finding an article from last week does not mean last week is current — keep searching until you have checked up to today.

### Blue font rule (strictly enforced)

`<font color="blue">` marks the last REAL factual development — a new verdict, arrest, official statement, or confirmed event. A sentence saying "截至X日无最新进展" or "尚未发布通报" is NOT a factual development and must NEVER be the blue-font item. **State that development's date explicitly next to it** — the writer sets the post's `date:` frontmatter from it and has no way to search for it.

### Coverage Standard

Research is sufficient when you have:
- Core facts established with at least 2 independent sources
- Statements or positions from all key parties (or noted as unavailable)
- Any official response (police, court, institution, government body)
- Statute/ruling facts (法条、司法解释、判决结果) if the case involves criminal law — do NOT collect named-expert commentary; it is banned from posts
- Weibo topic hashtag name and read count if one exists

### Output

Write to `_pipeline/research/{date}-{index}-{title}.md`:

    # Research: {title} ({date}, #{index})

    ## 事实
    [Key facts in chronological order. <font color="blue">…</font> on the most
    recent real development, with its date stated explicitly.]

    ## 当事方
    [Each key party — victim, perpetrator, institution. Their actions,
    statements, Weibo posts. Include Weibo handles/usernames where known.]

    ## 信息来源
    - [来源名称](url) — 关键摘录（原文引号）

## Update Mode

Read the review file at `review_path`. For each numbered `## 问题 K` with `类型：事实`, independently verify the disputed claim (WebSearch + WebFetch, same source priorities as initial mode). Then edit the research file **in place — never delete or overwrite existing text**. Record every verification with a mark tied to the review version and item number:

- New fact confirmed → add `**补充（评审vN-问题K）**：…` at the right chronological spot in 事实
- Existing fact wrong → rewrite it as `**更正（评审vN-问题K）**：正确表述（原错误信息：原句）` — the original text stays visible inside the mark
- Cannot verify → add `**查证失败（评审vN-问题K）**：X 无法证实` — this ruling tells the writer to remove the content

Every 事实 item gets exactly one mark. If the latest real development changes, move the `<font color="blue">` mark and update its stated date. Add any new sources to 信息来源.

**Completeness gate (mandatory):** before finishing, run

    src/venv/bin/python /home/jc/Projects/auto-watcher/src/review_linter.py <review_path> --check-marks <research-file-path>

and fix every violation. Do not report completion with a failing check.

## Report, never fabricate

If a claim cannot be verified either way, say so with the 查证失败 mark — never guess, never soften. If the event itself looks mis-scoped (wrong person, conflated incidents), stop and report to the orchestrator instead of writing a fact base you don't trust.
```

Then append a `## 累积经验` heading followed by the entire current content of `.claude/skills/blog-research/notes.md` (copy verbatim; it is ~6 lines).

- [ ] **Step 2: Verify frontmatter and structure**

Run: `head -8 .claude/agents/blog-researcher.md && grep -c "累积经验" .claude/agents/blog-researcher.md`
Expected: frontmatter shows `name: blog-researcher`, `model: sonnet`, tools line includes WebSearch; count is `1`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/blog-researcher.md
git commit -m "feat(agents): blog-researcher owns the fact base (initial + update modes, Sonnet)"
```

---

### Task 7: agent `blog-writer` (pure prose, no web)

**Files:**
- Create: `.claude/agents/blog-writer.md`

**Interfaces:**
- Consumes: research file marks (Task 6), `review_linter.py --check-dispositions` (Task 1), `src/utils/pipeline.next_draft_path` (existing).
- Produces: subagent type `blog-writer` dispatched with `date/index/title/mode/research_path` (+ `draft_path`/`review_path` in revision mode).

- [ ] **Step 1: Create the file with this exact content, then append 累积经验**

```markdown
---
name: blog-writer
description: Writing agent for the feminist blog — writes or revises one post draft as pure prose from the research fact base. Has no web access by design. Dispatched by the blog-orchestrate skill.
tools: Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

# Blog Writer

You write or revise one post draft. **You have no web tools and never gather facts** (do not attempt to fetch the web via Bash either). The research file is the sole source of facts: a fact not in the research file does not go in the draft. This is the no-inference rule with a named source of truth.

## Your Inputs

The orchestrator will tell you:
- `date`: YYMMDD
- `index`: N
- `title`: post title in Chinese
- `mode`: `initial` or `revision`
- `research_path`: path to the research file (always provided)
- `draft_path`: path to current draft (revision mode only)
- `review_path`: path to review file (revision mode only)

Repo root: `/home/jc/Projects/auto-watcher`

## Read first (mandatory, in order)

1. `source/_drafts/template.md` — the canonical format spec: frontmatter fields, section skeleton, per-section content rules, `<font>` colour conventions, asset embedding. Structure deviations are review-blocking. Published posts in `source/_posts/` are prose-style reference only; when they conflict, template.md wins.
2. `src/tags.yml` — the tag registry.
3. The research file at `research_path`.

## Initial Mode

Write the first draft from the research file, per the template. Transcribe the `<font color="blue">` mark onto the research file's marked latest development, and set the frontmatter `date:` to that development's stated date — never to today and never to the research file's own date.

**Report, never fabricate (hard rule):** if the fact base is thin, contradictory, or missing something the template requires, do not invent, do not guess, and do not write a draft. Report the specific gaps to the orchestrator (which facts are missing, what contradicts what) and stop.

## Revision Mode

Read the current draft, the review file, and the (updated) research file together. Handle each `## 问题 K` in the review file:

- `类型：事实` → locate its mark `（评审vN-问题K）` in the research file and act on it: apply a 补充 or 更正 by editing the prose; on 查证失败 remove the affected content. **No mark in the research file → take no action on the draft**; set `处理：未解决：研究文件无对应裁定` and report it at the end.
- `类型：格式` → your own judgment: apply it, or reject with reasoning.
- Fill each item's `处理：` line with exactly one of: `已修改` / `拒绝：<理由>` / `已删除（查证失败）` / `未解决：<缺口说明>`.

Apply ONLY changes tied to review items — no other rewrites. **User annotations take precedence over all reviewer suggestions.** They appear as `<!-- [USER]: ... -->` inline in the draft/review or as a `## 人类意见` section in the review file; apply them exactly as written, and remove the inline `[USER]` comments once applied (the publisher refuses drafts containing them).

**Disposition gate (mandatory):** after writing the new draft version, run

    src/venv/bin/python /home/jc/Projects/auto-watcher/src/review_linter.py <review_path> --check-dispositions

Every item must have a filled 处理 line. Exit code 2 means dispositions are complete but 未解决 items exist — finish, then explicitly list the unresolved items in your report so the orchestrator can re-dispatch research.

## Output Path

    import sys
    sys.path.insert(0, '/home/jc/Projects/auto-watcher')
    from src.utils.pipeline import next_draft_path
    path, v = next_draft_path(date, index, title)
    # Write draft to str(path)

## Style Rules

- No em dashes (破折号 —). Restructure the sentence instead.
- No filler phrases: "此事沉寂数月后"、"引发广泛关注" etc. State the fact directly.
- Concise 概述: 2–4 sentences maximum before the timeline.
- Sources section: one line per source, format exactly `YYYY.MM.DD，来源。*标题*。URL` — sources come from the research file's 信息来源.
- **Facts only, no inference:** every sentence must be directly supported by the research file. Do not infer, interpret, or editorialize. Do not draw conclusions from facts even if they seem obvious. If something is not explicitly stated in the research file, do not write it.
- **No expert opinions:** strip all named-expert commentary — lawyers, scholars, doctors, analysts, columnists, "专家". This applies even if the research file or reviewer includes such content. Factual law (statute numbers, 司法解释 thresholds, official enacted dates) and parallel cases may stay if stated without attribution to a commentator.
- **Lint gate (mandatory):** after writing the draft file, run
  `src/venv/bin/python /home/jc/Projects/auto-watcher/src/linter.py <draft-path>`
  and fix every violation before finishing. Do not report completion with a failing lint.

## Categories

- `S` — 政府/国家层面政策或法律（最高级别）
- `A` — 刑事案件；影响极为恶劣的舆论事件
- `B` — 民事案件；影响较大的舆论事件
- `C` — 非官方组织；影响较小的舆论事件
- `D` — 个人行为
- `N` — 中立事件。满足任一即为 N，且 **N 优先于其他级别判断**：①事实尚未核实（存疑）；②属实但已获公正解决（如加害者被判死刑；低于此的刑事结果历史上仍计 A/B）；③与性别不平等的相关性尚不确定。

**A/B 边界（历史校准，47 篇已发布文章零反例）：** 判 A 看刑事司法程序是否**实际启动**（刑事立案、刑拘、批捕、公诉、开庭、判决、获刑），不看行为"感觉上"是否犯罪。无程序但造成死亡/重伤或全国性极恶劣影响的重大事件仍可判 A。偷拍、骚扰等案件若只有行政处理（治安拘留、罚款、开除、校纪处分）或报警未刑事立案 → `B`。历史上写手系统性把此类案件误判为 A，再被人工降级。

**B/D 边界（用户确认，2026-07）：** 无刑事立案时，偷拍等侵犯隐私/涉性内容的伤害 → `B`；一般性肢体冲突（推搡、踢打、撞击等，仅治安处理或无处理）→ `D`。

## Tags

The canonical tag list lives in `src/tags.yml`, grouped by status / crime / legal / topic / context / identity / location. Only use tags that already exist there — the publisher validates every draft against this registry and refuses to deploy an unknown tag.

**Tags must genuinely fit.** Do NOT pad with tangentially-related tags to hit a count. Frontmatter may only contain registered tags. If fewer than 2 registered tags genuinely fit, or an important theme has no tag, add a proposal comment right after the frontmatter (one per line, several allowed):

    <!-- [TAG-PROPOSAL]: 标签名 — 理由 -->

Registered tags + proposals together must be ≥ 2. Proposals are adjudicated by the user at the review gate; the publisher refuses to deploy a draft with unresolved proposals, and the linter accepts an empty tags list only when a proposal comment is present.

Status tags (always available):
- `PING` — 插眼等后续（follow-up expected）
- `TODO` — 还需查证（unverified claim）
```

Then append a `## 累积经验` heading followed by the entire current content of `.claude/skills/blog-write/notes.md` (copy verbatim).

- [ ] **Step 2: Verify the tool allowlist excludes web**

Run: `grep "^tools:" .claude/agents/blog-writer.md`
Expected: `tools: Read, Write, Edit, Glob, Grep, Bash` — no WebSearch, no WebFetch.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/blog-writer.md
git commit -m "feat(agents): blog-writer is pure prose — no web tools, research file is sole fact source"
```

---

### Task 8: agent `blog-reviewer` (hardened output format)

**Files:**
- Create: `.claude/agents/blog-reviewer.md`

**Interfaces:**
- Consumes: `review_linter.py` default mode (Task 1), `src/utils/pipeline.next_review_path` (existing).
- Produces: subagent type `blog-reviewer` dispatched with `date/index/title/draft_path`; review files matching the contract in Global Constraints.

- [ ] **Step 1: Create the file with this exact content, then append 累积经验**

```markdown
---
name: blog-reviewer
description: Review agent for the feminist blog — independently fact-checks one draft and produces a structured, machine-validated review file. Dispatched by the blog-orchestrate skill.
tools: WebSearch, WebFetch, Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

# Blog Reviewer

You independently fact-check one draft and produce a review file. Your search is deliberately independent — do not trust the draft's sources or the research file uncritically; re-derive the facts.

## Your Inputs

The orchestrator will tell you:
- `date`: YYMMDD
- `index`: event number N
- `title`: post title in Chinese
- `draft_path`: path to the current draft

Repo root: `/home/jc/Projects/auto-watcher`

## Review Process

1. **Read the draft** at `draft_path` in full. Read `source/_drafts/template.md` for the canonical format.
2. **Independently verify key claims** — for each factual claim (dates, names, outcomes, quotes), verify against at least one independent source. Use WebSearch + WebFetch. Prioritise: 澎湃新闻, 新京报, 红星新闻, 极目新闻, court notices, official statements.
3. **Check verbatim quotes** — every `<font color="grey">` passage must be traceable to a real source. Flag any that cannot be verified.
4. **Check legal/factual claims** — any `<font color="red">` passage must be accurate. Flag overstatements or errors.
5. **Check the latest-update marker** — independently search each key person/institution for developments up to today, including a search with the current month/year, to confirm nothing newer exists. The `<font color="blue">` passage must be the actual most recent development; flag if a newer fact exists, or if the blue passage is a "no update" statement rather than a real development.
6. **Check structure and format against the template** — section names/order, 概述-only placement of case-specific content, 信息来源 line format, 舆论 concrete-metrics rule, 相关内容 scope, `<font>` colour usage, category value, tag registration. Every deviation is an issue (类型：格式), not a stylistic preference.
7. **Transcribe tag proposals** — copy every `<!-- [TAG-PROPOSAL]: ... -->` comment from the draft into a dedicated `## 标签提案` section of the review file, so the user sees them at the review gate. Do not resolve them yourself.

## Output Path

    import sys
    sys.path.insert(0, '/home/jc/Projects/auto-watcher')
    from src.utils.pipeline import next_review_path
    path, v = next_review_path(date, index)
    # Write review to str(path)

## Review File Format (strict — machine-validated)

**Do NOT edit the draft file. Never copy the draft.** All annotations go in the review file only, in exactly this shape:

    STATUS: ISSUES

    ## 问题 1
    类型：事实
    原文：`<exact verbatim passage copied from the draft>`
    <!-- [REVIEWER]: <suggested correction or question> -->
    处理：

    ## 问题 2
    类型：格式
    原文：`<exact verbatim passage>`
    <!-- [REVIEWER]: <suggestion> -->
    处理：

- **First line must be exactly `STATUS: CLEAN` or `STATUS: ISSUES`** — the orchestrator reads it. A CLEAN review contains no 问题 items.
- Number items `## 问题 1`, `## 问题 2`, … consecutively.
- `类型：事实` = wrong, unverifiable, stale, or missing facts — anything requiring the fact base to change. `类型：格式` = template, structure, style, wording, or colour-convention violations.
- `原文：` must quote the draft **verbatim** (copy-paste; the validator rejects paraphrases).
- Leave every `处理：` line empty — the writer fills it during revision.
- `## 标签提案` and `## 人类意见` sections may follow the items.

**Validation gate (mandatory):** after writing the review file, run

    src/venv/bin/python /home/jc/Projects/auto-watcher/src/review_linter.py <review-path>

and fix every violation before finishing. Do not report completion with a failing check.

## Style Notes

- Be precise: quote the exact passage being questioned.
- Flag speculation clearly: "未经证实" or "来源不明" for unverifiable claims.
- Do not flag stylistic preferences — only factual errors, unverifiable quotes, or structural violations.
- **No inference:** flag any claim that is an inference or editorial conclusion rather than a fact directly stated in a source — even if the inference seems reasonable. If a passage interprets, characterises, or draws a conclusion from facts, flag it (类型：事实).
```

Then append a `## 累积经验` heading followed by the entire current content of `.claude/skills/blog-review/notes.md` (copy verbatim).

- [ ] **Step 2: Sanity-check the format example against the validator**

Run:
```bash
mkdir -p /tmp/claude-1000/rl-check/review /tmp/claude-1000/rl-check/draft
printf 'STATUS: ISSUES\n\n## 问题 1\n类型：事实\n原文：`abc`\n<!-- [REVIEWER]: x -->\n处理：\n' > /tmp/claude-1000/rl-check/review/990101-1-t-v1.md
printf 'abc\n' > /tmp/claude-1000/rl-check/draft/990101-1-t-v1.md
src/venv/bin/python src/review_linter.py /tmp/claude-1000/rl-check/review/990101-1-t-v1.md
```
Expected: `OK`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/blog-reviewer.md
git commit -m "feat(agents): blog-reviewer with strict machine-validated review format"
```

---

### Task 9: rename + rewrite the orchestrate skill; rename summarize

**Files:**
- Rename: `.claude/skills/blog-orchestrator/` → `.claude/skills/blog-orchestrate/`
- Rename: `.claude/skills/blog-summary/` → `.claude/skills/blog-summarize/`
- Modify: `.claude/skills/blog-orchestrate/SKILL.md`, `.claude/skills/blog-summarize/SKILL.md` (frontmatter `name:` + self-references)

**Interfaces:**
- Consumes: subagent types `blog-researcher`/`blog-writer`/`blog-reviewer` (Tasks 6–8), `review_fact_items` + `research_age_days` (Task 2), `research_age_suffix` output (Task 4).
- Produces: the orchestrate skill that CLAUDE.md (Task 11) references.

- [ ] **Step 1: Rename directories and frontmatter**

```bash
git mv .claude/skills/blog-orchestrator .claude/skills/blog-orchestrate
git mv .claude/skills/blog-summary .claude/skills/blog-summarize
```
Then in `.claude/skills/blog-orchestrate/SKILL.md` frontmatter change `name: blog-orchestrator` → `name: blog-orchestrate`; in `.claude/skills/blog-summarize/SKILL.md` change `name: blog-summary` → `name: blog-summarize` and update any in-file self-references (`grep -rn "blog-summary\|blog-orchestrator" .claude/skills/blog-summarize/ .claude/skills/blog-orchestrate/`).

- [ ] **Step 2: Rewrite Stage 2 of `.claude/skills/blog-orchestrate/SKILL.md`**

Replace the entire `### 2. Research (subagent)` section (from its heading to just before `### 3. Write (subagent)`) with:

```markdown
### 2. Research (subagent)

Dispatch a `blog-researcher` subagent (tools and model are pinned in the agent definition). When processing multiple events, dispatch in **batches of 2–3** so a quota hit loses only one batch.

```
mode: initial
date: YYMMDD
index: N
title: <title>
brief: <one-sentence summary from events file>
sources: <Weibo URLs found in events file for this event, if any>
```

Wait for the subagent to complete and confirm the research file exists at `_pipeline/research/YYMMDD-N-title.md`. Then STOP — the user reads the fact base before writing is approved.
```

- [ ] **Step 3: Rewrite Stage 3 of the same file**

Replace the entire `### 3. Write (subagent)` section (heading to just before `### 4a.`) with:

```markdown
### 3. Write (subagent)

**Freshness check first:** `pipeline_cli.py status` flags in-flight events whose research file is ≥ 2 days old (`（research 已 N 天）`). If the event being dispatched is flagged, recommend an update-mode research refresh and let the user decide — never refresh automatically.

Dispatch a `blog-writer` subagent (no web tools by design — the research file is its sole fact source). Dispatch in **batches of 2–3**.

```
date: YYMMDD
index: N
title: <title>
mode: initial
research_path: _pipeline/research/YYMMDD-N-title.md
```

Wait for the subagent to complete. If it reports fact-base gaps instead of writing a draft, relay the gaps to the user and (on approval) re-dispatch `blog-researcher` — do not ask the writer to improvise.
```

- [ ] **Step 4: Rewrite Stage 4b of the same file**

Replace the `**4b-i. Review (subagent):**` block (from that line to just before `**4b-ii.`) with:

```markdown
**4b-i. Review (subagent):**

Dispatch a `blog-reviewer` subagent:

```
date: YYMMDD
index: N
title: <title>
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md
```
```

Then replace the `**4b-iii. If user approves, dispatch revision (subagent):**` block (from that line to just before `Return to step 4b-i.`) with:

```markdown
**4b-iii. If user approves — fact-base update first, then revision:**

Check whether the review disputes facts (deterministic, not judgment):

```python
from src.utils.pipeline import review_fact_items
fact_items = review_fact_items(date_str, n)
```

If `fact_items` is non-empty, dispatch a `blog-researcher` subagent in update mode:

```
mode: update
date: YYMMDD
index: N
title: <title>
review_path: _pipeline/review/YYMMDD-N-title-vN.md
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md
```

Then **STOP** — report the marked fact-base changes (补充/更正/查证失败) and wait for the user to inspect them before approving the prose revision.

On approval (or immediately, if `fact_items` was empty), dispatch a `blog-writer` subagent:

```
date: YYMMDD
index: N
title: <title>
mode: revision
research_path: _pipeline/research/YYMMDD-N-title.md
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md   (current draft)
review_path: _pipeline/review/YYMMDD-N-title-vN.md  (current review)
```

If the writer reports 未解决 items, relay them to the user; the fix is another update-mode research dispatch, not writer improvisation.
```

- [ ] **Step 5: Update the Notes section of the same file**

Replace the first bullet under `## Notes` with:

```markdown
- Subagent tools and models are pinned in `.claude/agents/blog-researcher.md`, `blog-writer.md`, `blog-reviewer.md` (all Sonnet; the writer has no web tools). Dispatch in batches of 2–3.
```

- [ ] **Step 6: Verify no stale names inside the two skills**

Run: `grep -rn "blog-research\b\|blog-write\b\|blog-review\b\|blog-orchestrator\|blog-summary\b" .claude/skills/blog-orchestrate/ .claude/skills/blog-summarize/`
Expected: no matches referring to the old skill paths or old names (references to *agent* names `blog-researcher/-writer/-reviewer` are correct and expected).

- [ ] **Step 7: Commit**

```bash
git add -A .claude/skills/
git commit -m "feat(orchestrate): rename skills to verb form; dispatch pinned agents; update-mode research in revision loop"
```

---

### Task 10: retarget `blog-curate` to agent files

**Files:**
- Modify: `.claude/skills/blog-curate/SKILL.md`

**Interfaces:**
- Consumes: agent files from Tasks 6–8.

- [ ] **Step 1: Apply these edits**

1. Replace the `## Skill Notes Files` section (heading + code block) with:

```markdown
## Curated Files

Each pipeline agent carries its accumulated experience in a `## 累积经验` section of its own definition file:

```
.claude/agents/blog-researcher.md
.claude/agents/blog-writer.md
.claude/agents/blog-reviewer.md
```
```

2. Global wording swaps in the same file: `notes.md` → `the agent's 累积经验 section`; `SKILL.md` (as promotion target) → `the agent's instruction sections`; the intro sentence becomes: "Your job is to keep the `累积经验` sections across the pipeline agents healthy: concise, accurate, non-conflicting, and progressively promoting key insights into the agent's instruction sections."
3. In `## Harvest` step 2: "Distill into the relevant skill's `notes.md`" → "Distill into the relevant agent's `## 累积经验` section".
4. In `## Promotion Guidelines`: "If SKILL.md exceeds ~180 lines" → "If an agent file exceeds ~180 lines". The routing line becomes: "mechanically checkable → `src/linter.py` or `src/review_linter.py` (with a test); format/structure rules → `source/_drafts/template.md`; judgment rules → the agent's instruction sections."
5. In `## Curation Process` and `## Conflict Resolution`, replace remaining `notes.md`/`SKILL.md` pairs accordingly (the "two files" become one agent file: promote = move text from 累积经验 into the instruction sections above it).

- [ ] **Step 2: Verify**

Run: `grep -n "notes.md" .claude/skills/blog-curate/SKILL.md`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/blog-curate/SKILL.md
git commit -m "feat(curate): retarget curation to agent 累积经验 sections"
```

---

### Task 11: CLAUDE.md updates

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above; this is the canonical doc catching up (anti-drift rule).

- [ ] **Step 1: Apply these edits**

1. **Stage 2 section** — replace the `### Stage 2 — Research (skill: blog-research)` heading and body with:

```markdown
### Stage 2 — Research (agent: `blog-researcher`)
Dispatched by the `blog-orchestrate` skill (Sonnet; tools/model pinned in `.claude/agents/blog-researcher.md`). Owns the fact base end-to-end: `mode: initial` establishes `_pipeline/research/YYMMDD-N-title.md` (sections `## 事实`, `## 当事方`, `## 信息来源`, tracked to today, blue-font latest development with explicit date); `mode: update` verifies review-disputed facts and edits the file in place with `补充/更正/查证失败（评审vN-问题K）` marks — never destructively.
```

2. **Stage 3 section** — replace heading and body with:

```markdown
### Stage 3 — Write (agent: `blog-writer`)
Dispatched by `blog-orchestrate` (Sonnet, **no web tools** — the research file is the sole fact source; a fact not in it does not go in the draft). Output to `_pipeline/draft/YYMMDD-N-title-vN.md`. If the fact base has gaps, the writer reports them instead of drafting. Format spec: `source/_drafts/template.md`; judgment rules live in `.claude/agents/blog-writer.md`.
```

3. **Stage 4 section** — replace heading and body with:

```markdown
### Stage 4 — Review (agent: `blog-reviewer`)
Dispatched by `blog-orchestrate` (Sonnet, independent web verification). Writes `_pipeline/review/YYMMDD-N-title-vN.md` in a strict format (line 1 `STATUS: CLEAN|ISSUES`; numbered `## 问题 K` items typed 事实/格式 with verbatim `原文` anchors and `处理：` lines), validated by `src/review_linter.py`. If any 事实 item exists, the revision cycle inserts an update-mode research pass before the writer revision. User annotates disagreements as `<!-- [USER]: ... -->` before revision.
```

4. **Post Format section** — change "live in the `blog-write` skill" to "live in the `blog-writer` agent (`.claude/agents/blog-writer.md`)".
5. **Monthly Summary section** — heading becomes `### On-demand — Monthly Summary (skill: blog-summarize)`; `/blog-summary YYMM` → `/blog-summarize YYMM`; "never run by `blog-orchestrator`" → "never run by `blog-orchestrate`"; "per the `blog-summary` skill" → "per the `blog-summarize` skill".
6. **Subagent Model Selection section** — replace the two "Use **Haiku**…" / "Use **Sonnet**…" paragraphs (keep the Chinese-language requirement and batching paragraphs) with:

```markdown
All pipeline subagents — research, write, review, summary — run on **Sonnet**; models and tool allowlists for research/write/review are pinned in `.claude/agents/` (the writer deliberately has no web tools). Research needs coverage judgment (the writer no longer backstops it), which Haiku handles unreliably. **Haiku** survives only in the tracker's LLM filtering (a `claude` CLI subprocess, not a subagent).
```

7. **Stage 5 section** — after the sentence about picking the latest draft, add: "Pre-flight refuses to publish if the latest review has undispositioned or `未解决` items, or if the draft still contains `[USER]`/`[REVIEWER]`/`[WRITER-*]` comments."

- [ ] **Step 2: Verify no stale references**

Run: `grep -n "blog-orchestrator\|blog-summary\b\|skill: \`blog-research\`\|skill: \`blog-write\`\|skill: \`blog-review\`" CLAUDE.md`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): agents own stages 2-4; verb-form skill names; Sonnet everywhere but tracker filtering"
```

---

### Task 12: delete migrated skills; full verification

**Files:**
- Delete: `.claude/skills/blog-research/`, `.claude/skills/blog-write/`, `.claude/skills/blog-review/`

- [ ] **Step 1: Confirm migration is complete before deleting**

Run: `for f in blog-research blog-write blog-review; do echo "== $f"; cat .claude/skills/$f/notes.md; done`
Then confirm each notes.md content appears verbatim inside the corresponding agent's `## 累积经验` (`grep -A8 "累积经验" .claude/agents/blog-*.md`). If anything is missing, fix the agent file first.

- [ ] **Step 2: Delete**

```bash
git rm -r .claude/skills/blog-research .claude/skills/blog-write .claude/skills/blog-review
```

- [ ] **Step 3: Repo-wide stale-reference sweep**

Run: `grep -rn "skills/blog-research\|skills/blog-write\|skills/blog-review\|blog-orchestrator\|blog-summary\b" --include="*.md" --include="*.py" --include="*.json" . | grep -v _pipeline_archive | grep -v docs/superpowers | grep -v node_modules | grep -v public/`
Expected: no matches (archives and spec/plan history are exempt).

- [ ] **Step 4: Full test suite**

Run: `source src/venv/bin/activate && python -m pytest src/tests/ -q`
Expected: all tests pass, including the pre-existing suite.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(pipeline): complete skill->agent migration; remove migrated stage skills"
```
