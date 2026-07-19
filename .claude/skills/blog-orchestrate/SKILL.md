---
name: blog-orchestrate
description: Main orchestrator for the feminist blog pipeline — runs tracking, research, writing, reviewing, and publishing with human gates
---

# Blog Orchestrate Skill

You are the main orchestrator for a feminist news blog automation pipeline. You coordinate tracking, research, writing, reviewing, and publishing, with human confirmation at key gates.

Repo root: `/home/jc/Projects/auto-watcher`

## Overview

```
Stage 1 — Track     → _pipeline/events/YYMMDD.md
Stage 2 — Research  → _pipeline/research/YYMMDD-N-title.md   (subagent)
Stage 3 — Write     → _pipeline/draft/YYMMDD-N-title-vN.md   (subagent)
Stage 4 — Review    → _pipeline/review/YYMMDD-N-title-vN.md  (subagent)
Stage 5 — Publish   → source/_posts/YYMMDD.md（同日第二篇起为 YYMMDD-N.md）
```

Human gates: **approve events** (after Stage 1) · **annotate drafts** (after Stage 3) · **approve revision** (after each review) · **confirm publish** (before Stage 5).

## Critical: Never Auto-Chain Stages

After any subagent stage completes (research / draft / review / revision), **STOP**. Report the file written and wait for explicit user go-ahead before triggering the next stage. Do not summarise a review and immediately revise. Do not declare a draft clean and immediately publish. The user reads each output file between stages and may choose to edit, annotate, or redirect.

---

## Stage 1 — Track

### 1a. Show pipeline status

```bash
cd /home/jc/Projects/auto-watcher
python src/pipeline_cli.py status
```

The output includes untracked dates (reconciled against the ledger), in-flight events, and pending-harvest events. Show the user the untracked dates. Default selection is yesterday.

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

If the user has no URL at all — a pure manual brief while the tracker is rate-limited — record it directly instead of running the tracker: `python src/pipeline_cli.py add YYMMDD N 标题` (adds the event to the ledger, pre-selected), then hand-write a matching `## N. 标题` entry in `events/YYMMDD.md` so the event content is readable.

After running, display the events file contents so the user can review.

### 1c. Human gate — Approve events

**Show the numbered event list and ask:**
**"Which events to process? Enter numbers (e.g. '1 3') or 'all', or 'none' to stop."**

Record each approved index in the ledger:

```bash
python src/pipeline_cli.py select YYMMDD N [N...]
```

To drop an event at any gate: `python src/pipeline_cli.py abort YYMMDD N`（记录 abort 并立即归档其工件）.

---

## Stage 2+3+4 — Research → Write → Review loop

### Filter terminal events

Query `event_statuses(date_str)` from `src.utils.ledger` — it returns `{index: state}` for the date. Dispatch only the **in-flight approved** states (`selected`, `research`, `draft-vN`, `review-vN`). Skip:
- `published` / `abort` — terminal, never re-dispatch.
- `candidate` — not yet user-approved (Stage 1c), so do not dispatch.

For each approved (date, index, title) triple:

### 2. Research (subagent)

Dispatch a `blog-researcher` subagent (tools and model are pinned in the agent definition). When processing multiple events, dispatch in **batches of 2–3** so a quota hit loses only one batch.

```
mode: initial
date: YYMMDD
index: N
title: <title>
brief: <one-sentence summary from events file>
sources: <Weibo URLs found in events file for this event, if any>
```

Wait for the subagent to complete and confirm the research file exists at `_pipeline/research/YYMMDD-N-title.md`. Then STOP — the user reads the fact base before writing is approved.

### 3. Write (subagent)

**Freshness check first:** `pipeline_cli.py status` flags in-flight events whose research file is ≥ 2 days old (`（research 已 N 天）`). If the event being dispatched is flagged, recommend an update-mode research refresh and let the user decide — never refresh automatically.

Dispatch a `blog-writer` subagent (no web tools by design — the research file is its sole fact source). Dispatch in **batches of 2–3**.

```
date: YYMMDD
index: N
title: <title>
mode: initial
research_path: _pipeline/research/YYMMDD-N-title.md
```

Wait for the subagent to complete. If it reports fact-base gaps instead of writing a draft, relay the gaps to the user and (on approval) re-dispatch `blog-researcher` — do not ask the writer to improvise.

### 4a. Human gate — Annotate drafts

**After all writes complete for this date, pause and tell the user:**

> "Drafts ready for your review. Please open each draft and add `<!-- [USER]: ... -->` annotations for anything you want preserved during revision. Tell me when you're done."

Wait for the user to confirm before proceeding.

### 4b. Review → Revise loop (human-gated; no max iterations)

For each draft:

**4b-i. Review (subagent):**

Dispatch a `blog-reviewer` subagent:

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

If the review file has a `## 标签提案` section (or the draft contains
`<!-- [TAG-PROPOSAL]: ... -->`), list each proposal and ask the user to approve or
reject. **Never edit the draft in place — 工作留痕：裁定进 review，改动进下一版。**
Approved: add the tag to the matching group in `src/tags.yml` (registry edit only),
and record the approval as a `<!-- [USER]: ... -->` annotation under the review's
`## 标签提案` section; the writer adds the tag to frontmatter and deletes the
proposal comment in the next draft version. Rejected: record the rejection as a
`<!-- [USER]: ... -->` annotation; the writer deletes the comment in the next
version. Only if no further draft version will exist (CLEAN review, no revision
round) may the orchestrator apply the frontmatter/comment edits directly, with
explicit user confirmation.

**Do not auto-trigger revision even if STATUS: ISSUES.** The user may want to annotate the review with `<!-- [USER]: ... -->`, edit suggestions, or stop the loop.

**4b-iii. If user approves — fact-base update first, then revision:**

Check whether the review disputes facts (deterministic, not judgment):

```python
from src.utils.pipeline import review_fact_items
fact_items = review_fact_items(date_str, n)
```

If `fact_items` is non-empty, dispatch a `blog-researcher` subagent in update mode:

```
mode: update
date: YYMMDD
index: N
title: <title>
review_path: _pipeline/review/YYMMDD-N-title-vN.md
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md
```

Then **STOP** — report the marked fact-base changes (补充/更正/查证失败) and wait for the user to inspect them before approving the prose revision.

On approval (or immediately, if `fact_items` was empty), dispatch a `blog-writer` subagent:

```
date: YYMMDD
index: N
title: <title>
mode: revision
research_path: _pipeline/research/YYMMDD-N-title.md
draft_path: _pipeline/draft/YYMMDD-N-title-vN.md   (current draft)
review_path: _pipeline/review/YYMMDD-N-title-vN.md  (current review)
```

If the writer reports 未解决 items, relay them to the user; the fix is another update-mode research dispatch, not writer improvisation.

If publish is later blocked by leftover `<!-- [USER]: ... -->` comments after a CLEAN review (no revision ran to consume them), resolve them with the user directly or dispatch a revision; do not edit the draft unilaterally.

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

The publisher copies drafts to `source/_posts/`, moves assets, and runs `pnpm build` + `pnpm run deploy`. The landing-page calendar regenerates automatically at build time from post frontmatter (`scripts/calendar.js`) — the publisher does not touch it.

After publishing, confirm the posts are live.

---

## Environment

The pipeline reads from environment variables or **`src/.env`** (not the repo root):
- `WEIBO_COOKIE` — required for tracker
- `TRACKED_UIDS` — comma-separated Weibo UIDs the tracker fetches

LLM filtering in the tracker uses the `claude` CLI subprocess (Haiku), not an external API key.

---

## Notes

- Subagent tools and models are pinned in `.claude/agents/blog-researcher.md`, `blog-writer.md`, `blog-reviewer.md` (all Sonnet; the writer has no web tools). Dispatch in batches of 2–3.
- After a full pipeline cycle, suggest running the `blog-curate` skill to maintain notes quality.
