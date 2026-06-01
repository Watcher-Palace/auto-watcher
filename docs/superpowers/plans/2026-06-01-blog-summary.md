# blog-summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-demand monthly-summary stage to the feminist blog — a `blog-summary` skill that computes category/tag stats plus neutral-descriptive prose for one month, publishes it as a Hexo page, and surfaces a `本月总结` link on the landing-page calendar.

**Architecture:** A new standalone skill (not in `blog-orchestrator`). Stage A dispatches a Sonnet subagent that runs a deterministic stdlib Python snippet for stats and reads post bodies for prose, writing a draft Hexo page to `_pipeline/summary/YYMM.md`. After a human gate, Stage B copies it to `source/summaries/YYMM.md` and runs `pnpm build` + `pnpm deploy`. `scripts/calendar.js` is extended to render a `本月总结` link next to a month whose summary page exists.

**Tech Stack:** Python 3 (stdlib only, run via `src/venv`), Hexo 8 generator (`scripts/calendar.js`, JS), Markdown skill doc, pnpm build/deploy.

**Spec:** `docs/superpowers/specs/2026-06-01-blog-summary-design.md`

**Conventions:** Repo is solo — commit directly to `main` (no feature branch). End commit messages with the `Co-Authored-By` trailer. Never commit `.env`.

---

### Task 1: Runtime directories

**Files:**
- Create: `_pipeline/summary/.gitkeep`
- Create: `source/summaries/.gitkeep`

- [ ] **Step 1: Create the two directories with keep-files**

```bash
cd /home/jc/Projects/auto-watcher
mkdir -p _pipeline/summary source/summaries
touch _pipeline/summary/.gitkeep source/summaries/.gitkeep
```

- [ ] **Step 2: Verify they exist and are tracked**

Run: `ls -la _pipeline/summary/.gitkeep source/summaries/.gitkeep`
Expected: both files listed, no error.

- [ ] **Step 3: Commit**

```bash
git add _pipeline/summary/.gitkeep source/summaries/.gitkeep
git commit -m "feat(summary): add _pipeline/summary and source/summaries dirs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Calendar `本月总结` link (`scripts/calendar.js`)

**Files:**
- Modify: `scripts/calendar.js` (summary map, month heading, CSS)

This task uses a throwaway fixture page to drive a red→green check, then removes it. The
fixture month `2602` (Feb 2026) is inside the calendar's render range and does not collide with
the real `2605` acceptance in Task 5.

- [ ] **Step 1: Create a throwaway fixture summary page**

```bash
cd /home/jc/Projects/auto-watcher
mkdir -p source/summaries
cat > source/summaries/2602.md <<'EOF'
---
title: 2026年2月 月度总结
date: 2026-02-28 23:59:59
summary_month: "2602"
layout: page
---

总计：0 篇
EOF
```

- [ ] **Step 2: Build and confirm there is NO link yet (red baseline)**

Run:
```bash
pnpm build >/dev/null 2>&1 && grep -c "本月总结" public/index.html
```
Expected: `0` (calendar.js does not yet emit the link). If `pnpm` errors about missing modules, run `pnpm install` first.

- [ ] **Step 3: Add the summary-page map after the dateMap sort**

In `scripts/calendar.js`, find:

```js
  Object.values(dateMap).forEach(posts =>
    posts.sort((a, b) => CAT_PRIORITY[a.cat] - CAT_PRIORITY[b.cat])
  );
```

Insert immediately after it:

```js

  // Build summary-page map: 'YYMM' -> url, from pages carrying a summary_month marker
  const summaryMap = {};
  locals.pages.each(page => {
    if (!page.summary_month) return;
    summaryMap[String(page.summary_month)] = root + page.path.replace(/\/index\.html$/, '/');
  });
```

- [ ] **Step 4: Compute a per-month heading inside `monthTable`**

In `scripts/calendar.js`, find:

```js
    const firstDow = m.clone().startOf('month').day(); // 0=Sun

    let rows = '';
```

Replace it with:

```js
    const firstDow = m.clone().startOf('month').day(); // 0=Sun

    const yymm = m.format('YYMM');
    const summaryUrl = summaryMap[yymm];
    const heading = summaryUrl
      ? `## ${year}年${month}月 <a class="month-summary" href="${summaryUrl}">本月总结</a>`
      : `## ${year}年${month}月`;

    let rows = '';
```

- [ ] **Step 5: Use the heading in the returned table**

In `scripts/calendar.js`, find:

```js
    return `\n## ${year}年${month}月\n
<table class="calendar-table">
```

Replace the first line of that template literal so it reads:

```js
    return `\n${heading}\n
<table class="calendar-table">
```

- [ ] **Step 6: Add the link style to the `<style>` block**

In `scripts/calendar.js`, find:

```js
  .calendar-table a { text-decoration: none; }
</style>`;
```

Replace with:

```js
  .calendar-table a { text-decoration: none; }
  .month-summary { font-size: 0.6em; font-weight: normal; }
</style>`;
```

- [ ] **Step 7: Build and confirm the link now appears (green)**

Run:
```bash
pnpm build >/dev/null 2>&1 && grep -o '<a class="month-summary"[^>]*>本月总结</a>' public/index.html
```
Expected: one match whose `href` contains `summaries/2602` (e.g. `/auto-watcher/summaries/2602.html`).

- [ ] **Step 8: Confirm a month with no summary page has no link**

Run:
```bash
grep -A1 "2026年4月" public/index.html | grep -c "本月总结"
```
Expected: `0` (April 2026 has no summary page).

- [ ] **Step 9: Remove the fixture and rebuild clean**

```bash
rm source/summaries/2602.md
pnpm build >/dev/null 2>&1 && grep -c "本月总结" public/index.html
```
Expected: `0` (no real summary pages exist yet).

- [ ] **Step 10: Commit (only the calendar change; the fixture is gone)**

```bash
git add scripts/calendar.js
git commit -m "feat(calendar): render 本月总结 link for months with a summary page

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: The `blog-summary` skill

**Files:**
- Create: `.claude/skills/blog-summary/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `.claude/skills/blog-summary/SKILL.md` with exactly this content:

````markdown
---
name: blog-summary
description: On-demand monthly summary for the feminist blog — computes category/tag statistics and writes a neutral-descriptive prose summary page for one month, then publishes it (the landing-page calendar gains a 本月总结 link). Invoke for "/blog-summary YYMM", "write summary of <month>", "write the May summary", or "monthly summary". NOT part of the regular tracking→research→write→review→publish pipeline.
---

# Blog Summary Skill

On-demand stage. **Not** part of the regular pipeline and **not** run by `blog-orchestrator`.
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
   bodies (matches the repo convention: research=Haiku, write/review=Sonnet).

3. When the subagent finishes, confirm the draft exists at `_pipeline/summary/{YYMM}.md` and
   show it to the user. **STOP — human gate.** Do not publish until the user reviews and
   confirms. (Same no-auto-chain rule as the rest of the pipeline.)

## Stage B — Publish (main session, only after the user confirms)

Publishing deploys to GitHub Pages — an outward-facing action. Never delegate it to the
subagent and never auto-chain it from Stage A. After the user confirms, run from repo root:

```bash
cp _pipeline/summary/{YYMM}.md source/summaries/{YYMM}.md
pnpm build      # regenerates the calendar; the 本月总结 link now appears for this month
pnpm deploy
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
- Count **all** categories (incl. D, N) and **all** tags (incl. status tags `TODO`, `PING`).

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

def pct(n):
    return round(100 * n / total) if total else 0

CAT_ORDER = ["S", "A", "B", "C", "D", "N"]
print("TOTAL", total)
print("CATS")
for c in CAT_ORDER:
    if cat_counts.get(c):
        print(c, cat_counts[c], pct(cat_counts[c]))
print("TAGS")
for t, n in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
    print(t, n, pct(n))
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

## 文章列表
> 按分类 S→N 排序，组内按日期
### <分类>
- <YYYY-MM-DD> 《<标题>》 — <tag> / <tag> / …

## 待跟进
> 本月标记 PING / TODO 的事件
- <YYYY-MM-DD> 《<标题>》 — PING/TODO：<未决事项>
```

含义 column values (canonical, from the `blog-write` skill):
S 政府/国家层面政策或法律 · A 刑事案件；影响极为恶劣的舆论事件 · B 民事案件；影响较大的舆论事件 ·
C 非官方组织；影响较小的舆论事件 · D 个人行为 · N 中立事件/等待后续

### Zero-post month

If `总篇数` is 0, still write a valid page: `总计：0 篇`, empty tables, and a `## 本月综述`
line noting that no published posts fell in {YYYY-MM} (likely a wrong/early month). Do not
fabricate prose sections.
````

- [ ] **Step 2: Verify the embedded snippet produces correct stats for 2605**

Save the snippet from Step 1 (the Python block) to a temp file with `yymm = "2605"` and run it:

Run:
```bash
source src/venv/bin/activate
python - <<'PY'
import re
from pathlib import Path
from collections import Counter
yymm = "2605"
target = f"20{yymm[:2]}-{yymm[2:]}"
rows = []
for f in sorted(Path("source/_posts").glob("*.md")):
    text = f.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m: continue
    fm = m.group(1)
    dm = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", fm, re.MULTILINE)
    if not dm or not dm.group(1).startswith(target): continue
    cat = (re.search(r"^categories:\s*(.+)$", fm, re.MULTILINE) or [None,"N"])[1].strip()
    tags = [t.strip() for t in re.findall(r"^-\s*(.+)$", fm[fm.index("tags:"):], re.MULTILINE)] if "tags:" in fm else []
    rows.append((dm.group(1), cat, tags))
total = len(rows)
print("TOTAL", total)
print("CATS", dict(Counter(r[1] for r in rows)))
PY
```
Expected output:
```
TOTAL 32
CATS {'A': 14, 'B': 13, 'C': 2, 'D': 2, 'N': 1}
```
(Independent cross-check: `grep -l '^date: 2026-05' source/_posts/*.md | wc -l` → `32`.)

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/blog-summary/SKILL.md
git commit -m "feat(summary): add blog-summary skill (stats + neutral prose, Sonnet)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Document the stage in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (pipeline tree, Stage Details, Subagent Model Selection, Landing-page Calendar)

- [ ] **Step 1: Add the summary draft to the `_pipeline/` tree**

In `CLAUDE.md`, find:

```
  review/YYMMDD-N-title-vN.md# Stage 4: review notes
  .state                     # last tracked date (plain text: "20260325")
```

Replace with:

```
  review/YYMMDD-N-title-vN.md# Stage 4: review notes
  summary/YYMM.md            # On-demand monthly summary draft (Stage A; not the regular pipeline)
  .state                     # last tracked date (plain text: "20260325")
```

- [ ] **Step 2: Add an on-demand stage subsection after Stage 5**

In `CLAUDE.md`, find the end of the Stage 5 block:

```
The script picks the latest draft for that event, copies it to `source/_posts/YYMMDD.md`, moves assets from `_pipeline/draft/YYMMDD-N-assets/`, then runs `pnpm build` + `pnpm deploy`. The calendar regenerates automatically from post frontmatter (see Landing-page Calendar). Do not execute these steps manually.
```

Insert immediately after it:

```

### On-demand — Monthly Summary (skill: `blog-summary`)

**Not part of the regular pipeline** and never run by `blog-orchestrator` — invoked only on request: `/blog-summary YYMM` or natural language ("write summary of <month>", "write the May summary", "monthly summary"). If no month is given, ask which month — do not guess.

- **Stage A — generate:** dispatch a single **Sonnet** subagent (per the `blog-summary` skill) that computes category/tag statistics over the month's **published** posts and writes a neutral-descriptive prose summary draft to `_pipeline/summary/YYMM.md`. Human gate: review the draft before publishing.
- **Stage B — publish (after confirmation):** copy the draft to `source/summaries/YYMM.md`, then `pnpm build` + `pnpm deploy`. The landing-page calendar then shows a `本月总结` link next to that month (see Landing-page Calendar). `publisher.py` is post-specific and is not used here.
```

- [ ] **Step 3: Add the Sonnet rule to Subagent Model Selection**

In `CLAUDE.md`, find:

```
Use **Sonnet** (`model: sonnet`) for write and review subagents — these require nuanced judgment (e.g. no inference, feminist framing) that Haiku handles unreliably.
```

Insert immediately after it:

```

Use **Sonnet** (`model: sonnet`) for the **`blog-summary`** generation subagent too — it reads and synthesizes the month's post bodies into neutral-descriptive prose, which Haiku handles unreliably.
```

- [ ] **Step 4: Extend the Landing-page Calendar section**

In `CLAUDE.md`, find:

```
To change calendar appearance or color mapping, edit `scripts/calendar.js`.
```

Insert immediately after it:

```

Month headings also show a `本月总结` link when that month has a **published summary page** (see the on-demand Monthly Summary stage). `scripts/calendar.js` builds the link by scanning pages for a `summary_month: "YYMM"` frontmatter marker; no summary page means no link.
```

- [ ] **Step 5: Verify the four insertions are present**

Run:
```bash
grep -c "blog-summary" CLAUDE.md && grep -c "本月总结" CLAUDE.md && grep -c "summary/YYMM.md" CLAUDE.md
```
Expected: first `>=2`, second `>=2`, third `>=1`.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document on-demand blog-summary stage in CLAUDE.md

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end acceptance (generate a real draft; do NOT publish)

**Files:**
- Create (artifact, not committed by this task): `_pipeline/summary/2605.md`

This validates the whole skill against real data. Publishing (Stage B) is the user's call —
stop before it.

- [ ] **Step 1: Generate the May 2026 draft via the skill's Stage A**

Dispatch a `model: sonnet` subagent with the skill's **Generation procedure** filled in for
`{YYMM}=2605`, `{YYYY-MM}=2026-05`, `{YYYY年M月}=2026年5月`. (If executing inline rather than
via a worker, perform that procedure directly.) It must write `_pipeline/summary/2605.md`.

- [ ] **Step 2: Verify the draft exists and has the required structure**

Run:
```bash
test -f _pipeline/summary/2605.md && \
grep -E '^summary_month: "2605"' _pipeline/summary/2605.md && \
grep -c -E '^## (本月综述|主题脉络|结构性观察|分类统计|标签统计|文章列表|待跟进)' _pipeline/summary/2605.md
```
Expected: the file exists, the `summary_month` line matches, and the section count is `7`
(or `6` if 待跟进 was omitted — but May has many `PING` posts, so expect `7`).

- [ ] **Step 3: Verify the stats in the draft match ground truth**

Run:
```bash
grep -E '^总计：32 篇' _pipeline/summary/2605.md && \
grep -E '^\| A \|.*\| 14 \| 44% \|' _pipeline/summary/2605.md && \
grep -E '^\| B \|.*\| 13 \| 41% \|' _pipeline/summary/2605.md
```
Expected: all three match (total 32; A=14/44%; B=13/41%).

- [ ] **Step 4: Manually eyeball the prose**

Read `_pipeline/summary/2605.md` and confirm: 本月综述 is 2–4 neutral sentences; 主题脉络
bullets name real events; 结构性观察 describes only patterns present in the posts; no
stance-taking / angry register; no claims absent from the month's posts; no named-expert
commentary.

- [ ] **Step 5: Stop. Report to the user.**

Do **not** run Stage B (`cp` to `source/summaries/`, `pnpm build`, `pnpm deploy`). Tell the
user the draft is ready at `_pipeline/summary/2605.md` for review and that publishing is their
call. (The draft is a working artifact; leave it uncommitted unless the user wants it kept.)

---

## Notes for the implementer

- **No new committed Python module / no pytest** — by spec, the stats logic lives in the skill
  and is verified by running it against real data (Tasks 3 & 5). Do not add a `src/*.py` file.
- **Order independence:** Tasks 1–4 are independent; Task 5 depends on Tasks 1 and 3 (and on
  Task 2 only if you also want to eyeball the calendar link, which the user will see at publish
  time anyway).
- **Future extension (not in this plan):** a cross-month "previously `PING`, now updated"
  tracker — see the spec's Future extensions section.
