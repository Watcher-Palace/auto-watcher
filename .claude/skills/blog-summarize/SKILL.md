---
name: blog-summarize
description: On-demand monthly summary for the feminist blog — computes category/tag statistics and writes a neutral-descriptive prose summary page for one month, then publishes it (the landing-page calendar gains a 本月总结 link). Invoke for "/blog-summarize YYMM", "write summary of <month>", "write the May summary", or "monthly summary". NOT part of the regular tracking→research→write→review→publish pipeline.
---

# Blog Summarize Skill

On-demand stage. **Not** part of the regular pipeline and **not** run by `blog-orchestrate`.
For one month it produces a summary **page** that combines deterministic category/tag
statistics with a neutral-descriptive prose synthesis, publishes it to the Hexo site, and the
landing-page calendar shows a `本月总结` link next to that month.

Repo root: `/home/jc/Projects/auto-watcher`

## Stage A — Generate (dispatch a Sonnet subagent)

1. **Determine the month** (`YYMM`, e.g. `2605`). If the user gave one, use it. If omitted,
   **ask which month** — do not guess.

2. **Dispatch ONE subagent with `model: sonnet`.** Its prompt is the entire
   **Generation procedure** section below, with `{YYMM}`, `{YYYY-MM}`, and `{YYYY年M月}`
   replaced for the target month. Sonnet because the prose requires reading and grouping post
   bodies.

3. When the subagent finishes, confirm the draft exists at `_pipeline/summary/{YYMM}.md` and
   show it to the user. **STOP — human gate.** Do not publish until the user reviews and
   confirms. (Same no-auto-chain rule as the rest of the pipeline.)

## Stage B — Publish (main session, only after the user confirms)

Publishing deploys to GitHub Pages — an outward-facing action. Never delegate it to the
subagent and never auto-chain it from Stage A. After the user confirms, run from repo root:

```bash
cp _pipeline/summary/{YYMM}.md source/summaries/{YYMM}.md
pnpm build      # regenerates the calendar; the 本月总结 link now appears for this month
pnpm run deploy
```

`publisher.py` is post-specific (writes to `source/_posts/`, moves assets, validates tags) and
is **not** used here.

---

## Generation procedure (embed this in the Sonnet subagent prompt)

> You are generating the monthly summary for **{YYYY年M月}** (`{YYMM}`). Work from repo root
> `/home/jc/Projects/auto-watcher`. Write the result to `_pipeline/summary/{YYMM}.md`. Write
> all prose in Simplified Chinese.

### Scope

- Read only **published** posts: `source/_posts/*.md`. (Unpublished/abort never reach this
  directory, so reading it enforces "published only".)
- Keep a post only if its frontmatter `date:` falls in `{YYYY-MM}`. The counting unit is the
  **post file**; one date may have several files (e.g. `260117.md` + `260117-2.md`), each a
  separate row.
- Count **all** categories (incl. D, M, N) and **all** tags (incl. status tags `TODO`, `PING`).

### Step 1 — Compute statistics (deterministic; do not tally by hand)

Activate the venv and run this exact stdlib-only snippet (no PyYAML):

```bash
source src/venv/bin/activate
```

```python
import re
from pathlib import Path
from collections import Counter

yymm = "{YYMM}"
target = f"20{yymm[:2]}-{yymm[2:]}"   # e.g. 2026-05

rows = []  # (date_str, title, category, [tags])
for f in sorted(Path("source/_posts").glob("*.md")):
    text = f.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        continue
    fm = m.group(1)
    dm = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", fm, re.MULTILINE)
    if not dm or not dm.group(1).startswith(target):
        continue
    title = (re.search(r"^title:\s*(.+)$", fm, re.MULTILINE) or [None, f.stem])[1].strip()
    cat = (re.search(r"^categories:\s*(.+)$", fm, re.MULTILINE) or [None, "N"])[1].strip()
    if "tags:" in fm:
        tags = [t.strip() for t in re.findall(r"^-\s*(.+)$", fm[fm.index("tags:"):], re.MULTILINE)]
    else:
        tags = []
    rows.append((dm.group(1), title, cat, tags))

total = len(rows)
cat_counts = Counter(r[2] for r in rows)
tag_counts = Counter(t for r in rows for t in r[3])

# category × tag cross-tab: (category, tag) -> post count
from collections import defaultdict
cell = defaultdict(int)
for _, _, c, ts in rows:
    for t in ts:
        cell[(c, t)] += 1

def pct(n):
    return round(100 * n / total) if total else 0

CAT_ORDER = ["S", "A", "B", "C", "D", "M", "N"]
tags_order = [t for t, _ in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))]
cats_present = [c for c in CAT_ORDER if cat_counts.get(c)]

print("TOTAL", total)
print("CATS")
for c in CAT_ORDER:
    if cat_counts.get(c):
        print(c, cat_counts[c], pct(cat_counts[c]))
print("TAGS")
for t, n in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
    print(t, n, pct(n))
print("CROSS")                       # category × tag cross-tab (rows S→N, cols = tags_order)
print("分类 | " + " | ".join(tags_order))
for c in cats_present:
    print(c + " | " + " | ".join(str(cell[(c, t)]) for t in tags_order))
print("ROWS")
for r in sorted(rows, key=lambda r: (CAT_ORDER.index(r[2]) if r[2] in CAT_ORDER else 99, r[0])):
    print(r[0], "|", r[2], "|", r[1], "|", ", ".join(r[3]))
```

Use the printed numbers verbatim. Percentages are integers; the tag-percentage base is **total
posts** (a multi-tag post counts toward each of its tags, so tag % can sum past 100%).

### Step 2 — Read the bodies for prose

Read each kept post's body (`## 概述`, etc.) — a month is small (heaviest on record ~66K
chars), so read them directly. All prose is **neutral-descriptive**: synthesize and group what
the posts report; no stance-taking, no angry/sardonic register, no facts or claims absent from
the month's posts, no named-expert commentary. **Every sentence must trace to a post published
this month.** When in doubt, write fewer well-supported sentences.

### Step 3 — Write the page

Write `_pipeline/summary/{YYMM}.md` in exactly this structure (it IS the page that gets
published, so keep the frontmatter). `date` is the last day of the month. Fill `<…>` from
Steps 1–2; drop any category/tag/section that has no data; omit 待跟进 entirely if no post is
tagged `PING`/`TODO`.

```
---
title: {YYYY年M月} 月度总结
date: {YYYY-MM-末日} 23:59:59
summary_month: "{YYMM}"
layout: page
---

> 范围：本月已发布文章（source/_posts，按 frontmatter 日期归月）。未发布 / abort 不计入。

总计：<总篇数> 篇

## 本月综述
<2–4 句中性概述：篇数、主导分类、本月整体面貌>

## 主题脉络
- **<主题，如 言论管控>**：<该主题下的事件标题，逗号分隔>
- **<主题，如 婚姻与财产>**：<…>

## 结构性观察
<一段：描述本月跨多起事件反复出现的事实层面模式；若无明显重复，直接说明>

## 分类统计
| 分类 | 含义 | 篇数 | 占比 |
|---|---|---|---|
| <分类> | <含义> | <n> | <p>% |

## 标签统计
> 占比 = 含该标签的文章数 ÷ 本月总篇数（一篇多标签会重复计入，合计可超 100%）
| 标签 | 篇数 | 占比 |
|---|---|---|
| <标签> | <n> | <p>% |

## 分类 × 标签交叉表
> 行 = 分类（S→N，仅出现的分类）；列 = 全部标签（按频次降序，与上表一致）；格 = 篇数。来自上面 CROSS 输出，逐格照抄。
| 分类 | <标签1> | <标签2> | … |
|---|---|---|---|
| <分类> | <n> | <n> | … |

## 文章列表
> 按分类 S→N 排序，组内按日期
### <分类>
- <YYYY-MM-DD> 《<标题>》 — <tag> / <tag> / …

## 待跟进
> 本月标记 PING / TODO 的事件
- <YYYY-MM-DD> 《<标题>》 — PING/TODO：<未决事项>
```

含义 column values (canonical, from the `blog-writer` agent, `.claude/agents/blog-writer.md`):
S 政府/国家层面政策或法律 · A 刑事案件；影响极为恶劣的舆论事件 · B 民事案件；影响较大的舆论事件 ·
C 非官方组织；影响较小的舆论事件 · D 个人行为 · M 正向进展（正向或在进程中的行动） · N 中立事件/等待后续

### Zero-post month

If `总篇数` is 0, still write a valid page: `总计：0 篇`, empty tables, and a `## 本月综述`
line noting that no published posts fell in {YYYY-MM} (likely a wrong/early month). Do not
fabricate prose sections.
