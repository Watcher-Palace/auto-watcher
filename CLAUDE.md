# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A feminist news blog (Hexo, deployed to GitHub Pages) with a semi-automated pipeline: track Weibo events → research → write → review → publish. Research, writing, and review stages are done by Claude Code directly using WebSearch/WebFetch — not LLM APIs (Chinese models censor feminist content; use Claude Code directly).

## Blog Commands

```bash
pnpm run server    # local preview at http://localhost:4000
pnpm run build
pnpm run deploy    # build + push to GitHub Pages
```

Deploy target (from `_config.yml`): `git@git_personal:Watcher-Palace/auto-watcher.git`, branch `gh-pages` (`git_personal` is an SSH alias).

## Pipeline Overview

```
_pipeline/
  events/YYMMDD.md           # Stage 1: tracked Weibo events (one per date)
  events/YYMMDD-status.txt   # per-event status, "N:selected" / "N:abort" / "N:published" (one per line). researched/drafted/reviewed/candidate are derived from file presence.
  research/YYMMDD-N-title.md # Stage 2: research output
  draft/YYMMDD-N-title-vN.md # Stage 3: draft post
  draft/YYMMDD-N-assets/     # images for this draft
  review/YYMMDD-N-title-vN.md# Stage 4: review notes
  .state                     # last tracked date (plain text: "20260325")
  done-dates.txt             # dates where all events are terminal (published/abort); append when a date is fully done
```

**Pipeline check:** Only scan dates NOT listed in `done-dates.txt`. When checking status, look at `events/YYMMDD.md` (for today's events if no status file yet) and `events/YYMMDD-status.txt` plus presence of research/draft/review files for in-flight dates.

Published posts go to `source/_posts/YYMMDD.md` with assets in `source/_posts/YYMMDD/`.

## Post Format

The authoritative post spec — frontmatter, section structure, inline `<font>` color conventions, asset embedding, categories, and tags — lives in the `blog-write` skill (`.claude/skills/blog-write/SKILL.md`). Edit it there; do not duplicate the spec in this file or it will drift.

## Landing-page Calendar

The monthly calendar on the homepage (`/index.html`) is generated at **build time** by the Hexo generator `scripts/calendar.js` from post frontmatter — there is no `source/index.md` and the publisher does not touch the calendar. Publishing a post is enough; the calendar regenerates on the next `pnpm build`/`deploy`.

How cells render (see `scripts/calendar.js`):
- Only categories S/A/B/C appear (D/N are excluded). Color: S = darkred bold, A = red, B = orange, C = yellow.
- An event day shows the phrase `挑战失败` split across that day's events — one `<a>` link per event, each colored by its category. Segments are joined by a neutral grey `_` so multiple same-category events on one day stay distinguishable.
- A day with no event since the last A–C event shows a green `Day N` counter.

To change calendar appearance or color mapping, edit `scripts/calendar.js`.

## Stage Details

### Stage 1 — Track (`src/tracker.py`)
Run (venv lives at `src/venv/`, not `.venv/`; date arg is positional YYMMDD, there is no `--date` flag):
```bash
source src/venv/bin/activate
python src/tracker.py [YYMMDD]            # single date (default: yesterday)
python src/tracker.py --days N [--end YYMMDD] [--merge]  # date range
```
Output: `_pipeline/events/YYMMDD.md` with numbered entries (`## N. 标题`).

Implementation details (for debugging, not for manual reimplementation):
- Weibo API: `https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}`
- Cookie must be from `weibo.cn` domain (fields: `_T_WM`, `ALF`, `SSOloginstate`, `SUB`, `SUBP`)
- Use desktop Chrome UA + `Referer: https://m.weibo.cn/` — mobile UA triggers bot detection
- Extract both `mblog.text` AND `mblog.retweeted_status.text` — feminist content is often in retweets
- Tracked account UID: `1114030772` (override via `TRACKED_UIDS`)
- LLM filtering runs via the `claude` CLI subprocess (`--model claude-haiku-4-5-20251001`), using the local Claude Code subscription — no OpenRouter or external API key

### Stage 2 — Research (skill: `blog-research`)
Invoke the `blog-research` skill before dispatching any research subagent. Output to `_pipeline/research/YYMMDD-N-title.md` with sections: `## Facts`, `## Parties`, `## Sources`.

### Stage 3 — Write (skill: `blog-write`)
Invoke the `blog-write` skill before dispatching any write subagent. Output to `_pipeline/draft/YYMMDD-N-title-vN.md`. The skill specifies required constraints — section names, URL format in 信息来源, per-section content — that must be embedded in every write-agent prompt.

### Stage 4 — Review (skill: `blog-review`)
Invoke the `blog-review` skill before dispatching any review subagent. Reviewer annotates suggestions as `<!-- [REVIEWER]: ... -->`. User annotates disagreements as `<!-- [USER]: ... -->` before revision.

### Stage 5 — Publish (`src/publisher.py`)
Run:
```bash
python src/publisher.py <YYMMDD> <N>
```
The script picks the latest draft for that event, copies it to `source/_posts/YYMMDD.md`, moves assets from `_pipeline/draft/YYMMDD-N-assets/`, then runs `pnpm build` + `pnpm deploy`. The calendar regenerates automatically from post frontmatter (see Landing-page Calendar). Do not execute these steps manually.

## Environment Variables

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
| Tracker exits with `RATE LIMITED` | Per-cookie throttle, persists 6–24h. Wait, then re-run with `--merge`. (Distinct from cookie expiry.) |
| Tracker LLM filtering fails | Check the `claude` CLI is on PATH and the Claude Code subscription is active — not OpenRouter or any API key. |

## Subagent Model Selection

Research files must be written entirely in **Simplified Chinese**. Do not write English prose — Chinese names/terms may appear but all explanatory text must be in Chinese.

Use **Haiku** (`model: haiku`) for research subagents — fetch-search-extract tasks that don't require stylistic judgment.

Use **Sonnet** (`model: sonnet`) for write and review subagents — these require nuanced judgment (e.g. no inference, feminist framing) that Haiku handles unreliably.

When dispatching parallel subagents (research, write, or review), run in **batches of 2–3**, not all at once, so a quota hit loses only one batch rather than all work.

## Tracker Blocker Protocol

When the Stage 1 tracker fails, surface the specific error immediately and wait for the user to resolve it. Do not attempt to replace the tracker with WebSearch or other discovery methods — the Weibo UIDs in `.env` are the authoritative event sources.

## Keeping Docs Accurate (anti-drift)

When a learned correction contradicts this file or a `SKILL.md`, fix that file directly — do not park the correction in a memory file as a permanent shadow copy. Auto-memory is for facts *not yet* in the canonical docs; once a fact lands here or in a skill, the memory should be deleted. This is the rule that keeps CLAUDE.md and the skills from drifting out of sync with reality (e.g. venv path, tracker LLM backend, script flags).
