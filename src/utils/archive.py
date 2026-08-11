"""按事件/按日期归档。状态判断一律来自 ledger（读路径内建对账）。"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from src.utils import pipeline as pl
from src.utils import ledger

_EVENT_STAGES = ("research", "draft", "review", "snapshots")

_SECTION_RE = re.compile(r"(?m)^## (\d+)\.")


def _move_into(entry: Path, dst_dir: Path) -> Path | None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / entry.name
    if dst.exists():
        return None  # 已归档——不覆盖
    shutil.move(str(entry), str(dst))
    return dst


def _split_events_md(text: str) -> tuple[str, list[tuple[int, str]]]:
    """拆 events md 为 (前言, [(事件号, 段文本), ...])；段文本含 ## 头到下一段前。"""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return text, []
    preamble = text[:matches[0].start()]
    secs: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        secs.append((int(m.group(1)), text[m.start():end]))
    return preamble, secs


def _merge_events_md(live: Path, archived: Path) -> Path | None:
    """把 live 里归档 md 尚无的 ## N 段并入归档 md、按事件号排序，再删 live。
    仅用于 events md 的同名碰撞（补录新事件到已归档日期）。返回归档路径。"""
    pre, arch_secs = _split_events_md(archived.read_text(encoding="utf-8"))
    _, live_secs = _split_events_md(live.read_text(encoding="utf-8"))
    arch_by_n = {n: s for n, s in arch_secs}
    # 冲突：live 有与归档同号但正文不同的段 → 整体不动，留 live 给人工裁定
    for n, s in live_secs:
        if n in arch_by_n and s.strip() != arch_by_n[n].strip():
            return None
    new_secs = [(n, s) for n, s in live_secs if n not in arch_by_n]
    merged = sorted(arch_secs + new_secs, key=lambda t: t[0])
    archived.write_text(pre + "".join(s for _, s in merged), encoding="utf-8")
    live.unlink()
    return archived


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
            # research/draft/review 的工件叫 260731-1-标题.md（靠尾部连字符区分 -1 与 -10），
            # 快照目录只叫 260731-1，没有尾部连字符，故两种形状都要匹配。
            if entry.name == f"{date_str}-{n}" or entry.name.startswith(prefix):
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
            if not (name == f"{date_str}.md" or name.startswith(f"{date_str}-")):
                continue
            target = archive_dir / stage / name
            if stage == "events" and name == f"{date_str}.md" and target.exists():
                # 补录到已归档日期：合并新 ## N 段而非跳过留孤儿
                merged = _merge_events_md(entry, target)
                if merged:
                    moved.append(merged)
                continue
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
