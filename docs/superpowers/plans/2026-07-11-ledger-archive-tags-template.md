# CSV 账本 + 按事件归档 + TAG-PROPOSAL + 模板权威 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `_pipeline/events.csv` 单一账本替代 status 侧车 / done-dates / .state / harvest-queue 四个状态载体，实现按事件归档、TAG-PROPOSAL 新标签机制、template.md 格式唯一权威，并修正全部已审计的文档漂移。

**Architecture:** 分层：`src/utils/pipeline.py`（纯路径助手）→ `src/utils/ledger.py`（CSV 状态 + 对账，读路径内建对账）→ `src/utils/archive.py`（按事件/按日期归档）→ `src/pipeline_cli.py`（用户/orchestrator 入口）。tracker/publisher 接入账本；一次性迁移脚本生成初始 CSV 后删除旧载体。

**Tech Stack:** Python 3.12 stdlib（csv/pathlib/argparse），pytest（hermetic，既有惯例 monkeypatch `src.utils.pipeline.PIPELINE`）。

**Spec:** `docs/superpowers/specs/2026-07-11-per-event-archive-tags-template-design.md`

## Global Constraints

- venv：`source src/venv/bin/activate`；测试命令 `python -m pytest src/tests/ -q`（全量必须绿才算任务完成）。
- 提交信息结尾必须带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`；直接提交 main。
- CSV 列名（精确逐字）：`维护日期,收录日期,事件编号,标题,状态,发布日期,发布标题,经验提取`。
- 状态枚举（精确逐字）：`candidate` `selected` `research` `draft-vN` `review-vN` `published` `abort` `无事件`；终态 = `published`/`abort`/`无事件`。经验提取列值：空/`待提取`/`已提取`。
- 日期一律 YYMMDD（如 `260711`）。所有文件 UTF-8。
- **可测试性关键约定**：新模块不得 `from src.utils.pipeline import PIPELINE`（值拷贝会使测试的 monkeypatch 失效）。必须 `from src.utils import pipeline as pl`，函数签名用 `pipeline_dir: Path | None = None`，函数体内 `pipeline_dir = pipeline_dir or pl.PIPELINE`（archive_dir 同理 `or pl.ARCHIVE`）。
- 中文串（列名、状态值）在代码中直接写字面量，不做 i18n。

---

### Task 1: ledger 核心读写（列定义、倒序块插入、引号往返）

**Files:**
- Create: `src/utils/ledger.py`
- Test: `src/tests/test_ledger.py`

**Interfaces:**
- Produces: `COLUMNS: list[str]`, `NO_EVENTS = "无事件"`, `TERMINAL_STATES: set[str]`, `HARVEST_PENDING = "待提取"`, `HARVEST_DONE = "已提取"`, `ledger_path(pipeline_dir=None) -> Path`, `read_rows(pipeline_dir=None) -> list[dict]`, `write_rows(rows, pipeline_dir=None) -> None`, `add_rows(new_rows: list[dict], pipeline_dir=None) -> None`, `get_row(date_str, n, pipeline_dir=None) -> dict | None`, `update_row(date_str, n, pipeline_dir=None, **fields) -> None`

- [ ] **Step 1: 写失败测试**

```python
# src/tests/test_ledger.py
import pytest
from src.utils import ledger


def test_read_rows_missing_file_is_empty(tmp_path):
    assert ledger.read_rows(pipeline_dir=tmp_path) == []


def test_write_read_roundtrip_with_commas_and_quotes(tmp_path):
    rows = [{
        "维护日期": "260711", "收录日期": "260524", "事件编号": "1",
        "标题": '标题，含逗号和"引号"', "状态": "candidate",
        "发布日期": "", "发布标题": "", "经验提取": "",
    }]
    ledger.write_rows(rows, pipeline_dir=tmp_path)
    assert ledger.read_rows(pipeline_dir=tmp_path) == rows


def test_add_rows_prepends_block_below_header(tmp_path):
    ledger.add_rows([{"维护日期": "260610", "收录日期": "260524",
                      "事件编号": "1", "标题": "旧", "状态": "candidate"}],
                    pipeline_dir=tmp_path)
    ledger.add_rows([
        {"维护日期": "260711", "收录日期": "260705", "事件编号": "2",
         "标题": "新b", "状态": "candidate"},
        {"维护日期": "260711", "收录日期": "260705", "事件编号": "1",
         "标题": "新a", "状态": "candidate"},
    ], pipeline_dir=tmp_path)
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    # 新块在最上面，块内按（收录日期, 事件编号）升序；缺省列补空串
    assert [(r["收录日期"], r["事件编号"]) for r in rows] == [
        ("260705", "1"), ("260705", "2"), ("260524", "1")]
    assert rows[0]["发布日期"] == ""


def test_header_mismatch_raises(tmp_path):
    (tmp_path / "events.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        ledger.read_rows(pipeline_dir=tmp_path)


def test_get_and_update_row(tmp_path):
    ledger.add_rows([{"维护日期": "260711", "收录日期": "260524",
                      "事件编号": "1", "标题": "t", "状态": "candidate"}],
                    pipeline_dir=tmp_path)
    assert ledger.get_row("260524", 1, pipeline_dir=tmp_path)["标题"] == "t"
    assert ledger.get_row("260524", 9, pipeline_dir=tmp_path) is None
    ledger.update_row("260524", 1, pipeline_dir=tmp_path, **{"状态": "selected"})
    assert ledger.get_row("260524", 1, pipeline_dir=tmp_path)["状态"] == "selected"
    with pytest.raises(KeyError):
        ledger.update_row("260524", 9, pipeline_dir=tmp_path, **{"状态": "x"})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `source src/venv/bin/activate && python -m pytest src/tests/test_ledger.py -q`
Expected: FAIL（`No module named 'src.utils.ledger'`）

- [ ] **Step 3: 最小实现**

```python
# src/utils/ledger.py
"""CSV 状态账本 —— _pipeline/events.csv 是管线状态的唯一权威。

一行 = 一个事件（或一个"无事件"日期）。按维护日期倒序：新维护块插在表头之下。
中间态（research/draft-vN/review-vN）由对账从工件文件推导，见 reconcile()。
"""
from __future__ import annotations
import csv
from datetime import date, timedelta
from pathlib import Path

from src.utils import pipeline as pl

COLUMNS = ["维护日期", "收录日期", "事件编号", "标题",
           "状态", "发布日期", "发布标题", "经验提取"]
NO_EVENTS = "无事件"
TERMINAL_STATES = {"published", "abort", NO_EVENTS}
HARVEST_PENDING = "待提取"
HARVEST_DONE = "已提取"


def ledger_path(pipeline_dir: Path | None = None) -> Path:
    return (pipeline_dir or pl.PIPELINE) / "events.csv"


def read_rows(pipeline_dir: Path | None = None) -> list[dict]:
    p = ledger_path(pipeline_dir)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise RuntimeError(f"{p}: 表头不符 {reader.fieldnames}")
        return [dict(r) for r in reader]


def write_rows(rows: list[dict], pipeline_dir: Path | None = None) -> None:
    p = ledger_path(pipeline_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _block_key(row: dict) -> tuple:
    n = row.get("事件编号", "")
    return (row.get("收录日期", ""), int(n) if n else 0)


def add_rows(new_rows: list[dict], pipeline_dir: Path | None = None) -> None:
    """新维护块插入表头之下（最近维护在最上），块内按（收录日期, 事件编号）升序。"""
    block = []
    for r in sorted(new_rows, key=_block_key):
        full = {c: "" for c in COLUMNS}
        full.update(r)
        block.append(full)
    write_rows(block + read_rows(pipeline_dir), pipeline_dir)


def get_row(date_str: str, n: int | str, pipeline_dir: Path | None = None) -> dict | None:
    for r in read_rows(pipeline_dir):
        if r["收录日期"] == date_str and r["事件编号"] == str(n):
            return r
    return None


def update_row(date_str: str, n: int | str,
               pipeline_dir: Path | None = None, **fields) -> None:
    rows = read_rows(pipeline_dir)
    for r in rows:
        if r["收录日期"] == date_str and r["事件编号"] == str(n):
            r.update(fields)
            write_rows(rows, pipeline_dir)
            return
    raise KeyError(f"账本中无 {date_str}-{n} 行")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_ledger.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/utils/ledger.py src/tests/test_ledger.py
git commit -m "feat(ledger): CSV ledger core — columns, prepend blocks, quoting roundtrip

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: ledger 状态转换（add_event / selected / aborted / published / 无事件 / max_index）

**Files:**
- Modify: `src/utils/ledger.py`（文件末尾追加）
- Test: `src/tests/test_ledger.py`（追加）

**Interfaces:**
- Consumes: Task 1 全部。
- Produces: `add_event(date_str, n, title, state="candidate", maint_date=None, pipeline_dir=None) -> bool`, `record_no_events(date_str, maint_date=None, pipeline_dir=None) -> bool`, `record_selected(date_str, n, pipeline_dir=None)`, `record_aborted(date_str, n, pipeline_dir=None)`, `record_published(date_str, n, pub_title="", pub_date=None, pipeline_dir=None)`, `max_index(date_str, pipeline_dir=None) -> int`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 src/tests/test_ledger.py

def _seed(tmp_path, state="candidate"):
    ledger.add_event("990101", 1, "标题一", state=state,
                     maint_date="260711", pipeline_dir=tmp_path)


def test_add_event_and_dedup(tmp_path):
    assert ledger.add_event("990101", 1, "t", maint_date="260711",
                            pipeline_dir=tmp_path) is True
    assert ledger.add_event("990101", 1, "t", maint_date="260711",
                            pipeline_dir=tmp_path) is False
    row = ledger.get_row("990101", 1, pipeline_dir=tmp_path)
    assert row["状态"] == "candidate" and row["维护日期"] == "260711"


def test_record_no_events_once_per_date(tmp_path):
    assert ledger.record_no_events("990102", maint_date="260711",
                                   pipeline_dir=tmp_path) is True
    assert ledger.record_no_events("990102", pipeline_dir=tmp_path) is False
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    assert rows[0]["状态"] == "无事件" and rows[0]["事件编号"] == ""


def test_record_selected_flow_and_guards(tmp_path):
    _seed(tmp_path)
    ledger.record_selected("990101", 1, pipeline_dir=tmp_path)
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["状态"] == "selected"
    ledger.record_selected("990101", 1, pipeline_dir=tmp_path)  # 幂等
    ledger.record_aborted("990101", 1, pipeline_dir=tmp_path)
    with pytest.raises(RuntimeError):
        ledger.record_selected("990101", 1, pipeline_dir=tmp_path)


def test_record_aborted_guards(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="发布题",
                            pub_date="260712", pipeline_dir=tmp_path)
    with pytest.raises(RuntimeError):
        ledger.record_aborted("990101", 1, pipeline_dir=tmp_path)


def test_record_published_sets_fields_and_harvest(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="发布题",
                            pub_date="260712", pipeline_dir=tmp_path)
    row = ledger.get_row("990101", 1, pipeline_dir=tmp_path)
    assert row["状态"] == "published"
    assert row["发布日期"] == "260712"
    assert row["发布标题"] == "发布题"
    assert row["经验提取"] == "待提取"
    # 幂等：重复发布不改字段
    ledger.record_published("990101", 1, pub_title="另一题", pipeline_dir=tmp_path)
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["发布标题"] == "发布题"


def test_record_published_missing_row_raises(tmp_path):
    with pytest.raises(KeyError):
        ledger.record_published("990101", 9, pipeline_dir=tmp_path)


def test_max_index(tmp_path):
    assert ledger.max_index("990101", pipeline_dir=tmp_path) == 0
    ledger.add_event("990101", 2, "b", pipeline_dir=tmp_path)
    ledger.add_event("990101", 1, "a", pipeline_dir=tmp_path)
    assert ledger.max_index("990101", pipeline_dir=tmp_path) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_ledger.py -q`
Expected: FAIL（`AttributeError: ... has no attribute 'add_event'`）

- [ ] **Step 3: 实现**

```python
# 追加到 src/utils/ledger.py

def _today() -> str:
    return date.today().strftime("%y%m%d")


def add_event(date_str: str, n: int, title: str, state: str = "candidate",
              maint_date: str | None = None,
              pipeline_dir: Path | None = None) -> bool:
    """新增事件行；(收录日期, 事件编号) 已存在则 no-op 返回 False。"""
    if get_row(date_str, n, pipeline_dir):
        return False
    add_rows([{"维护日期": maint_date or _today(), "收录日期": date_str,
               "事件编号": str(n), "标题": title, "状态": state}], pipeline_dir)
    return True


def record_no_events(date_str: str, maint_date: str | None = None,
                     pipeline_dir: Path | None = None) -> bool:
    """记录"查过该日期、无事件"；该收录日期已有任何行则 no-op。"""
    if any(r["收录日期"] == date_str for r in read_rows(pipeline_dir)):
        return False
    add_rows([{"维护日期": maint_date or _today(), "收录日期": date_str,
               "事件编号": "", "标题": "", "状态": NO_EVENTS}], pipeline_dir)
    return True


def record_selected(date_str: str, n: int, pipeline_dir: Path | None = None) -> None:
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] in ("published", "abort"):
        raise RuntimeError(f"{date_str}-{n} 已是终态 {row['状态']}，不能 select")
    if row["状态"] == "candidate":
        update_row(date_str, n, pipeline_dir, **{"状态": "selected"})


def record_aborted(date_str: str, n: int, pipeline_dir: Path | None = None) -> None:
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] == "published":
        raise RuntimeError(f"{date_str}-{n} 已 published，不能 abort；如确需请手改 CSV")
    update_row(date_str, n, pipeline_dir, **{"状态": "abort"})


def record_published(date_str: str, n: int, pub_title: str = "",
                     pub_date: str | None = None,
                     pipeline_dir: Path | None = None) -> None:
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] == "published":
        return
    if row["状态"] == "abort":
        raise RuntimeError(f"{date_str}-{n} 已 abort；如确需发布请手改 CSV")
    update_row(date_str, n, pipeline_dir, **{
        "状态": "published", "发布日期": pub_date or _today(),
        "发布标题": pub_title, "经验提取": HARVEST_PENDING})


def max_index(date_str: str, pipeline_dir: Path | None = None) -> int:
    ns = [int(r["事件编号"]) for r in read_rows(pipeline_dir)
          if r["收录日期"] == date_str and r["事件编号"]]
    return max(ns) if ns else 0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_ledger.py -q`
Expected: PASS（12 passed）

- [ ] **Step 5: Commit**

```bash
git add src/utils/ledger.py src/tests/test_ledger.py
git commit -m "feat(ledger): state transitions with guards; no-events rows; max_index

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: ledger 对账 + 查询（reconcile / event_statuses / is_date_terminal / post_slug / harvest / untracked）

**Files:**
- Modify: `src/utils/ledger.py`（追加）
- Test: `src/tests/test_ledger.py`（追加）

**Interfaces:**
- Consumes: Task 1–2。
- Produces: `reconcile(pipeline_dir=None) -> list[dict]`, `event_statuses(date_str, pipeline_dir=None) -> dict[int, str]`, `is_date_terminal(date_str, pipeline_dir=None) -> bool`, `post_slug(date_str, n, pipeline_dir=None) -> str`, `pending_harvest(pipeline_dir=None) -> list[tuple[str, int]]`, `mark_harvested(date_str, n, pipeline_dir=None)`, `get_untracked_dates(days=7, pipeline_dir=None) -> list[str]`
- 对账规则（spec）：非终态行按工件推导，`review-vN` > `draft-vN` > `research`，版本取最大；无工件时 candidate/selected 不动；**任何状态读取先对账**。

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 src/tests/test_ledger.py
def _artifacts(tmp_path, *relpaths):
    for rel in relpaths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")


def test_reconcile_derives_stage_and_version(tmp_path):
    _seed(tmp_path, state="selected")
    _artifacts(tmp_path,
               "research/990101-1-标题一.md",
               "draft/990101-1-标题一-v1.md",
               "draft/990101-1-标题一-v2.md")
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "draft-v2"}
    _artifacts(tmp_path, "review/990101-1-标题一-v2.md")
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "review-v2"}
    # 对账结果写回了 CSV
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["状态"] == "review-v2"


def test_reconcile_ignores_terminal_and_other_events(tmp_path):
    _seed(tmp_path)
    ledger.add_event("990101", 10, "十", pipeline_dir=tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    # 事件 1 的工件不得污染事件 10（前缀含结尾连字符）
    _artifacts(tmp_path, "draft/990101-1-标题一-v3.md")
    st = ledger.event_statuses("990101", pipeline_dir=tmp_path)
    assert st == {1: "published", 10: "candidate"}


def test_is_date_terminal(tmp_path):
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is False  # 无行
    _seed(tmp_path)
    ledger.add_event("990101", 2, "二", pipeline_dir=tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is False
    ledger.record_aborted("990101", 2, pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is True
    ledger.record_no_events("990103", pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990103", pipeline_dir=tmp_path) is True


def test_post_slug_second_published_gets_suffix(tmp_path):
    _seed(tmp_path)
    ledger.add_event("990101", 2, "二", pipeline_dir=tmp_path)
    assert ledger.post_slug("990101", 1, pipeline_dir=tmp_path) == "990101"
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.post_slug("990101", 2, pipeline_dir=tmp_path) == "990101-2"


def test_harvest_queue_roundtrip(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.pending_harvest(pipeline_dir=tmp_path) == [("990101", 1)]
    ledger.mark_harvested("990101", 1, pipeline_dir=tmp_path)
    assert ledger.pending_harvest(pipeline_dir=tmp_path) == []


def test_get_untracked_dates_uses_ledger_coverage(tmp_path):
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).strftime("%y%m%d")
    assert yesterday in ledger.get_untracked_dates(pipeline_dir=tmp_path)
    ledger.record_no_events(yesterday, pipeline_dir=tmp_path)
    assert yesterday not in ledger.get_untracked_dates(pipeline_dir=tmp_path)
    assert len(ledger.get_untracked_dates(days=3, pipeline_dir=tmp_path)) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_ledger.py -q`
Expected: FAIL（`no attribute 'event_statuses'` 等）

- [ ] **Step 3: 实现**

```python
# 追加到 src/utils/ledger.py

def _derive_state(date_str: str, n: str, pipeline_dir: Path) -> str | None:
    """从工件文件推导中间态；无工件返回 None。前缀必须含结尾连字符。"""
    for stage in ("review", "draft"):
        d = pipeline_dir / stage
        if d.exists():
            versions = [int(p.stem.rsplit("-v", 1)[-1])
                        for p in d.glob(f"{date_str}-{n}-*-v*.md")]
            if versions:
                return f"{stage}-v{max(versions)}"
    d = pipeline_dir / "research"
    if d.exists() and any(d.glob(f"{date_str}-{n}-*.md")):
        return "research"
    return None


def reconcile(pipeline_dir: Path | None = None) -> list[dict]:
    """对账内建于读路径：所有状态查询先经此处，遗忘不可能发生。"""
    pipeline_dir = pipeline_dir or pl.PIPELINE
    rows = read_rows(pipeline_dir)
    changed = False
    for r in rows:
        if r["状态"] in TERMINAL_STATES or not r["事件编号"]:
            continue
        derived = _derive_state(r["收录日期"], r["事件编号"], pipeline_dir)
        if derived and derived != r["状态"]:
            r["状态"] = derived
            changed = True
    if changed:
        write_rows(rows, pipeline_dir)
    return rows


def event_statuses(date_str: str, pipeline_dir: Path | None = None) -> dict[int, str]:
    return {int(r["事件编号"]): r["状态"] for r in reconcile(pipeline_dir)
            if r["收录日期"] == date_str and r["事件编号"]}


def is_date_terminal(date_str: str, pipeline_dir: Path | None = None) -> bool:
    """该收录日期所有行终态则 True；账本无该日期任何行则 False。"""
    rows = [r for r in reconcile(pipeline_dir) if r["收录日期"] == date_str]
    return bool(rows) and all(r["状态"] in TERMINAL_STATES for r in rows)


def post_slug(date_str: str, n: int, pipeline_dir: Path | None = None) -> str:
    """同日已有其他事件 published 时第二篇起用 YYMMDD-N。"""
    for r in read_rows(pipeline_dir):
        if (r["收录日期"] == date_str and r["事件编号"]
                and int(r["事件编号"]) != n and r["状态"] == "published"):
            return f"{date_str}-{n}"
    return date_str


def pending_harvest(pipeline_dir: Path | None = None) -> list[tuple[str, int]]:
    return [(r["收录日期"], int(r["事件编号"])) for r in read_rows(pipeline_dir)
            if r["经验提取"] == HARVEST_PENDING]


def mark_harvested(date_str: str, n: int, pipeline_dir: Path | None = None) -> None:
    update_row(date_str, n, pipeline_dir, **{"经验提取": HARVEST_DONE})


def get_untracked_dates(days: int = 7, pipeline_dir: Path | None = None) -> list[str]:
    covered = {r["收录日期"] for r in read_rows(pipeline_dir)}
    today = date.today()
    out = []
    for i in range(1, days + 1):
        d = (today - timedelta(days=i)).strftime("%y%m%d")
        if d not in covered:
            out.append(d)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_ledger.py -q`
Expected: PASS（18 passed）

- [ ] **Step 5: Commit**

```bash
git add src/utils/ledger.py src/tests/test_ledger.py
git commit -m "feat(ledger): reconcile-on-read, statuses, terminal check, post_slug, harvest, untracked

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 归档模块（archive_event / archive_date / finalize_event / 全量清扫）

**Files:**
- Create: `src/utils/archive.py`
- Test: `src/tests/test_archive.py`

**Interfaces:**
- Consumes: `ledger.get_row / is_date_terminal / reconcile / read_rows / TERMINAL_STATES`。
- Produces: `archive_event(date_str, n, pipeline_dir=None, archive_dir=None) -> list[Path]`, `archive_date(date_str, pipeline_dir=None, archive_dir=None) -> list[Path]`, `finalize_event(date_str, n, pipeline_dir=None, archive_dir=None) -> bool`（True = 整日期已收尾）, `sweep(pipeline_dir=None, archive_dir=None) -> list[Path]`（全量清扫，接替旧 `--backfill`）。
- 语义（spec 方案 A）：事件终态（published/abort）→ 立即归档其 `research/draft/review` 下 `{date}-{n}-` 前缀条目（含 `-assets/` 目录）；`events/{date}.md` 保留到整日期终态。幂等，不覆盖已存在目标。

- [ ] **Step 1: 写失败测试**

```python
# src/tests/test_archive.py
import pytest
from pathlib import Path
from src.utils import ledger
from src.utils.archive import archive_event, archive_date, finalize_event, sweep


def _mk(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith("/"):
        p.mkdir(parents=True, exist_ok=True)
    else:
        p.write_text("x", encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path):
    pipe = tmp_path / "_pipeline"
    arch = tmp_path / "_pipeline_archive"
    pipe.mkdir()
    _mk(pipe, "events/990101.md")
    _mk(pipe, "research/990101-1-标题一.md")
    _mk(pipe, "draft/990101-1-标题一-v1.md")
    (pipe / "draft" / "990101-1-assets").mkdir()
    _mk(pipe, "review/990101-1-标题一-v1.md")
    _mk(pipe, "research/990101-10-十.md")     # 前缀陷阱：1 不得匹配 10
    ledger.add_event("990101", 1, "标题一", pipeline_dir=pipe)
    ledger.add_event("990101", 10, "十", pipeline_dir=pipe)
    return pipe, arch


def test_archive_event_moves_only_target_event(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    moved = archive_event("990101", 1, pipeline_dir=pipe, archive_dir=arch)
    assert (arch / "draft" / "990101-1-assets").is_dir()
    assert (arch / "review" / "990101-1-标题一-v1.md").exists()
    assert (pipe / "research" / "990101-10-十.md").exists()      # 未被误搬
    assert (pipe / "events" / "990101.md").exists()               # 共享文件不动
    assert len(moved) == 4
    assert archive_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) == []  # 幂等


def test_finalize_event_noop_when_not_terminal(env):
    pipe, arch = env
    assert finalize_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) is False
    assert (pipe / "draft" / "990101-1-标题一-v1.md").exists()


def test_finalize_event_archives_and_finalizes_date_when_all_terminal(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert finalize_event("990101", 1, pipeline_dir=pipe, archive_dir=arch) is False
    assert (pipe / "events" / "990101.md").exists()   # 事件 10 未终态，md 保留
    ledger.record_aborted("990101", 10, pipeline_dir=pipe)
    assert finalize_event("990101", 10, pipeline_dir=pipe, archive_dir=arch) is True
    assert (arch / "events" / "990101.md").exists()   # 整日期收尾


def test_sweep_archives_all_terminal_events(env):
    pipe, arch = env
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    ledger.record_aborted("990101", 10, pipeline_dir=pipe)
    moved = sweep(pipeline_dir=pipe, archive_dir=arch)
    assert (arch / "events" / "990101.md").exists()
    assert moved and not (pipe / "review" / "990101-1-标题一-v1.md").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_archive.py -q`
Expected: FAIL（`No module named 'src.utils.archive'`）

- [ ] **Step 3: 实现**

```python
# src/utils/archive.py
"""按事件/按日期归档。状态判断一律来自 ledger（读路径内建对账）。"""
from __future__ import annotations
import shutil
from pathlib import Path

from src.utils import pipeline as pl
from src.utils import ledger

_EVENT_STAGES = ("research", "draft", "review")


def _move_into(entry: Path, dst_dir: Path) -> Path | None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / entry.name
    if dst.exists():
        return None  # 已归档——不覆盖
    shutil.move(str(entry), str(dst))
    return dst


def archive_event(date_str: str, n: int | str,
                  pipeline_dir: Path | None = None,
                  archive_dir: Path | None = None) -> list[Path]:
    pipeline_dir = pipeline_dir or pl.PIPELINE
    archive_dir = archive_dir or pl.ARCHIVE
    moved: list[Path] = []
    prefix = f"{date_str}-{n}-"   # 结尾连字符：n=1 不匹配 n=10
    for stage in _EVENT_STAGES:
        src_dir = pipeline_dir / stage
        if not src_dir.exists():
            continue
        for entry in sorted(src_dir.iterdir()):
            if entry.name.startswith(prefix):
                dst = _move_into(entry, archive_dir / stage)
                if dst:
                    moved.append(dst)
    return moved


def archive_date(date_str: str,
                 pipeline_dir: Path | None = None,
                 archive_dir: Path | None = None) -> list[Path]:
    """搬走该日期的全部残留（events md + 任何 {date}- 前缀条目）。幂等。"""
    pipeline_dir = pipeline_dir or pl.PIPELINE
    archive_dir = archive_dir or pl.ARCHIVE
    moved: list[Path] = []
    for stage in ("events",) + _EVENT_STAGES:
        src_dir = pipeline_dir / stage
        if not src_dir.exists():
            continue
        for entry in sorted(src_dir.iterdir()):
            name = entry.name
            if name == f"{date_str}.md" or name.startswith(f"{date_str}-"):
                dst = _move_into(entry, archive_dir / stage)
                if dst:
                    moved.append(dst)
    return moved


def finalize_event(date_str: str, n: int | str,
                   pipeline_dir: Path | None = None,
                   archive_dir: Path | None = None) -> bool:
    """事件终态则归档其工件；整日期终态则收尾共享文件。返回整日期是否已收尾。"""
    pipeline_dir = pipeline_dir or pl.PIPELINE
    row = ledger.get_row(date_str, n, pipeline_dir)
    if row is None or row["状态"] not in ("published", "abort"):
        return False
    archive_event(date_str, n, pipeline_dir, archive_dir)
    if ledger.is_date_terminal(date_str, pipeline_dir):
        archive_date(date_str, pipeline_dir, archive_dir)
        return True
    return False


def sweep(pipeline_dir: Path | None = None,
          archive_dir: Path | None = None) -> list[Path]:
    """全量清扫：归档账本中所有终态事件的滞留工件；整日期终态则收尾。"""
    pipeline_dir = pipeline_dir or pl.PIPELINE
    moved: list[Path] = []
    rows = ledger.reconcile(pipeline_dir)
    dates = sorted({r["收录日期"] for r in rows})
    for d in dates:
        for r in rows:
            if (r["收录日期"] == d and r["事件编号"]
                    and r["状态"] in ("published", "abort")):
                moved += archive_event(d, r["事件编号"], pipeline_dir, archive_dir)
        if ledger.is_date_terminal(d, pipeline_dir):
            moved += archive_date(d, pipeline_dir, archive_dir)
    return moved
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_archive.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add src/utils/archive.py src/tests/test_archive.py
git commit -m "feat(archive): per-event archiving on ledger state; date finalize; full sweep

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `pipeline_cli.py`（status / select / abort / add / archive / harvest）

**Files:**
- Create: `src/pipeline_cli.py`
- Test: `src/tests/test_pipeline_cli.py`

**Interfaces:**
- Consumes: ledger 全部 + `archive.finalize_event` / `archive.sweep`。
- Produces: `main(argv: list[str]) -> int`。子命令：
  - `status` — 对账后打印：`最后维护: X`、`未追踪(近7天): ...`、非终态行表格、`待提取经验: ...`
  - `select <收录日期> <N...>`
  - `abort <收录日期> <N...>`（record_aborted + finalize_event）
  - `add <收录日期> <N> <标题>`（状态=selected，维护日期=当天）
  - `archive [<收录日期> [N]]`（无参=sweep；带日期+N=finalize_event；只带日期=对该日期所有终态行 finalize_event）
  - `harvest` / `harvest done <收录日期> <N>`

- [ ] **Step 1: 写失败测试**

```python
# src/tests/test_pipeline_cli.py
import pytest
from src.utils import ledger
from src.pipeline_cli import main


@pytest.fixture
def pipe(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    root.mkdir()
    (tmp_path / "_pipeline_archive").mkdir()
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    return root


def test_select_and_abort_roundtrip(pipe, capsys):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    ledger.add_event("990101", 2, "二", pipeline_dir=pipe)
    assert main(["select", "990101", "1", "2"]) == 0
    assert ledger.get_row("990101", 1, pipeline_dir=pipe)["状态"] == "selected"
    assert main(["abort", "990101", "2"]) == 0
    assert ledger.get_row("990101", 2, pipeline_dir=pipe)["状态"] == "abort"


def test_add_creates_selected_row(pipe):
    assert main(["add", "990102", "1", "手工事件"]) == 0
    row = ledger.get_row("990102", 1, pipeline_dir=pipe)
    assert row["状态"] == "selected" and row["标题"] == "手工事件"


def test_status_lists_open_events_and_harvest(pipe, capsys):
    ledger.add_event("990101", 1, "进行中", pipeline_dir=pipe)
    ledger.add_event("990101", 2, "已发", pipeline_dir=pipe)
    ledger.record_published("990101", 2, pub_title="t", pipeline_dir=pipe)
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "进行中" in out and "candidate" in out
    assert "已发" not in out          # 终态行不进在途表
    assert "990101-2" in out          # 待提取经验列出


def test_archive_subcommand_sweeps(pipe):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    (pipe / "draft").mkdir()
    (pipe / "draft" / "990101-1-一-v1.md").write_text("x", encoding="utf-8")
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert main(["archive"]) == 0
    assert not (pipe / "draft" / "990101-1-一-v1.md").exists()


def test_harvest_list_and_done(pipe, capsys):
    ledger.add_event("990101", 1, "一", pipeline_dir=pipe)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=pipe)
    assert main(["harvest"]) == 0
    assert "990101-1" in capsys.readouterr().out
    assert main(["harvest", "done", "990101", "1"]) == 0
    assert ledger.pending_harvest(pipeline_dir=pipe) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_pipeline_cli.py -q`
Expected: FAIL（`No module named 'src.pipeline_cli'`）

- [ ] **Step 3: 实现**

```python
# src/pipeline_cli.py
"""管线状态 CLI —— 状态查看与转换的唯一入口（不要裸读/裸改 events.csv）。

用法：
  python src/pipeline_cli.py status
  python src/pipeline_cli.py select <收录日期> <N...>
  python src/pipeline_cli.py abort  <收录日期> <N...>
  python src/pipeline_cli.py add    <收录日期> <N> <标题>
  python src/pipeline_cli.py archive [<收录日期> [N]]
  python src/pipeline_cli.py harvest [done <收录日期> <N>]
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils import ledger
from src.utils.archive import finalize_event, sweep


def cmd_status() -> int:
    rows = ledger.reconcile()
    maint = [r["维护日期"] for r in rows if r["维护日期"]]
    print(f"最后维护: {max(maint) if maint else '（无记录）'}")
    untracked = ledger.get_untracked_dates()
    print("未追踪(近7天): " + (", ".join(untracked) if untracked else "无"))
    open_rows = [r for r in rows
                 if r["事件编号"] and r["状态"] not in ledger.TERMINAL_STATES]
    if open_rows:
        print("\n在途事件:")
        print(f"{'收录日期':<8} {'事件':<4} {'状态':<12} 标题")
        for r in open_rows:
            print(f"{r['收录日期']:<8} {r['事件编号']:<4} {r['状态']:<12} {r['标题']}")
    else:
        print("\n在途事件: 无")
    pending = ledger.pending_harvest()
    if pending:
        print("\n待提取经验: " + ", ".join(f"{d}-{n}" for d, n in pending))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    if cmd == "status":
        return cmd_status()
    if cmd == "select":
        date_str, ns = args[0], args[1:]
        for n in ns:
            ledger.record_selected(date_str, int(n))
            print(f"{date_str}-{n}: selected")
        return 0
    if cmd == "abort":
        date_str, ns = args[0], args[1:]
        for n in ns:
            ledger.record_aborted(date_str, int(n))
            done = finalize_event(date_str, int(n))
            print(f"{date_str}-{n}: abort（工件已归档）"
                  + ("；该日期已收尾" if done else ""))
        return 0
    if cmd == "add":
        date_str, n, title = args[0], int(args[1]), args[2]
        added = ledger.add_event(date_str, n, title, state="selected")
        print(f"{date_str}-{n}: {'已补录 (selected)' if added else '已存在，未改动'}")
        return 0
    if cmd == "archive":
        if len(args) >= 2:
            done = finalize_event(args[0], int(args[1]))
            print(f"{args[0]}-{args[1]}: " + ("日期已收尾" if done else "已处理"))
        elif len(args) == 1:
            for n, st in ledger.event_statuses(args[0]).items():
                if st in ("published", "abort"):
                    finalize_event(args[0], n)
            print(f"{args[0]}: 终态事件已归档")
        else:
            moved = sweep()
            print(f"全量清扫完成，共归档 {len(moved)} 个条目")
        return 0
    if cmd == "harvest":
        if args[:1] == ["done"]:
            ledger.mark_harvested(args[1], int(args[2]))
            print(f"{args[1]}-{args[2]}: 已提取")
        else:
            for d, n in ledger.pending_harvest():
                print(f"{d}-{n}")
        return 0
    print(f"未知子命令: {cmd}\n{__doc__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_pipeline_cli.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_cli.py src/tests/test_pipeline_cli.py
git commit -m "feat(cli): pipeline_cli — status/select/abort/add/archive/harvest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: publisher 接入账本（record_published 带发布信息、post_slug、finalize_event；删 harvest 队列块）

**Files:**
- Modify: `src/publisher.py`
- Modify: `src/tests/test_publisher.py`、`src/tests/test_harvest_queue.py`

**Interfaces:**
- Consumes: `ledger.record_published(date_str, n, pub_title, pub_date=None)`, `ledger.post_slug(date_str, n)`, `archive.finalize_event(date_str, n)`。
- Produces: `publish()` 行为——发布后账本行含发布标题/发布日期/经验提取=待提取，事件工件被归档。

- [ ] **Step 1: 改测试（先红）**

`src/tests/test_harvest_queue.py`：整文件重写——

```python
# src/tests/test_harvest_queue.py —— 收割状态并入账本
import pytest
from src.utils import ledger

VALID_DRAFT = (
    "---\ntitle: 发布标题\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
    "## 概述\n正文。\n\n"
    "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(VALID_DRAFT, encoding="utf-8")
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)
    return root, draft


def test_publish_marks_harvest_pending_with_pub_fields(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    row = ledger.get_row("990101", 1, pipeline_dir=root)
    assert row["状态"] == "published"
    assert row["发布标题"] == "发布标题"
    assert row["发布日期"] != ""
    assert row["经验提取"] == "待提取"


def test_publish_twice_is_idempotent(env):
    root, draft = env
    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)
    # 第一次发布已把草稿归档；publish 读 draft 路径，重发布用归档前保存的内容路径不再存在，
    # 所以幂等性在账本层验证：直接再调 record_published 不改字段
    ledger.record_published("990101", 1, pub_title="另一个", pipeline_dir=root)
    assert ledger.get_row("990101", 1, pipeline_dir=root)["发布标题"] == "发布标题"
```

`src/tests/test_publisher.py`：`test_publish_finalizes_terminal_date` 改为——删掉三行旧 monkeypatch（`src.publisher._post_slug`、`src.publisher.record_published`、`src.publisher.finalize_if_terminal`），改为与上面 `env` 相同的 `src.utils.pipeline.PIPELINE/ARCHIVE` monkeypatch + `ledger.add_event("990101", 1, "测试", pipeline_dir=root)`，断言：`publish(...)` 后 `(tmp_path / "_pipeline_archive" / "draft" / "990101-1-测试-v1.md").exists()` 且 `(tmp_path / "_pipeline_archive" / "events")` 下无残留（单事件日期收尾时 events md 不存在也不报错）。文件顶部 imports 不变（`copy_draft` 等测试保留原样）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_harvest_queue.py src/tests/test_publisher.py -q`
Expected: FAIL（publisher 仍引用 `_post_slug`/`finalize_if_terminal`/旧 `record_published` 签名）

- [ ] **Step 3: 改 publisher**

`src/publisher.py` 精确修改：

```python
# imports 区（第 8–11 行）改为：
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import REPO_ROOT, PIPELINE
from src.utils import ledger
from src.utils.archive import finalize_event
```

```python
# publish() 内（原第 69 行）：
    post_slug = ledger.post_slug(date_str, n)
```

```python
# publish() 尾部：原第 87–99 行（record_published(date_str, n) … finalize_if_terminal 块）整体替换为：
    ledger.record_published(date_str, n, pub_title=str(fm.get("title", title)))
    print(f"Recorded {date_str}-{n} as published in events.csv (经验提取=待提取)")

    if finalize_event(date_str, n):
        print(f"Date {date_str} complete → archived to _pipeline_archive/")
    else:
        print(f"Event {date_str}-{n} artifacts archived to _pipeline_archive/")
```

（删除 harvest-queue 追加块与其 print。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/test_publisher.py src/tests/test_harvest_queue.py src/tests/test_ledger.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/publisher.py src/tests/test_publisher.py src/tests/test_harvest_queue.py
git commit -m "feat(publisher): record to ledger with pub title/date; per-event archive; drop harvest queue file

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: tracker 接入账本（事件行、无事件行、去 .state）

**Files:**
- Modify: `src/tracker.py`
- Modify: `src/tests/test_tracker.py`、`src/tests/test_tracker_daily.py`、`src/tests/test_tracker_urls.py`（按 Step 2 的失败逐个适配）

**Interfaces:**
- Consumes: `ledger.add_event`, `ledger.record_no_events`, `ledger.max_index`。
- Produces: `write_events_file(date_str, events) -> Path | None`（空事件 → 不写 md、记无事件行、返回 None）；`append_events_to_file` 同步账本行。

- [ ] **Step 1: 加失败测试**

在 `src/tests/test_tracker.py` 追加（该文件已有 monkeypatch `src.utils.pipeline.PIPELINE` 的惯例；若无则按此建 fixture）：

```python
def test_write_events_file_records_ledger_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file
    from src.utils import ledger
    out = write_events_file("990101", [
        {"title": "甲", "brief": "b", "sources": []},
        {"title": "乙", "brief": "b", "sources": []},
    ])
    assert out is not None and out.exists()
    st = {int(r["事件编号"]): r for r in ledger.read_rows(pipeline_dir=tmp_path)}
    assert st[1]["标题"] == "甲" and st[1]["状态"] == "candidate"
    assert st[2]["标题"] == "乙"


def test_write_events_file_empty_records_no_events_without_md(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file
    from src.utils import ledger
    out = write_events_file("990102", [])
    assert out is None
    assert not (tmp_path / "events" / "990102.md").exists()
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    assert rows[0]["收录日期"] == "990102" and rows[0]["状态"] == "无事件"


def test_append_events_continues_ledger_index(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file, append_events_to_file
    from src.utils import ledger
    write_events_file("990103", [{"title": "甲", "brief": "b", "sources": []}])
    append_events_to_file("990103", [{"title": "乙", "brief": "b", "sources": []}])
    assert ledger.get_row("990103", 2, pipeline_dir=tmp_path)["标题"] == "乙"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_tracker.py -q`
Expected: 新增 3 条 FAIL

- [ ] **Step 3: 改 tracker**

```python
# src/tracker.py 第 18 行改为：
from src.utils.pipeline import events_path
from src.utils import ledger
```

```python
# write_events_file 替换为：
def write_events_file(date_str: str, events: list[dict]) -> Path | None:
    """写 events md（人读内容）并同步账本行。空事件：只记"无事件"行，不写 md。"""
    if not events:
        ledger.record_no_events(date_str)
        return None
    numbered = [dict(e, index=i + 1) for i, e in enumerate(events)]
    out = events_path(date_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_events(date_str, numbered), encoding="utf-8")
    for ev in numbered:
        ledger.add_event(date_str, ev["index"], ev["title"])
    return out
```

```python
# append_events_to_file：offset 行改为（md 计数与账本取大，md 丢失也不撞号）：
    offset = max(count_existing_events(out), ledger.max_index(date_str))
# 函数末尾 return 前追加：
    for ev in numbered:
        ledger.add_event(date_str, ev["index"], ev["title"])
```

（`append_events_to_file` 开头 `if not out.exists(): return write_events_file(...)` 与 `if not new_events: return out` 两个早退保持不变；后者之前不 add。）

删除 `set_state` 的两处调用（原 246、303 行）及其 import；`run_tracker` 的输出行改为：

```python
    print(f"Wrote {len(events)} events" + (f" to {out}" if out else " (无事件，已记录)"))
```

`run_tracker_range` 循环内 `out = writer(date_str, events)` 之后的 print 用 `out or '（无事件行）'`。

同步修 `src/tests/test_tracker_daily.py` / `test_tracker_urls.py`：跑一遍，凡因 `set_state` 缺失或 `write_events_file` 返回 None 断言失败的用例，按新行为更新断言（空事件日期断言"无 md + 账本无事件行"）。

- [ ] **Step 4: 跑全量测试确认通过**

Run: `python -m pytest src/tests/ -q`
Expected: PASS（test_pipeline_status/test_archiver 里引用旧函数的用例仍在——它们此刻还应通过，因为旧函数还没删）

- [ ] **Step 5: Commit**

```bash
git add src/tracker.py src/tests/test_tracker.py src/tests/test_tracker_daily.py src/tests/test_tracker_urls.py
git commit -m "feat(tracker): write ledger rows alongside events md; no-events rows; drop .state

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: 删除旧状态机代码与旧测试

**Files:**
- Modify: `src/utils/pipeline.py`
- Delete: `src/archiver.py`、`src/tests/test_archiver.py`、`src/tests/test_pipeline_status.py`

**Interfaces:**
- Produces: `pipeline.py` 只剩：`REPO_ROOT/PIPELINE/ARCHIVE` 常量 + 路径助手（`events_path`、`research_path`、`find_research_file`、`next_draft_path`、`latest_draft`、`review_path`、`next_review_path`、`latest_review`、`get_event_titles`）。

- [ ] **Step 1: 删代码**

从 `src/utils/pipeline.py` 删除：`STATE_FILE`、`_STORED_STATES`、`_status_path`、`_read_status_entries`、`_write_status_entries`、`record_selected`、`record_aborted`、`event_status`、`event_statuses`、`record_published`、`_done_dates_path`、`_read_done_dates`、`mark_done`、`is_date_terminal`、`_ARCHIVE_STAGES`、`archive_date`、`finalize_if_terminal`、`_post_slug`、`get_state`、`set_state`、`set_last_tracked_date`、`get_untracked_dates`、`pipeline_summary`，以及顶部现已无用的 `shutil`、`date/timedelta` import。

删除文件：`git rm src/archiver.py src/tests/test_archiver.py src/tests/test_pipeline_status.py`（其职责已由 `pipeline_cli archive`/`test_archive.py`/`test_ledger.py` 接替）。

- [ ] **Step 2: 全库 grep 确认无残留引用**

Run: `grep -rn 'finalize_if_terminal\|_post_slug\|mark_done\|_read_done_dates\|set_state\|get_state\|pipeline_summary\|record_selected\|archiver' src --include='*.py' | grep -v venv`
Expected: 无输出（或仅 ledger/cli 内自身定义）

- [ ] **Step 3: 跑全量测试**

Run: `python -m pytest src/tests/ -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add -A src
git commit -m "refactor(pipeline): remove sidecar/done-dates/.state machinery superseded by ledger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: 迁移——生成初始 events.csv，删除旧载体文件

**Files:**
- Create: `src/migrate_ledger.py`（用完即删）

- [ ] **Step 1: 写迁移脚本**

```python
# src/migrate_ledger.py —— 一次性：由现存侧车/工件/归档/文章生成初始账本。跑完删除本文件。
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import REPO_ROOT, PIPELINE, ARCHIVE
from src.utils import ledger

POSTS = REPO_ROOT / "source" / "_posts"


def sidecar_entries(p: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                n, _, state = line.partition(":")
                out[int(n)] = state
    return out


def titles_from_md(p: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    if p.exists():
        for m in re.finditer(r"^## (\d+)\. (.+)$",
                             p.read_text(encoding="utf-8"), re.MULTILINE):
            out[int(m.group(1))] = m.group(2).strip()
    return out


def artifact_indexes(date_str: str) -> dict[int, str]:
    """{n: derived_state} 综合 _pipeline 与 _pipeline_archive 的工件。"""
    out: dict[int, str] = {}
    for root in (PIPELINE, ARCHIVE):
        for n_str in {m.group(1)
                      for stage in ("research", "draft", "review")
                      if (root / stage).exists()
                      for f in (root / stage).iterdir()
                      if (m := re.match(rf"{date_str}-(\d+)-", f.name))}:
            derived = ledger._derive_state(date_str, n_str, root)
            n = int(n_str)
            if derived and (n not in out or derived > out[n]):
                out[n] = derived
    return out


def post_info(date_str: str, n: int) -> tuple[str, str]:
    """(发布日期, 发布标题)：文件首次入库的 git 日期 + frontmatter title。"""
    for name in (f"{date_str}-{n}.md", f"{date_str}.md"):
        p = POSTS / name
        if p.exists():
            m = re.search(r"^title:\s*(.+)$", p.read_text(encoding="utf-8"),
                          re.MULTILINE)
            title = m.group(1).strip() if m else ""
            r = subprocess.run(
                ["git", "log", "--diff-filter=A", "--follow",
                 "--format=%ad", "--date=format:%y%m%d", "--", str(p)],
                capture_output=True, text=True, cwd=REPO_ROOT)
            dates = r.stdout.split()
            return (dates[-1] if dates else "", title)
    return ("", "")


def main() -> int:
    harvest_pending = set()
    hq = PIPELINE / "harvest-queue.txt"
    if hq.exists():
        harvest_pending = {l.strip() for l in
                           hq.read_text(encoding="utf-8").splitlines() if l.strip()}

    dates: set[str] = set()
    for root in (PIPELINE, ARCHIVE):
        ev = root / "events"
        if ev.exists():
            for f in ev.iterdir():
                m = re.match(r"^(\d{6})(?:-status\.txt|\.md)$", f.name)
                if m:
                    dates.add(m.group(1))

    rows: list[dict] = []
    for d in sorted(dates, reverse=True):
        sc = sidecar_entries(PIPELINE / "events" / f"{d}-status.txt")
        sc.update(sidecar_entries(ARCHIVE / "events" / f"{d}-status.txt"))
        titles = titles_from_md(PIPELINE / "events" / f"{d}.md")
        titles.update(titles_from_md(ARCHIVE / "events" / f"{d}.md"))
        derived = artifact_indexes(d)
        indexes = sorted(set(sc) | set(titles) | set(derived))
        if not indexes:
            rows.append({"维护日期": "", "收录日期": d, "事件编号": "",
                         "标题": "", "状态": ledger.NO_EVENTS,
                         "发布日期": "", "发布标题": "", "经验提取": ""})
            continue
        for n in indexes:
            state = sc.get(n)
            pub_date = pub_title = harvest = ""
            if state == "published":
                pub_date, pub_title = post_info(d, n)
                harvest = (ledger.HARVEST_PENDING if f"{d}-{n}" in harvest_pending
                           else ledger.HARVEST_DONE)
            elif state != "abort":
                state = derived.get(n) or ("selected" if state == "selected"
                                           else "candidate")
            rows.append({"维护日期": "", "收录日期": d, "事件编号": str(n),
                         "标题": titles.get(n, ""), "状态": state,
                         "发布日期": pub_date, "发布标题": pub_title,
                         "经验提取": harvest})
    ledger.write_rows(rows)
    print(f"写入 {len(rows)} 行 → {ledger.ledger_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 跑迁移并核对**

```bash
source src/venv/bin/activate && python src/migrate_ledger.py
python src/pipeline_cli.py status
```

核对清单（对着输出人工核）：
- 在途事件应恰为：`260416-*`、`260417-*`、`260418-*`、`260421-*`、`260423-*`、`260424-*`、`260427-*`、`260428-*` 中侧车未记终态的行 + `260524-1`（reviewed）；`260524-2` 为 published。
- `260322/260323/260510/260515` 出现为 `无事件` 行。
- 归档日期（260501…260601 等）全部终态。
- 抽查 2–3 个 published 行的 发布标题/发布日期 与 `source/_posts` 一致。

- [ ] **Step 3: 删除旧载体并归档存量**

```bash
git add _pipeline/events.csv
git rm _pipeline/done-dates.txt _pipeline/events/*-status.txt
git rm _pipeline/events/260322.md _pipeline/events/260323.md _pipeline/events/260510.md _pipeline/events/260515.md
rm -f _pipeline/.state _pipeline/harvest-queue.txt
python src/pipeline_cli.py archive    # 全量清扫：260524-2 滞留工件归档
git add -A _pipeline _pipeline_archive
```

- [ ] **Step 4: 全量测试 + 提交 + 删脚本**

```bash
python -m pytest src/tests/ -q     # PASS
git add -A && git commit -m "feat(pipeline): migrate state to events.csv ledger; drop sidecars/done-dates/.state/harvest-queue

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git rm src/migrate_ledger.py && git commit -m "chore: remove one-shot ledger migration script

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: TAG-PROPOSAL —— linter 豁免 + publisher 发布门禁

**Files:**
- Modify: `src/linter.py`、`src/publisher.py`
- Test: `src/tests/test_linter.py`（追加）、`src/tests/test_publisher.py`（追加）

**Interfaces:**
- Produces: `linter.TAG_PROPOSAL_RE`（模式：`<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->`）；lint 规则：frontmatter tags 为空且无提案 → 违规；publisher：草稿含未裁决提案 → `SystemExit`。

- [ ] **Step 1: 追加失败测试**

```python
# src/tests/test_linter.py 追加
from datetime import date as _date
from src.linter import lint_text

BASE = (
    "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:{TAGS}\n---\n\n"
    "{BODY}## 概述\n正文。\n\n"
    "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n"
)


def test_empty_tags_with_proposal_passes():
    content = BASE.format(TAGS=" []", BODY="<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n\n")
    assert not [v for v in lint_text(content, {"犯罪"}, _date(2020, 1, 2))
                if "tags" in v]


def test_empty_tags_without_proposal_fails():
    content = BASE.format(TAGS=" []", BODY="")
    assert any("tags" in v for v in lint_text(content, {"犯罪"}, _date(2020, 1, 2)))


def test_unregistered_tag_still_fails_even_with_proposal():
    content = BASE.format(TAGS="\n- 未注册", BODY="<!-- [TAG-PROPOSAL]: x — y -->\n\n")
    assert any("未注册" in v for v in lint_text(content, {"犯罪"}, _date(2020, 1, 2)))
```

```python
# src/tests/test_publisher.py 追加
def test_publish_refuses_unresolved_tag_proposal(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    (tmp_path / "_pipeline_archive").mkdir()
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text(
        "---\ntitle: t\ndate: 2020-01-01\ncategories: B\ntags:\n- 犯罪\n---\n\n"
        "<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n\n"
        "## 概述\n正文。\n\n"
        "## 信息来源\n2020.01.01，来源。*标题*。https://example.com/a\n",
        encoding="utf-8")
    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", root)
    monkeypatch.setattr("src.utils.pipeline.ARCHIVE", tmp_path / "_pipeline_archive")
    from src.utils import ledger
    ledger.add_event("990101", 1, "测试", pipeline_dir=root)
    from src.publisher import publish
    with pytest.raises(SystemExit, match="TAG-PROPOSAL"):
        publish("990101", 1, "测试", draft, deploy=False)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest src/tests/test_linter.py src/tests/test_publisher.py -q`
Expected: 新增用例 FAIL

- [ ] **Step 3: 实现**

`src/linter.py`：模块顶部加

```python
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")
```

`lint_text` 中 tags 检查（原第 66–68 行）改为：

```python
    tags = fm.get("tags") or []
    if not tags and not TAG_PROPOSAL_RE.search(content):
        violations.append(
            "tags 为空且无 TAG-PROPOSAL —— 选 2 个以上贴切标签，或用 "
            "<!-- [TAG-PROPOSAL]: 标签名 — 理由 --> 提案新标签"
        )
```

`src/publisher.py` `publish()` 中 `validate_tags(...)` 之后插入：

```python
    from src.linter import TAG_PROPOSAL_RE
    proposals = TAG_PROPOSAL_RE.findall(content)
    if proposals:
        raise SystemExit(
            "未裁决的 [TAG-PROPOSAL]，拒绝发布：\n"
            + "\n".join(f"  - {p}" for p in proposals)
            + "\n批准：将标签加入 src/tags.yml 相应分组和草稿 frontmatter，删除注释；"
              "否决：删除注释。"
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest src/tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/linter.py src/publisher.py src/tests/test_linter.py src/tests/test_publisher.py
git commit -m "feat(tags): TAG-PROPOSAL — lint waiver for empty tags; publish gate on unresolved proposals

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: TAG-PROPOSAL —— 三个 skill 的文案

**Files:**
- Modify: `.claude/skills/blog-write/SKILL.md`、`.claude/skills/blog-review/SKILL.md`、`.claude/skills/blog-orchestrator/SKILL.md`

- [ ] **Step 1: blog-write Tags 节替换**

将 Tags 节中这两段：

> **Every v1 draft must carry 2+ tags** … The linter rejects empty tags.
>
> If the event genuinely needs a new tag, stop and ask the user before inventing one; do not silently coin new tags in a draft.

替换为：

```markdown
**Tags must genuinely fit.** Do NOT pad with tangentially-related tags to hit a count.
Frontmatter may only contain registered tags. If fewer than 2 registered tags genuinely
fit, or an important theme has no tag, add a proposal comment right after the frontmatter
(one per line, several allowed):

    <!-- [TAG-PROPOSAL]: 标签名 — 理由 -->

Registered tags + proposals together must be ≥ 2. Proposals are adjudicated by the user
at the review gate; the publisher refuses to deploy a draft with unresolved proposals,
and the linter accepts an empty tags list only when a proposal comment is present.
```

- [ ] **Step 2: blog-review 增加转录要求**

在 Review Process 第 6 条后追加第 7 条：

```markdown
7. **Transcribe tag proposals** — copy every `<!-- [TAG-PROPOSAL]: ... -->` comment
   from the draft into a dedicated `## 标签提案` section of the review file, so the
   user sees them at the review gate. Do not resolve them yourself.
```

- [ ] **Step 3: orchestrator 4b-ii 增加裁决步骤**

在 4b-ii 的报告句后追加：

```markdown
If the review file has a `## 标签提案` section (or the draft contains
`<!-- [TAG-PROPOSAL]: ... -->`), list each proposal and ask the user to approve or
reject. Approved: add the tag to the matching group in `src/tags.yml`, add it to the
draft's frontmatter `tags:`, and delete the proposal comment (mechanical edits — do
them directly, no subagent). Rejected: delete the proposal comment.
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/blog-write/SKILL.md .claude/skills/blog-review/SKILL.md .claude/skills/blog-orchestrator/SKILL.md
git commit -m "docs(skills): TAG-PROPOSAL protocol — writer proposes, reviewer transcribes, user adjudicates

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: template.md 唯一格式权威 + skill/CLAUDE.md 指针

**Files:**
- Rewrite: `source/_drafts/template.md`
- Modify: `.claude/skills/blog-write/SKILL.md`、`.claude/skills/blog-review/SKILL.md`、`.claude/skills/blog-orchestrator/SKILL.md`、`.claude/skills/blog-curate/SKILL.md`、`CLAUDE.md`

- [ ] **Step 1: 重写 template.md（完整内容）**

```markdown
---
title: （文章标题）
date: 2026-01-01   # 最新事实性进展的发生日（YYYY-MM-DD，禁止时间成分；不是报道日/搜索日）
categories: B      # 单字母 S/A/B/C/D/N；判级边界见 blog-write skill
tags:              # 只用 src/tags.yml 已注册标签，且必须真正贴切（禁止凑数）
- 犯罪
# 需要新标签时不要自造：在 frontmatter 之后写
# <!-- [TAG-PROPOSAL]: 标签名 — 理由 -->
---

## 概述
（2–4 句中性概述。所有案件相关内容——时间线、前情、后续、判决细节、各方主张、
受害者自述——都以 #### 子节放在本节内，不得另立独立章节。日期加粗：**YYYY年M月D日**：…）

#### 时间线（按需）
#### 判决要点（按需）

## 信息来源
（一行一条，格式精确为：）
2026.01.01，来源名称。*标题*。https://example.com/ 或 {% asset_path file.pdf %}

## 舆论
（可选。只写具体数据：阅读量/讨论量/转发量/评论量/投票结果。
没有任何具体数字就整节删除——连标题都不要留。
禁止"网友纷纷表示""引发热议"、任何评论转述或对舆论的定性。）
### 微博词条
#词条名# 访问日期：2026.01.01。阅读量：N万。

## 相关内容
（可选。只放一般性/对比性材料：法条原文、同类案件、结构性背景。
案件本身的内容一律进 ## 概述 的 #### 子节。同"只有事实"规则，无评论。）

<!-- 行内格式约定：
  <font color="red">…</font>   法律/事实上关键的表述、核心认定
  <font color="blue">…</font>  最新一条真实事实进展（不能是"暂无进展"类句子）
  <font color="grey">…</font>  当事人/法院/官方的逐字引用（所有逐字引用必须用灰色）
资产嵌入（文件放 _pipeline/draft/{date}-{index}-assets/）：
  <img src="{% asset_path 文件名.jpg %}" width="300" alt="说明">
  <embed src="{% asset_path 文件.pdf %}" type="application/pdf" width="100%" height="600px">
风格硬规则：不用破折号（—）；不写填充语（"此事沉寂数月后"等）；每句话必须
有来源直接支撑，不推断不引申；剥离一切具名专家评论。 -->
```

- [ ] **Step 2: blog-write 收缩**

Draft Format 节（含代码块骨架）、Inline Formatting 节、Assets 节整体替换为一节：

```markdown
## Draft Format

**The canonical format spec is `source/_drafts/template.md` — read it in full before
writing.** It defines frontmatter fields, section skeleton and per-section content
rules, the `<font>` colour conventions, and asset embedding. Structure deviations are
review-blocking. Use published posts in `source/_posts/` only as prose-style reference —
older posts may predate current format rules; when they conflict, template.md wins.
```

（Modes、Tracking、Blue font rule、Revision、Output Path、Style Rules、Categories、Tags、lint 关卡各节保留。Style Rules 中与 template 注释重复的条目保留——它们是 writer 的工作规则，template 是格式权威，允许一句话级重叠。）

- [ ] **Step 3: blog-review 第 6 条具体化**

替换第 6 条为：

```markdown
6. **Check structure and format against the canonical template** — read
   `source/_drafts/template.md` first, then compare the draft section by section:
   section names/order, 概述-only placement of case-specific content (#### sub-sections),
   信息来源 line format, 舆论 concrete-metrics rule, 相关内容 scope, `<font>` colour
   usage, category value, tag registration. Every deviation is an ISSUE (STATUS: ISSUES),
   not a stylistic preference.
```

- [ ] **Step 4: orchestrator 派发块加硬指令**

Stage 3（write dispatch）参数块前加一行：

```markdown
The subagent prompt MUST begin by instructing it to read, in order:
`.claude/skills/blog-write/SKILL.md`, `.claude/skills/blog-write/notes.md`,
`source/_drafts/template.md` — before writing anything.
```

4b-i（review dispatch）参数块前加同款（对应 blog-review 的 SKILL.md/notes.md + template.md）。4b-iii（revision）沿用 write 的要求。

- [ ] **Step 5: CLAUDE.md Post Format 节替换**

```markdown
## Post Format

The canonical **format** spec — frontmatter, section structure, per-section content
rules, inline `<font>` conventions, asset embedding — lives in
`source/_drafts/template.md` (never rendered: `render_drafts: false`).
Judgment rules — categories boundaries, tag selection and TAG-PROPOSAL protocol,
style/no-inference rules — live in the `blog-write` skill. Edit those two files; do
not duplicate the spec here or it will drift.
```

- [ ] **Step 6: blog-curate 促升指南补一行**

在 "Prefer code over prose (anti-bloat)" 段落末尾追加：

```markdown
Routing when promoting: mechanically checkable → `src/linter.py` (with a test);
format/structure rules → `source/_drafts/template.md`; judgment rules → the skill's
`SKILL.md`.
```

- [ ] **Step 7: Commit**

```bash
git add source/_drafts/template.md .claude/skills CLAUDE.md
git commit -m "docs(template): template.md is the single format authority; skills point to it

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: 杂项一致性修正（D）

**Files:**
- Modify: `.claude/skills/blog-orchestrator/SKILL.md`、`.claude/skills/blog-research/SKILL.md`、`CLAUDE.md`
- Delete: `_pipeline/events/--date.md`

- [ ] **Step 1: 逐项修改**

1. orchestrator Environment 节：`The pipeline reads from environment variables or `.env` in the repo root:` → `The pipeline reads from environment variables or **`src/.env`** (not the repo root):`。CLAUDE.md Environment Variables 节首行后加一句：`The file lives at `src/.env` (gitignored) — not the repo root.`
2. CLAUDE.md Pipeline Overview 与 orchestrator 概览中的发布产物行改为：`source/_posts/YYMMDD.md（同日第二篇起为 YYMMDD-N.md）`。
3. blog-research：开头加 `**Write the entire file in Simplified Chinese** — 中文成文，英文仅限专名。`；Output 模板章节标题改为 `## 事实` / `## 当事方` / `## 信息来源`；Search Strategy 第 4 步改为 `4. Search title + "判决" or "立案" or "通报" → find case-fact/legal developments (statutes, rulings, official notices)`；Coverage Standard 的 `Legal/expert commentary…` 一条改为 `Statute/ruling facts (法条、司法解释、判决结果) if the case involves criminal law — do NOT collect named-expert commentary; the writer must strip it`。CLAUDE.md Stage 2 的 sections 行同步为 `## 事实`, `## 当事方`, `## 信息来源`。
4. `git rm '_pipeline/events/--date.md'`
5. orchestrator 5b：`runs `pnpm run deploy`` → `runs `pnpm build` + `pnpm run deploy``。

- [ ] **Step 2: Commit**

```bash
git add -A .claude CLAUDE.md _pipeline
git commit -m "docs: fix .env path, post filename, research language/scope; drop --date.md junk

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: E 的文档收尾（CLAUDE.md 管线总览 + orchestrator/curate 接 CLI）

**Files:**
- Modify: `CLAUDE.md`、`.claude/skills/blog-orchestrator/SKILL.md`、`.claude/skills/blog-curate/SKILL.md`

- [ ] **Step 1: CLAUDE.md Pipeline Overview 重写**

将目录树与 "Pipeline check" 段替换为：

```markdown
```
_pipeline/
  events.csv                 # 状态唯一权威（账本）：一行一事件；只经 pipeline_cli/代码写
  events/YYMMDD.md           # 事件内容（brief/来源），人和 agent 读；状态代码不解析
  research/YYMMDD-N-title.md # Stage 2 输出
  draft/YYMMDD-N-title-vN.md # Stage 3 输出（+ YYMMDD-N-assets/）
  review/YYMMDD-N-title-vN.md# Stage 4 输出
  summary/YYMM.md            # 月度总结草稿（on-demand）
  .tracker-state.json        # tracker 增量游标（内部）
```

**Pipeline check:** `python src/pipeline_cli.py status` — 对账后列出在途事件与待提取经验。
不要裸读/裸改 events.csv（对账内建于 CLI 读路径）。状态流：candidate → selected →
research → draft-vN → review-vN → published/abort（终态；`无事件` 行标记查过但无事件的日期）。
事件一到终态即按事件归档到 `_pipeline_archive/`；日期全终态后其 events md 一并归档。
```

Stage 5 节中 harvest-queue 句改为：`Each successful publish marks the event 待提取 in events.csv; run the blog-curate skill periodically…`。

- [ ] **Step 2: orchestrator 接 CLI**

- 1a 的 python 片段替换为：`python src/pipeline_cli.py status`（说明输出含未追踪日期）。
- 1c 的 record_selected 片段替换为：`python src/pipeline_cli.py select YYMMDD N [N...]`；同处加一句：`To drop an event at any gate: python src/pipeline_cli.py abort YYMMDD N（记录 abort 并立即归档其工件）`。
- 4b-ii 的 latest_review python 片段保留（读 review 文件，与状态无关）。
- 手工补录（tracker 限流工作流）提示：`python src/pipeline_cli.py add YYMMDD N 标题` + 手写 `events/YYMMDD.md` 条目。

- [ ] **Step 3: curate 接账本**

Harvest 节首段改为：

```markdown
`python src/pipeline_cli.py harvest` lists published events (`YYMMDD-N`) whose
corrections have not yet been distilled (经验提取=待提取 in `_pipeline/events.csv`;
the publisher marks each publish 待提取). For each entry (files may sit in
`_pipeline/` or `_pipeline_archive/` after archiving):
```

第 3 步 `Remove processed entries from the queue.` 改为：`Mark each processed entry: python src/pipeline_cli.py harvest done YYMMDD N`。

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .claude/skills/blog-orchestrator/SKILL.md .claude/skills/blog-curate/SKILL.md
git commit -m "docs: pipeline overview on ledger; orchestrator/curate use pipeline_cli

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 15: 终检

- [ ] **Step 1: 全量测试**

Run: `source src/venv/bin/activate && python -m pytest src/tests/ -q`
Expected: 全绿

- [ ] **Step 2: 真实数据冒烟**

```bash
python src/pipeline_cli.py status      # 在途应只剩 260524-1（review-v2，若你已修订）等真实在途
grep -c '' _pipeline/events.csv        # 行数 = 事件行+无事件行+表头，粗核
ls _pipeline/events/                   # 应只剩在途日期的 md（无 *-status.txt、无空存根）
```

- [ ] **Step 3: 收尾 grep（确认无旧载体残留引用）**

Run: `grep -rn 'harvest-queue\|done-dates\|status\.txt\|\.state\b' src .claude CLAUDE.md --include='*.py' --include='*.md' | grep -v venv | grep -v _archive | grep -v specs | grep -v plans`
Expected: 无输出

- [ ] **Step 4: 提交收尾（如有零星改动）并向用户汇报**
