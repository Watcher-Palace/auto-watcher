# Blog Automation — Handoff Document

Everything Claude Code needs to know to bootstrap a new repo for this project.

---

## What This Is

A feminist news blog (Hexo, deployed to GitHub Pages at `https://Watcher-Palace.github.io/blog/`) with a pipeline that tracks Weibo, researches events, writes posts, reviews them, and publishes.

**The key insight from v1:** The research and writing stages must be done by Claude Code directly using its own WebSearch/WebFetch tools — not by calling third-party LLM APIs. Chinese free models (StepFun, Qwen, DeepSeek) censor feminist content. Western free models (Llama, Gemma) are rate-limited or don't support tool use reliably. Claude Code has no such constraints.

---

## Blog Architecture

- **Framework:** Hexo, theme `hexo-theme-landscape`
- **Deploy:** `git@git_personal:Watcher-Palace/blog-auto.git`, branch `main`, via `hexo-deployer-git`
- **SSH alias:** `git_personal` → `~/.ssh/config` → `github.com` with personal key
- **Permalink:** `/:year/:title/`
- **Post assets:** `post_asset_folder: true` — each post has a matching folder `source/_posts/YYMMDD/`

```bash
pnpm run server    # http://localhost:4000
pnpm run build
pnpm run deploy    # build + push to GitHub Pages
```

### Post Frontmatter

```yaml
---
title: Post title
date: 2026-01-23 20:20:39
categories: A   # A=刑事/极恶劣, B=民事/较大, C=非官方/较小, D=个人, N=中立/待续
tags:
- tag1
---
```

Special tags: `PING` = 待续跟进, `TODO` = 待查证

### Inline Formatting

```html
<font color="red">emphasis</font>
<font color="blue">latest update</font>
<font color="grey">verbatim quote</font>
```

### Sections

```
## 概述               (always)
#### 时间线           (inside 概述, if multi-date)
## 信息来源           (always)
## 前情               (optional)
## 后续               (optional)
## 舆论               (optional)
### 微博词条          (inside 舆论)
## 相关内容           (optional)
```

---

## Pipeline Stages

### Stage 1 — Track (Python, headless-capable)

Fetches Weibo and filters for feminist-relevant events.

**Weibo API:**
```
https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}
```

**Critical details:**
- Cookie must be from `weibo.cn` domain (NOT weibo.com) — fields: `_T_WM`, `ALF`, `SSOloginstate`, `SUB`, `SUBP`
- WebClient needs desktop Chrome UA + `Referer: https://m.weibo.cn/` — mobile UA triggers bot detection
- Parse JSON directly; strip HTML from `mblog.text` via BeautifulSoup
- **Include retweet body:** `mblog.retweeted_status.text` — most feminist content is in retweets, not top-level posts
- Deduplication prompt: "If multiple posts describe the same incident, merge them into a single event entry"

**Output:** `_pipeline/events/YYMMDD.md`
```markdown
## N. 标题简述
**Sources**: [url]
**Brief**: 一两句话概述。
```

**Accounts to track (numeric UIDs):**
- `1114030772`

**Topic keywords:** 女性、女权、性别、婚姻、家暴、性侵、拐卖、生育、就业歧视

---

### Stage 2 — Research (Claude Code directly)

Claude Code uses WebSearch + WebFetch to research each approved event and writes the research file.

**Output:** `_pipeline/research/YYMMDD-N-title.md`
```markdown
# Research: {title} ({date}, #{index})

## Facts
[Chronological. <font color="blue"> for most recent updates]

## Parties
[Victims, perpetrators, institutions — their actions, statements, social media posts.
Include Weibo handles where known.]

## Sources
- [来源名称](url) — 关键摘录
```

**Research approach:**
1. Search for event title in Chinese
2. Search specifically for victim/party statements and Weibo posts
3. Search for legal/expert commentary on sentencing or policy issues
4. Fetch key article URLs; extract verbatim quotes

---

### Stage 3 — Write (Claude Code directly)

Claude Code reads the research file and writes the draft, fetching additional URLs as needed.

**Output:** `_pipeline/draft/YYMMDD-N-title-vN.md`

**Style rules:**
- No em dashes (破折号) — restructure the sentence instead
- Concise wording; avoid filler phrases like "此事沉寂数月后"
- Include verbatim quotes from parties in `<font color="grey">` blocks
- Download and embed images (evidence photos, official notices) as assets

**Assets:** `_pipeline/draft/YYMMDD-N-assets/` → moved to `source/_posts/YYMMDD/` on publish

---

### Stage 4 — Review (Claude Code directly)

Claude Code reads the draft independently, fact-checks against sources, and writes a review file.

**Output:** `_pipeline/review/YYMMDD-N-title-vN.md`

Review covers: fact accuracy, missing details, wording issues, category/tag correctness.
Annotates suggestions as `<!-- [REVIEWER]: ... -->`.
User annotates disagreements as `<!-- [USER]: ... -->` before revision.

---

### Stage 5 — Publish (Python)

Copies approved draft to `source/_posts/YYMMDD.md`, moves assets, injects calendar entry into `source/index.md`, runs `pnpm deploy`.

Calendar entry format in index.md (inject into correct month):
```html
<li><a href="/blog/YYYY/title/">YYYY-MM-DD 标题</a> <span class="cat-A">A</span></li>
```

Month names (ZH): 一月 二月 三月 四月 五月 六月 七月 八月 九月 十月 十一月 十二月

---

## Pipeline State Files

```
_pipeline/
  events/YYMMDD.md          # tracked events
  research/YYMMDD-N-title.md
  draft/YYMMDD-N-title-vN.md
  draft/YYMMDD-N-assets/    # images for this draft
  review/YYMMDD-N-title-vN.md
  .state                    # JSON: last_tracked_date, approved_indexes
```

`.state` format:
```json
{"last_tracked_date": "2026-03-25", "approved": {"260325": [1, 3]}}
```

---

## Environment

```
WEIBO_COOKIE=_T_WM=...; ALF=...; SSOloginstate=...; SUB=...; SUBP=...
OPENROUTER_API_KEY=sk-or-...
```

OpenRouter model for tracker: `stepfun/step-3.5-flash:free` (Chinese model, fine for filtering)
Research/write/review: done by Claude Code, no LLM API needed

---

## Lessons Learned (Do Not Repeat)

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| Tracker returns "Nothing noticeable" | Retweet body not extracted | Include `mblog.retweeted_status.text` |
| Weibo fetch fails | Wrong cookie domain (weibo.com vs weibo.cn) | Use cookies from `weibo.cn` DevTools |
| Weibo fetch blocked | Mobile UA triggers bot detection | Use desktop Chrome UA |
| LLM censors content | Chinese models block feminist topics | Use Claude Code directly for research/write/review |
| Free western LLMs fail | Rate limits or no tool-use support | Use Claude Code directly |
| `coordinator.py` can't import scripts | Run from wrong directory | `sys.path.insert(0, str(Path(__file__).parent.parent))` |

---

## Recommended New Architecture

Instead of Python agent scripts calling LLM APIs, structure as:

```
~/.claude/skills/
  blog-coordinator/    # orchestration flow
  blog-researcher/     # research methodology
  blog-writer/         # writing style + template
  blog-reviewer/       # review checklist

scripts/
  tracker.py           # only Python agent needed (headless/cron)
  publisher.py         # only Python script needed (hexo deploy)
  utils/
    pipeline.py        # path resolution, state management
    web.py             # WebClient (fetch + extract_text)
```

Research, writing, and review are all done by Claude Code subagents dispatched from the coordinator skill. This enables parallel research of multiple events and eliminates LLM API dependency for sensitive content.
