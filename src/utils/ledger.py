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
