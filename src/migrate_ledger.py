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

    # done-dates.txt 语义：该日期已整体收尾——其中未走完流程的事件是被有意略过的，
    # 账本对应终态为 abort（设计文档要求迁移消费 done-dates；无此文件则空集）。
    done: set[str] = set()
    dd = PIPELINE / "done-dates.txt"
    if dd.exists():
        done = {l.strip() for l in dd.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.strip().startswith("#")}

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
                if d in done:
                    state = "abort"  # done 日期内的非终态事件 = 被有意略过
            rows.append({"维护日期": "", "收录日期": d, "事件编号": str(n),
                         "标题": titles.get(n, ""), "状态": state,
                         "发布日期": pub_date, "发布标题": pub_title,
                         "经验提取": harvest})
    ledger.write_rows(rows)
    print(f"写入 {len(rows)} 行 → {ledger.ledger_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
