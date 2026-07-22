"""管线状态 CLI —— 状态查看与转换的唯一入口（不要裸读/裸改 events.csv）。

用法：
  python src/pipeline_cli.py status
  python src/pipeline_cli.py select <收录日期> <N...>
  python src/pipeline_cli.py abort  <收录日期> <N...>
  python src/pipeline_cli.py staged <收录日期> <N...>   # 终态：值得关注但暂无可靠来源/相关性未定；草稿移入 source/_drafts 存查
  python src/pipeline_cli.py add    <收录日期> <N> <标题>
  python src/pipeline_cli.py archive [<收录日期> [N]]
  python src/pipeline_cli.py harvest [done <收录日期> <N>]
  python src/pipeline_cli.py ping-due
  python src/pipeline_cli.py dedup <关键词...>
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils import ledger
from src.utils.archive import finalize_event, stage_event, sweep


def research_age_suffix(date_str: str, n) -> str:
    """在途事件研究文件年龄提示；≥2 天提醒 orchestrator 建议刷新。"""
    from src.utils.pipeline import research_age_days
    age = research_age_days(date_str, int(n))
    return f"（research 已 {age} 天）" if age is not None and age >= 2 else ""


def cmd_status() -> int:
    rows = ledger.reconcile()
    maint = [r["维护日期"] for r in rows if r["维护日期"]]
    print(f"最后维护: {max(maint) if maint else '（无记录）'}")
    untracked = ledger.get_untracked_dates()
    print("未追踪(近15天): " + (", ".join(untracked) if untracked else "无"))
    open_rows = [r for r in rows
                 if r["事件编号"] and r["状态"] not in ledger.TERMINAL_STATES]
    if open_rows:
        print("\n在途事件:")
        print(f"{'收录日期':<8} {'事件':<4} {'状态':<12} 标题")
        for r in open_rows:
            suffix = research_age_suffix(r["收录日期"], r["事件编号"])
            print(f"{r['收录日期']:<8} {r['事件编号']:<4} {r['状态']:<12} {r['标题']}{suffix}")
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
    if cmd == "staged":
        date_str, ns = args[0], args[1:]
        for n in ns:
            ledger.record_staged(date_str, int(n))
            parked, done = stage_event(date_str, int(n))
            note = (f"草稿已存查 source/_drafts/{parked.name}" if parked
                    else "无草稿")
            print(f"{date_str}-{n}: staged（{note}；其余工件已归档）"
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
                if st in ledger.EVENT_TERMINAL_STATES:
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
    if cmd == "ping-due":
        from datetime import date, timedelta
        from src.publisher import read_frontmatter
        from src.utils import pipeline as pl
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        for p in sorted(pl.POSTS.glob("*.md")):
            fm = read_frontmatter(p.read_text(encoding="utf-8"))
            if "PING" in (fm.get("tags") or []) and str(fm.get("date"))[:10] <= cutoff:
                print(f"{p.stem}  {str(fm.get('date'))[:10]}  {fm.get('title', '')}")
        return 0
    if cmd == "dedup":
        from src.utils import pipeline as pl
        kws = args
        if not kws:
            print("usage: dedup <关键词>...")
            return 1
        for r in ledger.read_rows():
            if r["标题"] and any(k in r["标题"] for k in kws):
                print(f"账本 {r['收录日期']}-{r['事件编号']} [{r['状态']}] {r['标题']}")
        for base in (pl.POSTS, pl.PIPELINE / "research", pl.ARCHIVE / "research"):
            if not base.exists():
                continue
            for p in sorted(base.glob("*.md")):
                text = p.read_text(encoding="utf-8")
                if any(k in p.name or k in text for k in kws):
                    print(f"{base.parent.name}/{base.name}/{p.name}")
        return 0
    print(f"未知子命令: {cmd}\n{__doc__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
