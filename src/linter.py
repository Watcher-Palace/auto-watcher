"""Mechanical draft linter — catches format violations before the Sonnet review.

Checks are deterministic only (no judgment calls): em dashes, 舆论 without
concrete metrics, source-line format, unregistered tags, standalone 前情/后续
sections, invalid categories, future dates, missing required sections.
"""
from __future__ import annotations
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.publisher import read_frontmatter, load_tag_registry

VALID_CATEGORIES = {"S", "A", "B", "C", "D", "N"}
METRIC_RE = re.compile(r"(阅读量|讨论量|转发量|评论量|投票|票数)")
SOURCE_LINE_RE = re.compile(r"^(- )?\d{4}\.\d{1,2}\.\d{1,2}，.+?。\*.+?\*。\S+")
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")


def _sections(body: str) -> dict[str, str]:
    """Map '## X' heading → section text (up to next ## heading)."""
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def lint_text(content: str, registry: set[str] | None, today: date) -> list[str]:
    violations: list[str] = []
    fm = read_frontmatter(content)
    body = content.split("---", 2)[-1] if content.startswith("---") else content

    prose = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    if "—" in prose:
        violations.append("破折号 — 出现（风格规则：重组句子，不用破折号）")

    secs = _sections(body)
    for required in ("概述", "信息来源"):
        if required not in secs:
            violations.append(f"缺少必需章节 ## {required}")

    if "舆论" in secs:
        s = secs["舆论"]
        if not (METRIC_RE.search(s) and re.search(r"\d", s)):
            violations.append(
                "## 舆论 无具体数据（阅读量/讨论量/转发量/评论量）——无数据时整节删除"
            )

    if "信息来源" in secs:
        for ln in secs["信息来源"].splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("<!--"):
                continue
            if not SOURCE_LINE_RE.match(ln):
                violations.append(
                    f"信息来源 行格式不符（YYYY.MM.DD，来源。*标题*。URL）：{ln[:50]}"
                )

    cats = fm.get("categories")
    cat_list = cats if isinstance(cats, list) else [cats]
    for c in cat_list:
        if c not in VALID_CATEGORIES:
            violations.append(f"categories 非法值：{c!r}（允许 S/A/B/C/D/N）")

    tags = fm.get("tags") or []
    if not tags and not TAG_PROPOSAL_RE.search(content):
        violations.append(
            "tags 为空且无 TAG-PROPOSAL —— 选 2 个以上贴切标签，或用 "
            "<!-- [TAG-PROPOSAL]: 标签名 — 理由 --> 提案新标签"
        )
    if registry:
        for t in tags:
            if t not in registry:
                violations.append(f"未注册 tag：{t}（见 src/tags.yml）")

    d = fm.get("date")
    if isinstance(d, datetime) or (isinstance(d, str) and re.search(r"\d{2}:\d{2}", d)):
        violations.append("date 含时间成分 —— 只写 YYYY-MM-DD（无 00:00:00）")
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            d = None
            violations.append(f"date 无法解析：{fm.get('date')!r}")
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date) and d > today:
        violations.append(f"date 在未来：{d.isoformat()}")

    return violations


def lint_warnings(content: str) -> list[str]:
    """Reviewer-waivable issues: reported, but never block a draft."""
    body = content.split("---", 2)[-1] if content.startswith("---") else content
    warnings: list[str] = []
    for banned in ("前情", "后续"):
        if banned in _sections(body):
            warnings.append(f"独立 ## {banned} 章节（默认应并入 ## 概述 的 #### 子节；评审可放行）")
    return warnings


def lint_file(path: Path) -> list[str]:
    return lint_text(path.read_text(encoding="utf-8"), load_tag_registry(), date.today())


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python src/linter.py <draft.md>...")
        return 2
    rc = 0
    for p in argv:
        content = Path(p).read_text(encoding="utf-8")
        vs = lint_text(content, load_tag_registry(), date.today())
        ws = lint_warnings(content)
        if vs:
            rc = 1
            print(f"LINT FAIL {p}")
            for v in vs:
                print(f"  - {v}")
        else:
            print(f"LINT OK {p}")
        for w in ws:
            print(f"  ~ WARN: {w}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
