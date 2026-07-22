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
    if row is None or row["状态"] not in ledger.EVENT_TERMINAL_STATES:
        return False
    archive_event(date_str, n, pipeline_dir, archive_dir)
    if ledger.is_date_terminal(date_str, pipeline_dir):
        archive_date(date_str, pipeline_dir, archive_dir)
        return True
    return False


def stage_event(date_str: str, n: int | str,
                pipeline_dir: Path | None = None,
                archive_dir: Path | None = None,
                drafts_dir: Path | None = None) -> tuple[Path | None, bool]:
    """staged 收尾：最新草稿移入 source/_drafts 存查（永不渲染），其余工件照常归档。
    返回（草稿存查路径或 None，整日期是否已收尾）。须在 record_staged 之后调用。"""
    pipeline_dir = pipeline_dir or pl.PIPELINE
    drafts_dir = drafts_dir or pl.SOURCE_DRAFTS
    parked = None
    d = pipeline_dir / "draft"
    if d.exists():
        versions = [p for p in d.glob(f"{date_str}-{n}-*-v*.md")
                    if p.stem.rsplit("-v", 1)[-1].isdigit()]
        if versions:
            latest = max(versions, key=lambda p: int(p.stem.rsplit("-v", 1)[-1]))
            parked = _move_into(latest, drafts_dir)
    done = finalize_event(date_str, n, pipeline_dir, archive_dir)
    return parked, done


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
                    and r["状态"] in ledger.EVENT_TERMINAL_STATES):
                moved += archive_event(d, r["事件编号"], pipeline_dir, archive_dir)
        if ledger.is_date_terminal(d, pipeline_dir):
            moved += archive_date(d, pipeline_dir, archive_dir)
    return moved
