# Design: `blog-summary` — on-demand monthly category & tag summary

**Date:** 2026-06-01
**Status:** Approved design, pending spec review

## Purpose

An on-demand stage, **not** part of the regular tracking→research→write→review→publish
pipeline and not wired into `blog-orchestrator`. Invoked only when the user asks for it.
It produces, for one month, a summary **page** with statistics over the blog's **published**
articles: category counts, tag counts, and a grouped article list. The page is published to
the Hexo site and linked from the landing-page calendar (a `本月总结` link next to that
month's heading).

It is intentionally statistical for now. The skill leaves room to layer a qualitative prose
pass (themes / narrative of the month) on top later, which is why generation runs on Sonnet
rather than a bare deterministic script.

## Two stages

```
Stage A — Generate (Sonnet subagent)  → _pipeline/summary/YYMM.md   (draft = a complete Hexo page)
   ── human gate: user reviews the draft ──
Stage B — Publish (main session, confirmed) → source/summaries/YYMM.md → pnpm build + deploy
```

The calendar link appears only after Stage B (the page exists in `source/` and is deployed) —
i.e. only when the summary is "written **and** published", per requirement.

## Stage A — Generate

**Trigger:** the slash form `/blog-summary YYMM` (e.g. `/blog-summary 2605`), or natural
language in a session — "write the May summary", "write summary of 2605", "summarize last
month". All map to this skill.

**Month argument:** `YYMM`. If omitted, default to the **last fully-completed calendar
month** relative to today.

**Model:** on trigger, the main session invokes the `blog-summary` skill (to load its
procedure) and **dispatches a single subagent with `model: sonnet`** to do the generation and
write the draft. Rationale: matches the repo convention (research=Haiku, write/review=Sonnet),
keeps the expensive main-session model out of a routine task, and leaves headroom for a future
prose pass. (Publishing — Stage B — is **not** delegated to the subagent; see below.)

### Scope / data source

- **Strictly published articles.** Read `source/_posts/*.md`. Anything `abort` or
  unpublished never reaches `source/_posts`, so reading that directory automatically enforces
  "published only" — no status-sidecar consultation needed.
- **Month grouping is by frontmatter `date`**, not filename. `2605` = every post whose
  `date:` falls in `2026-05`. (Matches how `scripts/calendar.js` keys posts:
  `post.date.format('YYMMDD')`.)
- **All categories count**, including `D` and `N` — this is a content summary of everything
  published, not the A–C "挑战失败" calendar.
- **All tags count**, including the status tags `TODO` and `PING` (kept as-is per decision).

### Computation (deterministic core)

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
  ever uses inline style, the snippet should fall back to splitting the inline list.)

Reference snippet (to be embedded in the skill — gathers data; the subagent formats it):

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

Percentages: `round(100 * count / total)` (integer percent). For tags the base is **total
posts** (a post with 4 tags counts once toward each of its tags), so the tag percentages can
sum to more than 100% — intentional, and noted in the page header.

Ordering:
- Category table & article-list groups: fixed order `S, A, B, C, D, N` (skip categories with 0 posts).
- Within an article-list group: by `date` ascending.
- Tag table: by count descending, then tag string for stable ties.

### Draft output (a complete Hexo page)

The draft written to `_pipeline/summary/YYMM.md` **is** the page that will be published — so it
carries Hexo page frontmatter and the content uses `##` sections (no duplicate `#` H1; the page
title comes from frontmatter).

```
---
title: 2026年5月 月度总结
date: 2026-05-31 23:59:59
summary_month: "2605"
layout: page
---

> 范围：本月已发布文章（source/_posts，按 frontmatter 日期归月）。未发布 / abort 不计入。

总计：18 篇

## 分类统计
| 分类 | 含义 | 篇数 | 占比 |
|---|---|---|---|
| A | 刑事案件；影响极为恶劣的舆论事件 | 9 | 50% |
| B | 民事案件；影响较大的舆论事件 | 7 | 39% |
| C | 非官方组织；影响较小的舆论事件 | 2 | 11% |

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

Frontmatter notes:
- `summary_month: "2605"` (quoted string, preserves leading-zero months) is the marker
  `scripts/calendar.js` matches on.
- **No `categories:` / `tags:`** on the page — keeps the summary out of the blog's
  category/tag indexes and out of the calendar's post scan (which iterates `locals.posts`,
  not pages, so a page can't affect it regardless).
- `date` set to the last day of the month (display only; pages are not subject to Hexo's
  future-post hiding).

Category-meaning labels (含义 column) come from the canonical list in the `blog-write` skill:

| 分类 | 含义 |
|---|---|
| S | 政府 / 国家层面政策或法律 |
| A | 刑事案件；影响极为恶劣的舆论事件 |
| B | 民事案件；影响较大的舆论事件 |
| C | 非官方组织；影响较小的舆论事件 |
| D | 个人行为 |
| N | 中立事件 / 等待后续 |

After the subagent returns, the main session reports the draft path. **Human gate:** the user
reviews `_pipeline/summary/YYMM.md` before publishing.

## Stage B — Publish (confirmed, main session)

Publishing is an outward-facing action (deploys to GitHub Pages), so it is done by the **main
session after explicit user confirmation**, never by the subagent and never auto-chained from
Stage A. Because the draft is already a complete page, publishing is a copy + build + deploy:

```bash
cp _pipeline/summary/YYMM.md source/summaries/YYMM.md
pnpm build      # regenerates the calendar — the 本月总结 link now appears for this month
pnpm deploy
```

No new publisher script and `publisher.py` is **not** reused (it is post-specific: writes to
`source/_posts/`, moves assets, validates tags against `tags.yml`). The summary page has none
of that. These three commands are documented in the skill and run from repo root after
confirmation. (If this proves repetitive later, it can be extracted into a script — out of
scope now.)

## Calendar integration (`scripts/calendar.js`)

The generator already receives `locals` (with `.pages`) and renders one `## YYYY年M月`
heading per month. Changes:

1. Build a summary map from pages, keyed by the `summary_month` marker:

   ```js
   // 'YYMM' -> url
   const summaryMap = {};
   locals.pages.each(page => {
     if (!page.summary_month) return;
     summaryMap[String(page.summary_month)] = root + page.path.replace(/\/index\.html$/, '/');
   });
   ```

   Using `page.path` (with the same `index.html` strip the post code uses) keeps the link
   correct regardless of pretty-url config. (Confirmed: Hexo 8 passes `locals.pages` to
   generators; `root` is `/auto-watcher/`. A flat file `source/summaries/2605.md` renders to
   `/auto-watcher/summaries/2605.html` — not a trailing-slash dir — which is fine since the
   link is built from `page.path`. Use `source/summaries/2605/index.md` instead only if a
   pretty `/summaries/2605/` URL is wanted.)

2. In `monthTable(m)`, render the heading with a link when that month has a summary:

   ```js
   const yymm = m.format('YYMM');                 // e.g. "2605"
   const summaryUrl = summaryMap[yymm];
   const heading = summaryUrl
     ? `## ${year}年${month}月 <a class="month-summary" href="${summaryUrl}">本月总结</a>`
     : `## ${year}年${month}月`;
   ```

   and use `heading` in place of the current `## ${year}年${month}月` line.

3. Add a small style to the existing `<style>` block so the link reads as a secondary label:

   ```css
   .month-summary { font-size: 0.6em; font-weight: normal; }
   ```

Months without a published summary page render exactly as today (no link).

## Files to create / modify

1. **New:** `.claude/skills/blog-summary/SKILL.md` — the skill. Frontmatter `description` must
   include the trigger phrasing so the skill is discoverable from natural-language requests
   ("write summary of …", "monthly summary"). Body contains: scope, parsing rules + reference
   snippet, ordering rules, the draft page template (incl. frontmatter), the rule that
   **generation** is dispatched to a `model: sonnet` subagent, and the **publish** procedure
   (human gate → `cp` to `source/summaries/YYMM.md` → `pnpm build` → `pnpm deploy`, run in the
   main session after confirmation).
2. **Modify:** `scripts/calendar.js` — `summaryMap` from `locals.pages`, conditional heading
   link, and the `.month-summary` CSS rule.
3. **New (runtime dirs):** `_pipeline/summary/` and `source/summaries/`, each with a `.gitkeep`
   so the directories exist in the repo.
4. **Modify:** `CLAUDE.md` —
   - Add an "On-demand: monthly summary" note (separate from the regular pipeline; triggered by
     `/blog-summary` or natural language; Stage A generate + Stage B publish).
   - Add the Sonnet rule to "Subagent Model Selection".
   - Extend the "Landing-page Calendar" section: month headings can carry a `本月总结` link,
     sourced at build time from summary pages' `summary_month` frontmatter.

`blog-orchestrator` is intentionally **not** modified — this stage is standalone and must not
be auto-chained into the pipeline.

## Edge cases

- **Zero posts in the month:** still write a valid page with `总计：0 篇` and empty tables, and
  tell the user no published posts fell in that month (likely a wrong/early month argument).
  Publishing such a page is the user's call.
- **Re-running an already-summarized month:** regenerate the draft (overwrite) and, on
  re-publish, overwrite `source/summaries/YYMM.md` and redeploy. Idempotent.
- **Generated but not published:** no calendar link — the link is tied to the page existing in
  `source/` and being deployed, which is exactly "written and published".
- **Multiple posts on one day** (e.g. `260117.md` + `260117-2.md`): each is a separate row;
  both appear in their category group. No de-duplication.
- **Post with no `tags:`** : contributes to category counts and the article list (tags shown
  empty) but not to any tag count.
- **Category missing/blank:** default to `N`.

## Testing / verification

No hermetic unit tests are added (no new committed Python module — logic lives in the skill).
Verification is by running against a real month and eyeballing:
- Stage A for `2605`: confirm category counts match `grep -c` spot-checks, the article list is
  complete and correctly grouped S→N, tag percentages use the total-posts base.
- No-argument run: confirm it defaults to the last completed month.
- Zero-post month: confirm the zero-post page + message.
- Stage B: after `pnpm build` (or `pnpm server`), confirm the `本月总结` link appears next to
  that month's heading, resolves to the summary page, and that months without a summary show
  no link.

## Out of scope (YAGNI for now)

- Qualitative prose / thematic narrative (deferred; the Sonnet-subagent choice keeps the door
  open).
- Month-over-month comparison / trends.
- A dedicated publish script (three Bash commands suffice for now).
- Category×tag cross-tabulation.

Note: the summary is published as a Hexo **page** (not a post), so it does not appear in post
feeds, archives, or the calendar's post scan.
