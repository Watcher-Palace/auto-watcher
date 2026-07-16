# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A feminist news blog (Hexo, deployed to GitHub Pages) with a semi-automated pipeline: track Weibo events → research → write → review → publish. Research, writing, and review stages are done by Claude Code subagents; the research and review agents use WebSearch/WebFetch, while the writer agent has no web access. None of this runs through external LLM APIs (Chinese models censor feminist content; use Claude Code directly).

## Blog Commands

```bash
pnpm run server    # local preview at http://localhost:4000
pnpm run build     # hexo generate — regenerates public/
pnpm run deploy    # hexo deploy — pushes the EXISTING public/ to gh-pages; does NOT build
```

**Always `pnpm run build` before `pnpm run deploy`** for a manual deploy — `deploy` only pushes whatever is already in `public/`, so skipping the build silently ships stale content. (`publisher.py` already chains build → deploy, so this only bites manual deploys.)

Deploy target (from `_config.yml`): `git@git_personal:Watcher-Palace/auto-watcher.git`, branch `gh-pages` (`git_personal` is an SSH alias).

## Pipeline Overview

```
_pipeline/
  events.csv                 # 状态唯一权威（账本）：一行一事件；只经 pipeline_cli/代码写
  events/YYMMDD.md           # 事件内容（brief/来源），人和 agent 读；状态代码不解析
  research/YYMMDD-N-title.md # Stage 2 输出
  draft/YYMMDD-N-title-vN.md # Stage 3 输出（+ YYMMDD-N-assets/）
  review/YYMMDD-N-title-vN.md# Stage 4 输出
  summary/YYMM.md            # 月度总结草稿（on-demand）
  .tracker-state.json        # tracker 增量游标（内部）
```

**Pipeline check:** `python src/pipeline_cli.py status` — 对账后列出在途事件与待提取经验。
不要裸读/裸改 events.csv（对账内建于 CLI 读路径）。状态流：candidate → selected →
research → draft-vN → review-vN → published/abort（终态；`无事件` 行标记查过但无事件的日期）。
事件一到终态即按事件归档到 `_pipeline_archive/`；日期全终态后其 events md 一并归档。

Published posts go to `source/_posts/YYMMDD.md`（同日第二篇起为 YYMMDD-N.md） with assets in `source/_posts/YYMMDD/`.

## Post Format

The canonical **format** spec — frontmatter, section structure, per-section content
rules, inline `<font>` conventions, asset embedding — lives in
`source/_drafts/template.md` (never rendered: `render_drafts: false`).
Judgment rules — categories boundaries, tag selection and TAG-PROPOSAL protocol,
style/no-inference rules — live in the `blog-writer` agent (`.claude/agents/blog-writer.md`). Edit those two files; do
not duplicate the spec here or it will drift.

## Landing-page Calendar

The monthly calendar on the homepage (`/index.html`) is generated at **build time** by the Hexo generator `scripts/calendar.js` from post frontmatter — there is no `source/index.md` and the publisher does not touch the calendar. Publishing a post is enough; the calendar regenerates on the next `pnpm build`/`deploy`.

How cells render (see `scripts/calendar.js`):
- Only categories S/A/B/C appear (D/N are excluded). Color: S = darkred bold, A = red, B = orange, C = yellow.
- An event day shows the phrase `挑战失败` split across that day's events — one `<a>` link per event, each colored by its category. Segments are joined by a neutral grey `_` so multiple same-category events on one day stay distinguishable.
- A day with no event since the last A–C event shows a green `Day N` counter.

To change calendar appearance or color mapping, edit `scripts/calendar.js`.

Month headings also show a `本月总结` link when that month has a **published summary page** (see the on-demand Monthly Summary stage). `scripts/calendar.js` builds the link by scanning pages for a `summary_month: "YYMM"` frontmatter marker; no summary page means no link.

## Tests

```bash
source src/venv/bin/activate
python -m pytest src/tests/ -q
```
Tests are hermetic (network and the `claude` CLI are mocked). The same command runs in CI on every push/PR via `.github/workflows/tests.yml`; deps are pinned in `requirements.txt`.

## Stage Details

### Stage 1 — Track (`src/tracker.py`)
Run (venv lives at `src/venv/`, not `.venv/`; date arg is positional YYMMDD, there is no `--date` flag):
```bash
source src/venv/bin/activate
python src/tracker.py [YYMMDD]            # single date (default: yesterday)
python src/tracker.py --days N [--end YYMMDD] [--merge]  # date range
python src/tracker.py --daily [--budget N]  # incremental since last seen post (cron-safe; auto-resumes budget/rate-limit cursors)
python src/tracker.py --urls <url1,url2|@file> [YYMMDD]  # anonymous fetch of public post URLs (no cookie/account; immune to the rate limit)
```
Output: `_pipeline/events/YYMMDD.md` with numbered entries (`## N. 标题`).

Implementation details (for debugging, not for manual reimplementation):
- Weibo API: `https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}`
- Cookie must be from `weibo.cn` domain (fields: `_T_WM`, `ALF`, `SSOloginstate`, `SUB`, `SUBP`)
- Use desktop Chrome UA + `Referer: https://m.weibo.cn/` — mobile UA triggers bot detection
- Extract both `mblog.text` AND `mblog.retweeted_status.text` — feminist content is often in retweets
- Tracked account UID: set via `TRACKED_UIDS` env var in `src/.env` (not committed)
- Incremental state (per-UID last-seen post ID + resume cursors) lives in `_pipeline/.tracker-state.json`
- LLM filtering runs via the `claude` CLI subprocess (`--model claude-haiku-4-5-20251001`), using the local Claude Code subscription — no OpenRouter or external API key

### Stage 2 — Research (agent: `blog-researcher`)
Dispatched by the `blog-orchestrate` skill (Sonnet; tools/model pinned in `.claude/agents/blog-researcher.md`). Owns the fact base end-to-end: `mode: initial` establishes `_pipeline/research/YYMMDD-N-title.md` (sections `## 事实`, `## 当事方`, `## 信息来源`, tracked to today, blue-font latest development with explicit date); `mode: update` verifies review-disputed facts and edits the file in place with `补充/更正/查证失败（评审vN-问题K）` marks — never destructively.

### Stage 3 — Write (agent: `blog-writer`)
Dispatched by `blog-orchestrate` (Sonnet, **no web tools** — the research file is the sole fact source; a fact not in it does not go in the draft). Output to `_pipeline/draft/YYMMDD-N-title-vN.md`. If the fact base has gaps, the writer reports them instead of drafting. Format spec: `source/_drafts/template.md`; judgment rules live in `.claude/agents/blog-writer.md`.

### Stage 4 — Review (agent: `blog-reviewer`)
Dispatched by `blog-orchestrate` (Sonnet, independent web verification). Writes `_pipeline/review/YYMMDD-N-title-vN.md` in a strict format (line 1 `STATUS: CLEAN|ISSUES`; numbered `## 问题 K` items typed 事实/格式 with verbatim `原文` anchors and `处理：` lines), validated by `src/review_linter.py`. If any 事实 item exists, the revision cycle inserts an update-mode research pass before the writer revision. User annotates disagreements as `<!-- [USER]: ... -->` before revision.

### Stage 5 — Publish (`src/publisher.py`)
Run:
```bash
python src/publisher.py <YYMMDD> <N>
```
The script picks the latest draft for that event, copies it to `source/_posts/YYMMDD.md`, moves assets from `_pipeline/draft/YYMMDD-N-assets/`, then runs `pnpm build` + `pnpm run deploy`. Pre-flight refuses to publish if the latest review has undispositioned or `未解决` items, or if the draft still contains `[USER]`/`[REVIEWER]`/`[WRITER-*]` comments. The calendar regenerates automatically from post frontmatter (see Landing-page Calendar). Do not execute these steps manually.

Each successful publish marks the event 待提取 in events.csv; run the `blog-curate` skill periodically to distill queued corrections into the agents' 累积经验 sections (general principles only — see the skill's exception gate).

### On-demand — Monthly Summary (skill: `blog-summarize`)

**Not part of the regular pipeline** and never run by `blog-orchestrate` — invoked only on request: `/blog-summarize YYMM` or natural language ("write summary of <month>", "write the May summary", "monthly summary"). If no month is given, ask which month — do not guess.

- **Stage A — generate:** dispatch a single **Sonnet** subagent (per the `blog-summarize` skill) that computes category/tag statistics over the month's **published** posts and writes a neutral-descriptive prose summary draft to `_pipeline/summary/YYMM.md`. Human gate: review the draft before publishing.
- **Stage B — publish (after confirmation):** copy the draft to `source/summaries/YYMM.md`, then `pnpm build` + `pnpm run deploy`. The landing-page calendar then shows a `本月总结` link next to that month (see Landing-page Calendar). `publisher.py` is post-specific and is not used here.

## Environment Variables

The file lives at `src/.env` (gitignored) — not the repo root.

```
WEIBO_COOKIE=_T_WM=...; ALF=...; SSOloginstate=...; SUB=...; SUBP=...
TRACKED_UIDS=uid1,uid2,uid3     # Weibo UIDs the tracker fetches
```

Tracker LLM filtering uses the `claude` CLI subprocess (Haiku) on the local Claude Code subscription. There is no OpenRouter/external API key dependency.

## Known Pitfalls

| Problem | Fix |
|---------|-----|
| Weibo fetch fails silently | Cookie must be from `weibo.cn`, not `weibo.com` |
| Weibo fetch blocked | Use desktop Chrome UA, not mobile |
| Weibo cookie expired (all UIDs fail, no captcha challenge) | Get fresh cookie from browser — do NOT switch to WebSearch for discovery |
| Tracker exits with `RATE LIMITED` | Account-level throttle — a fresh cookie for the same account does NOT reset it. Persists 6–24h. Wait (`--daily` auto-resumes its cursor), or add events immediately via `--urls` (anonymous, unaffected). (Distinct from cookie expiry.) |
| Tracker LLM filtering fails | Check the `claude` CLI is on PATH and the Claude Code subscription is active — not OpenRouter or any API key. |

## Subagent Model Selection

Research files must be written entirely in **Simplified Chinese**. Do not write English prose — Chinese names/terms may appear but all explanatory text must be in Chinese.

All pipeline subagents — research, write, review, summary — run on **Sonnet**; models and tool allowlists for research/write/review are pinned in `.claude/agents/` (the writer deliberately has no web tools). Research needs coverage judgment (the writer no longer backstops it), which Haiku handles unreliably. **Haiku** survives only in the tracker's LLM filtering (a `claude` CLI subprocess, not a subagent).

When dispatching parallel subagents (research, write, or review), run in **batches of 2–3**, not all at once, so a quota hit loses only one batch rather than all work.

## Tracker Blocker Protocol

When the Stage 1 tracker fails, surface the specific error immediately and wait for the user to resolve it. Do not attempt to replace the tracker with WebSearch or other discovery methods — the Weibo UIDs in `src/.env` are the authoritative event sources.

## Keeping Docs Accurate (anti-drift)

When a learned correction contradicts this file, a `SKILL.md`, or an agent file (`.claude/agents/*.md`), fix that file directly — do not park the correction in a memory file as a permanent shadow copy. Auto-memory is for facts *not yet* in the canonical docs; once a fact lands here, in a skill, or in an agent file, the memory should be deleted. This is the rule that keeps CLAUDE.md, the skills, and the agents from drifting out of sync with reality (e.g. venv path, tracker LLM backend, script flags).
