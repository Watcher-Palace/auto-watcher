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
# staged＝暂无可靠来源/相关性未定但值得关注、等后续报道：不发布，草稿移入 source/_drafts 存查
EVENT_TERMINAL_STATES = {"published", "abort", "staged"}
TERMINAL_STATES = EVENT_TERMINAL_STATES | {NO_EVENTS}
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
    if row["状态"] in EVENT_TERMINAL_STATES:
        raise RuntimeError(f"{date_str}-{n} 已是终态 {row['状态']}，不能 select")
    if row["状态"] == "candidate":
        update_row(date_str, n, pipeline_dir, **{"状态": "selected"})


def record_aborted(date_str: str, n: int, pipeline_dir: Path | None = None) -> None:
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] in ("published", "staged"):
        raise RuntimeError(
            f"{date_str}-{n} 已是终态 {row['状态']}，不能 abort；如确需请手改 CSV")
    update_row(date_str, n, pipeline_dir, **{"状态": "abort"})


def record_staged(date_str: str, n: int, pipeline_dir: Path | None = None) -> None:
    """终态 staged：暂无可靠来源/相关性未定但值得关注，等后续报道。幂等。"""
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] == "staged":
        return
    if row["状态"] in ("published", "abort"):
        raise RuntimeError(
            f"{date_str}-{n} 已是终态 {row['状态']}，不能 staged；如确需请手改 CSV")
    update_row(date_str, n, pipeline_dir, **{"状态": "staged"})


def record_published(date_str: str, n: int, pub_title: str = "",
                     pub_date: str | None = None,
                     pipeline_dir: Path | None = None) -> None:
    row = get_row(date_str, n, pipeline_dir)
    if row is None:
        raise KeyError(f"账本中无 {date_str}-{n} 行")
    if row["状态"] == "published":
        return
    if row["状态"] in ("abort", "staged"):
        raise RuntimeError(f"{date_str}-{n} 已 {row['状态']}；如确需发布请手改 CSV")
    update_row(date_str, n, pipeline_dir, **{
        "状态": "published", "发布日期": pub_date or _today(),
        "发布标题": pub_title, "经验提取": HARVEST_PENDING})


def max_index(date_str: str, pipeline_dir: Path | None = None) -> int:
    ns = [int(r["事件编号"]) for r in read_rows(pipeline_dir)
          if r["收录日期"] == date_str and r["事件编号"]]
    return max(ns) if ns else 0


def _stage_max_version(pipeline_dir: Path, stage: str, date_str: str, n: str) -> int:
    """该 stage 目录下 {date}-{n}-*-vK.md 的最大 K；无匹配或后缀非数字（如
    `-video.md` 误撞 glob）一律跳过，返回 0。"""
    d = pipeline_dir / stage
    if not d.exists():
        return 0
    versions = []
    for p in d.glob(f"{date_str}-{n}-*-v*.md"):
        suffix = p.stem.rsplit("-v", 1)[-1]
        if suffix.isdigit():
            versions.append(int(suffix))
    return max(versions) if versions else 0


def _derive_state(date_str: str, n: str, pipeline_dir: Path) -> str | None:
    """从工件文件推导中间态；无工件返回 None。前缀必须含结尾连字符。

    review-vM 只覆盖 draft-vM：若最大 draft 版本 > 最大 review 版本，说明有更新的
    草稿尚未经过对应版本的评审，真实状态是 draft-vN；否则报告最大 review（若存在）
    或最大 draft。
    """
    draft_max = _stage_max_version(pipeline_dir, "draft", date_str, n)
    review_max = _stage_max_version(pipeline_dir, "review", date_str, n)
    if draft_max > review_max:
        return f"draft-v{draft_max}"
    elif review_max:
        return f"review-v{review_max}"
    elif draft_max:
        return f"draft-v{draft_max}"
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


def get_untracked_dates(days: int = 15, pipeline_dir: Path | None = None) -> list[str]:
    # 15 matches the --daily bucket window: a hole must survive that long
    # before it can silently age out of the status report (260707 did, at 7).
    covered = {r["收录日期"] for r in read_rows(pipeline_dir)}
    today = date.today()
    out = []
    for i in range(1, days + 1):
        d = (today - timedelta(days=i)).strftime("%y%m%d")
        if d not in covered:
            out.append(d)
    return out
