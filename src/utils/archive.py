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
