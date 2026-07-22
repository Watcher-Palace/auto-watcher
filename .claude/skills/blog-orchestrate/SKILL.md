---
name: blog-orchestrate
description: Main orchestrator for the feminist blog pipeline — runs tracking, research, writing, reviewing, and publishing with human gates
---

# Blog Orchestrate Skill

You are the main orchestrator for a feminist news blog automation pipeline. You coordinate tracking, research, writing, reviewing, and publishing, with human confirmation at key gates.

Repo root: `/home/jc/Projects/auto-watcher`

**Every Bash call must start from the absolute repo root, and every `python` command
needs the venv activated in the same call.** Shell state does not persist between
calls (bare `python` → `command not found`) but the **working directory does** — so a
repeated `cd source/_posts` fails and relative paths resolve against wherever the last
call ended. Always prefix:

```bash
cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python ...
```

The command blocks below omit the prefix for readability; add it every time.

## Overview

```
Stage 1 — Track     → _pipeline/events/YYMMDD.md
Stage 2 — Research  → _pipeline/research/YYMMDD-N-title.md   (subagent)
Stage 3 — Write     → _pipeline/draft/YYMMDD-N-title-vN.md   (subagent)
Stage 4 — Review    → _pipeline/review/YYMMDD-N-title-vN.md  (subagent)
Stage 5 — Publish   → source/_posts/YYMMDD.md（同日第二篇起为 YYMMDD-N.md）
```

Human gates: **approve events** (after Stage 1) · **送审/打回/abort** (after Stage 3) · **annotate the review + approve revision** (after each review) · **confirm publish** (before Stage 5).

## Critical: Never Auto-Chain Stages

After any subagent stage completes (research / draft / review / revision), **STOP**. Report the file written and wait for explicit user go-ahead before triggering the next stage. Do not summarise a review and immediately revise. Do not declare a draft clean and immediately publish. The user reads each output file between stages and may choose to edit, annotate, or redirect.

## Critical: Report Terse（用户裁定，2026-07-21）

用户读输出文件本身，**不需要你把 subagent 的汇报转述一遍**。默认汇报格式是一行：

> `260716-7 review v3：ISSUES — 事实 2 / 格式 5。{path}`

草稿/研究同理：`260706-5 v5 已写：{path}`、`260708-4 研究完成：{path}（资产 3 件）`。不要复述逐条问题、不要转贴 subagent 的汇报原文、不要解释它做了什么改动——用户会自己打开文件看。

**只有这三类内容才展开写**（写清楚，不要压缩）：

1. **需要用户裁决的**：标签提案、信源冲突无法定论、事实与用户既有裁定抵触、subagent 报回的缺口需要决定是补研究还是删内容。把选项和你的推荐一并给出。
2. **系统性问题**：同一类错误跨多篇复现（如一天内两次二次化名）、研究文件层面的错误被写手照抄、某条规则反复失效——这类要指出模式本身，并说明打算改哪个 agent 文件的哪条规则。
3. **你自己的偏离**：你跳过了某个人类闸口、超出用户设定的批次上限、替 subagent 做了它该做的判断——主动说，别等用户发现。

subagent 汇报里的其余内容（逐条改了什么、跑了哪些 gate、自查结果）一律不转述。gate 失败或 linter 不通过属于第 3 类，要说。

---

## Stage 1 — Track

### 1a. Show pipeline status

```bash
cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python src/pipeline_cli.py status
```

The output includes untracked dates (reconciled against the ledger), in-flight events, and pending-harvest events. Show the user the untracked dates. Default selection is yesterday.

Ask: **"Which dates to track? (default: yesterday = YYMMDD, or enter comma-separated dates, or 'none' to skip)"**

If the user provides a date that already has an events file, confirm before overwriting: **"YYMMDD already tracked. Retrack and overwrite? (y/n)"**

### 1b. Run tracker

Run once for all confirmed dates (the date arg is positional and accepts several):

```bash
cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python src/tracker.py YYMMDD [YYMMDD ...]
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

值得关注但暂无可靠来源/相关性未定的事件，在任一闸口可记 `python src/pipeline_cli.py
staged YYMMDD N`（终态：最新草稿移入 `source/_drafts/` 存查、不发布，其余工件归档；
后续报道出现时按新事件重新收录）。

---

## Stage 2+3+4 — Research → Write → Review loop

### Filter terminal events

Query `event_statuses(date_str)` from `src.utils.ledger` — it returns `{index: state}` for the date. Dispatch only the **in-flight approved** states (`selected`, `research`, `draft-vN`, `review-vN`). Skip:
- `published` / `abort` / `staged` — terminal, never re-dispatch.
- `candidate` — not yet user-approved (Stage 1c), so do not dispatch.

For each approved (date, index, title) triple:

### 2. Research (subagent)

Dispatch a `blog-researcher` subagent (tools and model are pinned in the agent definition). 多事件时按批派发（批量规则见 Notes）。

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

Dispatch a `blog-writer` subagent (no web tools by design — the research file is its sole fact source). （批量规则见 Notes）

```
date: YYMMDD
index: N
title: <title>
mode: initial
research_path: _pipeline/research/YYMMDD-N-title.md
```

Wait for the subagent to complete. If it reports fact-base gaps instead of writing a draft, relay the gaps to the user and (on approval) re-dispatch `blog-researcher` — do not ask the writer to improvise.

### 4a. Human gate — Send to review, or drop

**After all writes complete for this date, pause and tell the user:**

> "Drafts ready. 送审 / 打回重写 / abort / staged？"

Wait for the user to decide before proceeding.

**Do NOT ask the user to annotate the draft here（用户裁定 2026-07-21）.** `[USER]`
annotations belong in the **review file**, at gate 4b-ii — never in a draft. Two
reasons, both structural:

- publisher.py `publish()` 预检 refuses any draft containing `[USER]`, and only a revision
  consumes them. A CLEAN review runs no revision, so a draft annotation made here
  deadlocks publishing.
- Draft-inline `[USER]` is deleted once applied（见 blog-writer《Revision Mode》）, which is
  exactly the outcome blog-writer《不许删 review 文件里的 [USER] 注释》条 forbids for review files — the user's
  reasoning disappears and the next review re-raises the same point.

If the user wants a draft killed before spending a review pass, that is `abort`,
not an annotation.

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

Tell the user, one line (见上方 Report Terse)：**"{date}-{n} review v{N}：{STATUS} — 事实 {X} / 格式 {Y}。{path}"**，再问 `Approve revision? (y/n / edit-and-continue)`。计数用 `review_fact_items()` 与 `类型：格式` 的条目数，不要逐条复述问题内容。

**这里是唯一的 `[USER]` 标注点。** 用户的异议、裁定、追加要求都写进**评审文件**——
`## 人类意见` 节，或挂在具体 `## 问题 K` 下。评审文件是工作留痕，写手只能在其后追加
"（已应用）"，**不得删除或改写**（blog-writer《不许删 review 文件里的 [USER] 注释》条）。不要让用户往草稿里标。

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

If publish is blocked by leftover `<!-- [USER]: ... -->` comments in a draft, the
annotation went to the wrong file — see gate 4a. Resolve it with the user directly or
dispatch a revision to consume it; do not edit the draft unilaterally.

Return to step 4b-i.

---

## Stage 5 — Publish

### 5a. Human gate — Confirm publish

Show the user a summary of all clean drafts ready to publish. Ask:

**"Ready to publish N post(s): [titles]. Confirm? (y/n)"**

### 5b. Run publisher

```bash
cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python src/publisher.py YYMMDD N
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

- Subagent tools and models are pinned in `.claude/agents/blog-researcher.md`, `blog-writer.md`, `blog-reviewer.md` (all Sonnet; the writer has no web tools). Dispatch in batches of up to 3 (user directive 2026-07-20).
- After a full pipeline cycle, suggest running the `blog-curate` skill to maintain notes quality.
