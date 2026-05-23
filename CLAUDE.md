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

Deploy target: `git@github.com:jshu039-maker/blog.git`, branch `main` (SSH alias `git_personal` may be used).

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
```

Published posts go to `source/_posts/YYMMDD.md` with assets in `source/_posts/YYMMDD/`.

## Post Format

**Frontmatter:**
```yaml
---
title: Post title
date: 2026-01-23 20:20:39
categories: A   # S=政府/国家层面, A=刑事/极恶劣, B=民事/较大, C=非官方/较小, D=个人, N=中立/待续
tags:
- PING          # PING=待续跟进, TODO=待查证
---
```

**Standard sections** (概述 always first; 时间线 inside 概述 if multi-date):
```
## 概述
#### 时间线  (optional)
## 信息来源
## 前情      (optional)
## 后续      (optional)
## 舆论       (optional)
### 微博词条  (inside 舆论)
## 相关内容  (optional)
```

**Inline formatting:**
```html
<font color="red">emphasis</font>
<font color="blue">latest update</font>
<font color="grey">verbatim quote</font>
```

**Asset embedding:**
```html
<img src="{% asset_path filename.jpg %}" width="300" alt="description">
<embed src="{% asset_path file.pdf %}" type="application/pdf" width="100%" height="600px">
```

## index.md Calendar

`source/index.md` contains a monthly calendar table. When publishing, inject a new `<td>` entry (or add a link to an existing date cell). Link format:
```html
<a style="color: red;" href="{{ site.root }}2026/YYMMDD/" title="Post title">link text</a>
```
Color convention: darkred bold = S, red = A, yellow = B, orange = C/mixed, black = N/PING.

## Stage Details

### Stage 1 — Track (`src/tracker.py`)
Run:
```bash
python src/tracker.py [YYMMDD]            # single date (default: yesterday)
python src/tracker.py --days N [--end YYMMDD] [--merge]  # date range
```
Output: `_pipeline/events/YYMMDD.md` with numbered entries (`## N. 标题`).

Implementation details (for debugging, not for manual reimplementation):
- Weibo API: `https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}`
- Cookie must be from `weibo.cn` domain (fields: `_T_WM`, `ALF`, `SSOloginstate`, `SUB`, `SUBP`)
- Use desktop Chrome UA + `Referer: https://m.weibo.cn/` — mobile UA triggers bot detection
- Extract both `mblog.text` AND `mblog.retweeted_status.text` — feminist content is often in retweets
- Tracked account UID: `1114030772`

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
The script picks the latest draft for that event, copies it to `source/_posts/YYMMDD.md`, moves assets from `_pipeline/draft/YYMMDD-N-assets/`, updates `source/index.md` calendar if present, then runs `pnpm build` + `pnpm deploy`. Do not execute these steps manually.

## Environment Variables

```
WEIBO_COOKIE=_T_WM=...; ALF=...; SSOloginstate=...; SUB=...; SUBP=...
OPENROUTER_API_KEY=sk-or-...   # only needed for tracker (tencent/hy3-preview:free)
```

## Known Pitfalls

| Problem | Fix |
|---------|-----|
| Weibo fetch fails silently | Cookie must be from `weibo.cn`, not `weibo.com` |
| Weibo fetch blocked | Use desktop Chrome UA, not mobile |
| Weibo cookie expired (all UIDs fail, no captcha challenge) | Get fresh cookie from browser — do NOT switch to WebSearch for discovery |
| Tracker exits with `RATE LIMITED` | Per-cookie throttle, persists 6–24h. Wait, then re-run with `--merge`. (Distinct from cookie expiry.) |
| OpenRouter model 404 | Update `src/config.yaml` tracker_model to a current free model (e.g. `tencent/hy3-preview:free`) |

## Subagent Model Selection

Research files must be written entirely in **Simplified Chinese**. Do not write English prose — Chinese names/terms may appear but all explanatory text must be in Chinese.

Use **Haiku** (`model: haiku`) for research subagents — fetch-search-extract tasks that don't require stylistic judgment.

Use **Sonnet** (`model: sonnet`) for write and review subagents — these require nuanced judgment (e.g. no inference, feminist framing) that Haiku handles unreliably.

When dispatching parallel research agents, run in **batches of 2–3**, not all at once, so a quota hit loses only one batch rather than all work.

## Tracker Blocker Protocol

When the Stage 1 tracker fails, surface the specific error immediately and wait for the user to resolve it. Do not attempt to replace the tracker with WebSearch or other discovery methods — the Weibo UIDs in `.env` are the authoritative event sources.
