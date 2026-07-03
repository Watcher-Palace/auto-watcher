---
name: blog-orchestrator
description: Main orchestrator for the feminist blog pipeline — runs tracking, research, writing, reviewing, and publishing with human gates
---

# Blog Orchestrator Skill

You are the main orchestrator for a feminist news blog automation pipeline. You coordinate tracking, research, writing, reviewing, and publishing, with human confirmation at key gates.

Repo root: `/home/jc/Projects/auto-watcher`

## Overview

```
Stage 1 — Track     → _pipeline/events/YYMMDD.md
Stage 2 — Research  → _pipeline/research/YYMMDD-N-title.md   (subagent)
Stage 3 — Write     → _pipeline/draft/YYMMDD-N-title-vN.md   (subagent)
Stage 4 — Review    → _pipeline/review/YYMMDD-N-title-vN.md  (subagent)
Stage 5 — Publish   → source/_posts/YYMMDD.md
```

Human gates: **approve events** (after Stage 1) · **annotate drafts** (after Stage 3) · **approve revision** (after each review) · **confirm publish** (before Stage 5).

## Critical: Never Auto-Chain Stages

After any subagent stage completes (research / draft / review / revision), **STOP**. Report the file written and wait for explicit user go-ahead before triggering the next stage. Do not summarise a review and immediately revise. Do not declare a draft clean and immediately publish. The user reads each output file between stages and may choose to edit, annotate, or redirect.

---

## Stage 1 — Track

### 1a. Show pipeline status

```python
import sys
sys.path.insert(0, '/home/jc/Projects/auto-watcher')
from src.utils.pipeline import pipeline_summary, get_untracked_dates
print(pipeline_summary())
untracked = get_untracked_dates()
```

Show the user the untracked dates. Default selection is yesterday.

Ask: **"Which dates to track? (default: yesterday = YYMMDD, or enter comma-separated dates, or 'none' to skip)"**

If the user provides a date that already has an events file, confirm before overwriting: **"YYMMDD already tracked. Retrack and overwrite? (y/n)"**

### 1b. Run tracker

For each confirmed date, run:

```bash
cd /home/jc/Projects/auto-watcher
source src/venv/bin/activate
python src/tracker.py YYMMDD
```

The tracker reads `WEIBO_COOKIE` and `TRACKED_UIDS` from environment or `.env`. LLM filtering runs via the `claude` CLI subprocess (Haiku), using the local Claude Code subscription — not an external API key.

If the user supplies public Weibo post URLs instead (e.g. while rate-limited), use the anonymous URL mode — no cookie involved:

```bash
python src/tracker.py --urls "url1,url2" YYMMDD
```

After running, display the events file contents so the user can review.

### 1c. Human gate — Approve events

**Show the numbered event list and ask:**
**"Which events to process? Enter numbers (e.g. '1 3') or 'all', or 'none' to stop."**

Record each approved index in the unified status sidecar:

```python
from src.utils.pipeline import record_selected
for i in approved_indexes:
    record_selected(date_str, i)
```

---

## Stage 2+3+4 — Research → Write → Review loop

### Filter terminal events

Query `event_statuses(date_str)` from `src.utils.pipeline` — it returns `{index: state}` for the date. Dispatch only the **in-flight approved** states (`selected`, `researched`, `drafted`, `reviewed`). Skip:
- `published` / `abort` — terminal, never re-dispatch.
- `candidate` — not yet user-approved (Stage 1c), so do not dispatch.

For each approved (date, index, title) triple:

### 2. Research (subagent)

Dispatch a `blog-research` subagent with **`model: haiku`** (mechanical fetch-search-extract). When processing multiple events, dispatch in **batches of 2–3** so a quota hit loses only one batch.

```
date: YYMMDD
index: N
title: <title>
brief: <one-sentence summary from events file>
sources: <Weibo URLs found in events file for this event, if any>
```

Wait for the research subagent to complete and confirm the research file exists at `_pipeline/research/YYMMDD-N-title.md`.

### 3. Write (subagent)

Dispatch a `blog-write` subagent in `initial` mode with **`model: sonnet`** (writing needs nuanced judgment — no inference, feminist framing — that Haiku handles unreliably). Dispatch in **batches of 2–3**.

```
date: YYMMDD
index: N
title: <title>
mode: initial
research_path: _pipeline/research/YYMMDD-N-title.md
```

Wait for the write subagent to complete.

### 4a. Human gate — Annotate drafts

**After all writes complete for this date, pause and tell the user:**

> "Drafts ready for your review. Please open each draft and add `<!-- [USER]: ... -->` annotations for anything you want preserved during revision. Tell me when you're done."

Wait for the user to confirm before proceeding.

### 4b. Review → Revise loop (human-gated; no max iterations)

For each draft:

**4b-i. Review (subagent):**

Dispatch a `blog-review` subagent with **`model: sonnet`** (fact-checking and the no-inference rule need nuanced judgment):

```
date: YYMMDD
index: N
title: <title>
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md
```

**4b-ii. Stop. Report status to user.**

```python
from src.utils.pipeline import latest_review
review, v = latest_review(date_str, n)
first_line = review.read_text().splitlines()[0]
# STATUS: CLEAN or STATUS: ISSUES
```

Tell the user: **"Review v{N} written: {STATUS}. Review file: {path}. Approve revision? (y/n / edit-and-continue)"**

**Do not auto-trigger revision even if STATUS: ISSUES.** The user may want to annotate the review with `<!-- [USER]: ... -->`, edit suggestions, or stop the loop.

**4b-iii. If user approves, dispatch revision (subagent):**

A revision is a `blog-write` subagent — use **`model: sonnet`**.

```
date: YYMMDD
index: N
title: <title>
mode: revision
research_path: _pipeline/research/YYMMDD-N-title.md
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md   (current draft)
review_path: _pipeline/review/YYMMDD-N-title-vN.md  (current review)
```

Return to step 4b-i.

---

## Stage 5 — Publish

### 5a. Human gate — Confirm publish

Show the user a summary of all clean drafts ready to publish. Ask:

**"Ready to publish N post(s): [titles]. Confirm? (y/n)"**

### 5b. Run publisher

```bash
cd /home/jc/Projects/auto-watcher
source src/venv/bin/activate
python src/publisher.py YYMMDD N
```

The publisher copies drafts to `source/_posts/`, moves assets, and runs `pnpm run deploy`. The landing-page calendar regenerates automatically at build time from post frontmatter (`scripts/calendar.js`) — the publisher does not touch it.

After publishing, confirm the posts are live.

---

## Environment

The pipeline reads from environment variables or `.env` in the repo root:
- `WEIBO_COOKIE` — required for tracker
- `TRACKED_UIDS` — comma-separated Weibo UIDs the tracker fetches

LLM filtering in the tracker uses the `claude` CLI subprocess (Haiku), not an external API key.

---

## Notes

- Subagent models and batch sizes are specified inline at each dispatch step above (Haiku for research, Sonnet for write/review, batches of 2–3).
- After a full pipeline cycle, suggest running the `blog-curate` skill to maintain notes quality.
