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

Human gates: **approve events** (after Stage 1) · **annotate drafts** (after Stage 3) · **confirm publish** (before Stage 5).

---

## Stage 1 — Track

### 1a. Show pipeline status

```python
import sys
sys.path.insert(0, '/home/jc/Projects/auto-watcher')
from scripts.utils.pipeline import pipeline_summary, get_untracked_dates
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
source .venv/bin/activate
python scripts/tracker.py --date YYMMDD
```

The tracker reads `WEIBO_COOKIE` and `OPENROUTER_API_KEY` from environment or `.env`.

After running, display the events file contents so the user can review.

### 1c. Human gate — Approve events

**Show the numbered event list and ask:**
**"Which events to process? Enter numbers (e.g. '1 3') or 'all', or 'none' to stop."**

Write approved indexes to `_pipeline/events/YYMMDD-approved.txt`, one per line.

```python
from scripts.utils.pipeline import approved_path
approved_path(date_str).write_text("\n".join(str(i) for i in approved_indexes) + "\n")
```

---

## Stage 2+3+4 — Research → Write → Review loop

For each approved (date, index, title) triple:

### 2. Research (subagent)

Dispatch a `blog-research` subagent:

```
date: YYMMDD
index: N
title: <title>
brief: <one-sentence summary from events file>
sources: <Weibo URLs found in events file for this event, if any>
```

Wait for the research subagent to complete and confirm the research file exists at `_pipeline/research/YYMMDD-N-title.md`.

### 3. Write (subagent)

Dispatch a `blog-write` subagent in `initial` mode:

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

### 4b. Review → Revise loop (no max iterations)

For each draft, repeat until the review is `STATUS: CLEAN`:

**4b-i. Review (subagent):**

Dispatch a `blog-review` subagent:

```
date: YYMMDD
index: N
title: <title>
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md
```

**4b-ii. Check review status:**

```python
from scripts.utils.pipeline import latest_review
review, v = latest_review(date_str, n)
first_line = review.read_text().splitlines()[0]
# STATUS: CLEAN or STATUS: ISSUES
```

If `STATUS: CLEAN`: proceed to publish.

If `STATUS: ISSUES`:

**4b-iii. Revise (subagent):**

Dispatch a `blog-write` subagent in `revision` mode:

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
source .venv/bin/activate
python scripts/publisher.py --date YYMMDD
```

The publisher copies drafts to `source/_posts/`, moves assets, updates the calendar in `source/index.md`, and runs `pnpm deploy`.

After publishing, confirm the posts are live.

---

## Environment

The pipeline reads from environment variables or `.env` in the repo root:
- `WEIBO_COOKIE` — required for tracker
- `OPENROUTER_API_KEY` — required for tracker

---

## Notes

- Dispatch research subagents in parallel when processing multiple events for the same date.
- Write/review subagents run per-event; they may be parallelised if the user prefers speed over sequential review.
- After a full pipeline cycle, suggest running the `blog-curate` skill to maintain notes quality.
