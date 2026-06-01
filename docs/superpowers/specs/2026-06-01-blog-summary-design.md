# Design: `blog-summary` — on-demand monthly category & tag summary

**Date:** 2026-06-01
**Status:** Approved design, pending spec review

## Purpose

An on-demand stage, **not** part of the regular tracking→research→write→review→publish
pipeline and not wired into `blog-orchestrator`. Invoked only when the user asks for it.
It produces a per-month summary file with statistics over the blog's **published**
articles: category counts, tag counts, and a grouped article list.

It is intentionally statistical for now. The skill leaves room to layer a qualitative
prose pass (themes / narrative of the month) on top later, which is why it runs on Sonnet
rather than a bare deterministic script.

## Invocation & model

- **Trigger:** either the slash form `/blog-summary YYMM` (e.g. `/blog-summary 2605`),
  or natural language in a session — "write the May summary", "write summary of 2605",
  "summarize last month". All map to this skill.
- **Month argument:** `YYMM` (e.g. `2605` = May 2026). If no month is given, default to the
  **last fully-completed calendar month** relative to today.
- **Model:** on trigger, the main session invokes the `blog-summary` skill (to load its
  procedure) and then **dispatches a single subagent with `model: sonnet`** to execute it
  and write the output file. Rationale: matches the repo convention (research=Haiku,
  write/review=Sonnet), keeps the expensive main-session model out of a routine task, and
  leaves headroom for a future Sonnet-quality prose pass.

## Scope / data source

- **Strictly published articles.** Read `source/_posts/*.md`. Anything `abort` or
  unpublished never reaches `source/_posts`, so reading that directory automatically
  enforces "published only" — no status-sidecar consultation needed.
- **Month grouping is by frontmatter `date`**, not filename. `2605` = every post whose
  `date:` falls in `2026-05`. (This matches how `scripts/calendar.js` keys posts:
  `post.date.format('YYMMDD')`.)
- **All categories count**, including `D` and `N`. This is a content summary of everything
  published, not the A–C "挑战失败" calendar.
- **All tags count**, including the status tags `TODO` and `PING` (kept as-is per decision).

## Computation (deterministic core)

The skill instructs the subagent to run a self-contained stdlib-only Python snippet over the
post frontmatter and aggregate with `collections.Counter`, rather than tallying by eye
(error-prone across dozens of posts). No new committed `.py` module — the snippet lives in
the skill and is run via the existing venv (`source src/venv/bin/activate`).

Parsing rules (regex, stdlib only — no PyYAML dependency):
- Frontmatter = text between the first two `---` lines.
- `date:` → first `YYYY-MM-DD`; keep the post only if it starts with the target `YYYY-MM`.
- `title:` → remainder of the line.
- `categories:` → the scalar on that line (single letter S/A/B/C/D/N). Default `N` if absent.
- `tags:` → block-list items: lines matching `^-\s*(.+)$` following the `tags:` line.
  (All posts in this repo use block-style tags; inline `[a, b]` is not expected. If a post
  ever uses inline style, the snippet should still handle it — documented as an edge case.)

Reference snippet (to be embedded in the skill):

```python
import re, sys
from datetime import date
from pathlib import Path
from collections import Counter

def default_yymm():
    t = date.today()
    y, m = (t.year - 1, 12) if t.month == 1 else (t.year, t.month - 1)
    return f"{y % 100:02d}{m:02d}"

yymm = sys.argv[1] if len(sys.argv) > 1 else default_yymm()
target = f"20{yymm[:2]}-{yymm[2:]}"   # "2026-05"

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
```

Percentages: `round(100 * count / total)` (integer percent). For tags the base is
**total posts** (a post with 4 tags counts once toward each of its tags), so the tag
percentages can sum to more than 100% — this is intentional and noted in the output header.

Ordering:
- Category table & article-list groups: fixed order `S, A, B, C, D, N` (skip categories with 0 posts).
- Within an article-list group: by `date` ascending.
- Tag table: by count descending, then tag string for stable ties.

## Output

Path: `_pipeline/summary/YYMM.md` (new pipeline-artifact subdir; create if missing).

Template:

```
# 2026年5月 月度小结
> 范围：本月已发布文章（source/_posts，按 frontmatter 日期归月）。未发布 / abort 不计入。

总计：18 篇

## 分类统计
| 分类 | 含义 | 篇数 | 占比 |
|---|---|---|---|
| A | 刑事案件 / 影响极恶劣舆论 | 9 | 50% |
| B | 民事案件 / 影响较大舆论 | 7 | 39% |
| C | 非官方组织 / 影响较小舆论 | 2 | 11% |

## 标签统计
> 占比 = 含该标签的文章数 ÷ 本月总篇数（一篇多标签会重复计入，合计可超 100%）
| 标签 | 篇数 | 占比 |
|---|---|---|
| 法律 | 6 | 33% |
| 婚姻 | 4 | 22% |
| … | | |

## 文章列表
> 按分类 S→N 排序，组内按日期

### A
- 2026-05-03 《女医学生遭前男友杀害案一审判决死刑》 — 法律 / 犯罪 / 故意杀人
- …

### B
- …
```

Category-meaning labels (for the 含义 column) come from the canonical list in the
`blog-write` skill:

| 分类 | 含义 |
|---|---|
| S | 政府 / 国家层面政策或法律 |
| A | 刑事案件；影响极为恶劣的舆论事件 |
| B | 民事案件；影响较大的舆论事件 |
| C | 非官方组织；影响较小的舆论事件 |
| D | 个人行为 |
| N | 中立事件 / 等待后续 |

## Files to create / modify

1. **New:** `.claude/skills/blog-summary/SKILL.md` — the skill. Frontmatter `description`
   must include the trigger phrasing so the skill is discoverable from natural-language
   requests ("write summary of …", "monthly summary"). Body contains: scope, the parsing
   rules + reference snippet, ordering rules, the output template, and the instruction that
   it is dispatched to a `model: sonnet` subagent.
2. **New (runtime):** `_pipeline/summary/` directory (created on first run; add a `.gitkeep`
   so the dir exists in the repo).
3. **Modify:** `CLAUDE.md` — add a short "On-demand: monthly summary" note to the Pipeline
   Overview / Stage Details documenting that this stage exists, is separate from the regular
   pipeline, is triggered by `/blog-summary` or natural language, and runs on a Sonnet
   subagent. Add the Sonnet rule to the "Subagent Model Selection" section.

`blog-orchestrator` is intentionally **not** modified — this stage is standalone and must not
be auto-chained into the pipeline.

## Edge cases

- **Zero posts in the month:** write the file with `总计：0 篇` and empty tables, and tell the
  user no published posts fell in that month (likely a wrong/early month argument).
- **Multiple posts on one day** (e.g. `260117.md` + `260117-2.md`): each is a separate row;
  both appear in their category group. No de-duplication.
- **Post with no `tags:`** : contributes to category counts and the article list (tags shown
  as empty) but not to any tag count.
- **Inline tag style** `tags: [a, b]`: not present in the repo today; the snippet handles
  block style. If encountered, the snippet should fall back to splitting the inline list.
- **Category missing/blank:** default to `N`.

## Testing / verification

Hermetic unit tests are not added (no new committed Python module — logic lives in the
skill). Verification is by running the skill against a real month and eyeballing:
- Run for `2605`; confirm category counts match `grep -c` spot-checks and the article list
  is complete and correctly grouped.
- Run with no argument; confirm it defaults to the last completed month.
- Run for a month with no posts; confirm the zero-post message.

## Out of scope (YAGNI for now)

- Qualitative prose / thematic narrative (deferred; the Sonnet-subagent choice keeps the door
  open).
- Month-over-month comparison / trends.
- Publishing the summary as a blog post (it is an internal `_pipeline` artifact).
- Category×tag cross-tabulation.
