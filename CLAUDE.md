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
  events/YYMMDD-approved.txt # line-separated approved event indexes (e.g. "1\n3")
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
categories: A   # A=刑事/极恶劣, B=民事/较大, C=非官方/较小, D=个人, N=中立/待续
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
Color convention: red = category A, yellow = B, orange = C/mixed, black = N/PING.

## Stage Details

### Stage 1 — Track (Python script)
- Weibo API: `https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}`
- Cookie must be from `weibo.cn` domain (fields: `_T_WM`, `ALF`, `SSOloginstate`, `SUB`, `SUBP`)
- Use desktop Chrome UA + `Referer: https://m.weibo.cn/` — mobile UA triggers bot detection
- Extract both `mblog.text` AND `mblog.retweeted_status.text` — feminist content is often in retweets
- Tracked account UID: `1114030772`
- Output: `_pipeline/events/YYMMDD.md` with numbered entries (`## N. 标题`)

### Stage 2 — Research (Claude Code)
Search Chinese, find verbatim quotes from parties, check legal/expert commentary. Output to `_pipeline/research/YYMMDD-N-title.md` with sections: `## Facts`, `## Parties`, `## Sources`.

### Stage 3 — Write (Claude Code)
Read research file, write draft to `_pipeline/draft/YYMMDD-N-title-v1.md`. Download evidence images to `_pipeline/draft/YYMMDD-N-assets/`. Style: no em dashes (破折号), concise, no filler phrases.

### Stage 4 — Review (Claude Code)
Read draft independently, fact-check against sources. Annotate suggestions as `<!-- [REVIEWER]: ... -->`. User annotates disagreements as `<!-- [USER]: ... -->` before revision.

### Stage 5 — Publish (Python script)
Copy approved draft to `source/_posts/YYMMDD.md`, move assets, update `source/index.md` calendar, run `pnpm deploy`.

## Environment Variables

```
WEIBO_COOKIE=_T_WM=...; ALF=...; SSOloginstate=...; SUB=...; SUBP=...
OPENROUTER_API_KEY=sk-or-...   # only needed for tracker (stepfun/step-3.5-flash:free)
```

## Known Pitfalls

| Problem | Fix |
|---------|-----|
| Tracker returns nothing | Include `mblog.retweeted_status.text` (retweet body) |
| Weibo fetch fails silently | Cookie must be from `weibo.cn`, not `weibo.com` |
| Weibo fetch blocked | Use desktop Chrome UA, not mobile |
| Python import errors in scripts | `sys.path.insert(0, str(Path(__file__).parent.parent))` |
