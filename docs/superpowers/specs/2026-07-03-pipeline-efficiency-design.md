# Pipeline Efficiency Design — Retrieval, Skill Evolution, Draft Linting

Date: 2026-07-03
Status: approved in conversation (user answers recorded below)

## Problem

1. **News retrieval** collides with Weibo's account-level rate limit. The throttle
   (ok:-100 captcha) is attached to the account, not the cookie — swapping cookies on
   the same account does nothing. It is triggered by the current bursty usage pattern:
   multi-week gaps followed by range-mode backfills of up to 20 pages × 4 UIDs
   (~80 requests in ~10 minutes). `PAGINATION_MAX_PAGES = 20` (~200 posts/UID) also
   silently truncates long backfills, losing events even when a run "succeeds".
2. **blog-write does not learn.** The notes.md + blog-curate evolution loop exists but
   has never been fed — all notes.md files are empty. User corrections live in review
   annotations (`## 人类意见`, `<!-- [USER]: -->`) and draft diffs, then evaporate.
   39/58 drafts needed ≥1 revision; category re-grading is the top recurring
   correction (9 events, mostly downgrades from A). The orchestrator skill is seldom
   run — the user drives stages ad hoc — so nothing hung on the orchestrator fires.
3. **Format violations burn Sonnet review cycles.** Mechanical rules (em dashes,
   舆论-without-numbers, source-line format, tag registry) are only caught by the
   Sonnet reviewer or at publish time.

## Validated facts (experiments, 2026-07-03)

- Single post pages on `weibo.com` ARE retrievable with zero account credentials via
  headless Chrome: the Sina Visitor System JS issues tourist cookies automatically.
  Verified: full text of https://weibo.com/1699432410/5306536081752889 extracted.
- Plain curl cannot pass the visitor system (JS required). `m.weibo.cn` detail pages
  are also visitor-walled.
- Anonymous **timeline/profile** access is NOT confirmed — feed XHR returned nothing
  in quick tests. Discovery therefore still requires the logged-in account (or
  user-supplied URLs) until a dedicated spike proves otherwise.

## User decisions (recorded)

- Retrieval: user proposed URL-list + anonymous browser retrieval; confirmed feasible.
  Demand-shaping for the logged-in tracker is the baseline.
- Cadence: **daily scheduled run** accepted.
- Skill evolution: backfill mining + ongoing harvest, but **generalize, don't
  memorize** — and *rules that hold for most posts but have exceptions must be
  presented to the user (with the exception cases) as keep/drop/refine questions,
  never silently adopted or dropped*. Only zero-counterexample rules may be folded
  into SKILL.md directly.
- Linter: approved, runs after write before review.
- The orchestrator cannot be the hook for anything mandatory (seldom run).
  `publisher.py` is the only chokepoint that always runs.

## Workstream A — Tracker v2 (retrieval)

### A1. `src/wbfetch.py` — anonymous post fetcher
- Playwright-python driving system Chrome (`channel="chrome"`, headless).
- Input: a `weibo.com` post URL. Output: dict {url, author, text, retweet_text,
  created_at, image_urls}. Explicit waits on post-text selector; N retries;
  clear error when the visitor flow fails.
- Also exposed as CLI (`python src/wbfetch.py URL...`) so research/write/review
  subagents can read Weibo sources (WebFetch cannot pass the visitor wall).
- Unit tests hermetic (playwright mocked); one live smoke test kept manual/optional.

### A2. `tracker.py --urls` mode
- `python src/tracker.py --urls <file-or-comma-list> [date]`: wbfetch each URL
  anonymously → existing Haiku filter → events file, merge semantics.
- No cookie/account involved. Formalizes the manual-brief workaround.

### A3. Incremental state + request budget (logged-in path)
- `_pipeline/.tracker-state.json`: per-UID `last_seen_id` + resumable catch-up
  cursor (pending window, next page).
- Pagination stops as soon as a page contains only already-seen posts (non-pinned).
- Per-run request budget (default ~40 HTTP page fetches). On exhaustion: persist
  cursor, write partial events (merge), exit 0 with "resume tomorrow" notice —
  a planned multi-day catch-up instead of a RATE LIMITED crash.
- On RateLimited: persist cursor, keep partial results, same resume path.
- New `--daily` mode: incremental fetch since `last_seen_id` for every UID (plus
  resuming any pending catch-up cursor), budget-capped, merge semantics, suitable
  for unattended cron. Existing single-date and range modes remain.
- Error text no longer suggests "fresh cookie from another browser session"
  (account-level limit; already corrected in CLAUDE.md pitfalls).

### A4. Daily cron
- Crontab line running `src/venv/bin/python src/tracker.py --daily` (incremental,
  budget-capped, logs to `_pipeline/tracker.log`). Prepared in `setup/cron.md`;
  installation is a user action (one command).

## Workstream B — Write-skill evolution (learning, not memorizing)

### B1. One-time distillation with validation
- Mine all `_pipeline_archive/review/` + `_pipeline/review/` user annotations and
  v1→final draft diffs.
- Draft general principles; for categories, a rubric stating the *why* of each
  S/A/B/C/D/N boundary with contrastive examples.
- Validate: re-classify all published posts with the rubric; measure agreement
  against final (human-approved) categories.
- Adoption gate: zero-counterexample rules → fold into blog-write SKILL.md.
  Rules with exceptions → `_pipeline/skill-evolution-questions.md`, one entry per
  rule with its exception cases, for the user to keep/drop/refine.

### B2. Ongoing harvest via publisher chokepoint
- `publisher.py` appends `YYMMDD-N` to `_pipeline/harvest-queue.txt` after a
  successful publish and prints a reminder to run harvest.
- `blog-curate` SKILL.md gains a harvest step: consume the queue, read that event's
  reviews + draft versions, distill into notes.md as `[NOTE]`/`[CANDIDATE]` with the
  generalization rule above (principles only, no case specifics; exceptions → ask).
- CLAUDE.md Stage 5 gets one line pointing at the harvest step.

## Workstream C — Draft linter

- `src/linter.py`: deterministic checks — em dash (—), `## 舆论` without concrete
  numbers (阅读量/讨论量/转发量/评论量 + digits), 信息来源 line format
  (`YYYY.MM.DD，来源。*标题*。URL|asset`), tags not in `src/tags.yml`, standalone
  `## 前情`/`## 后续` sections, frontmatter date in the future, missing required
  sections (概述/信息来源). CLI: `python src/linter.py <draft.md>`; nonzero exit
  with violation list.
- blog-write SKILL.md: writer must run the linter and fix violations before
  finishing (initial and revision modes).
- `publisher.py`: run linter as a publish gate (extends existing tag validation).

## Out of scope

- Second Weibo account, RSS supplementation (user chose neither).
- Anonymous timeline discovery (future spike; A1 makes it cheap to attempt).
- Any change to human publish gates.

## Testing

- All new logic TDD'd in `src/tests/`, hermetic (network + claude CLI + playwright
  mocked), same pytest command as CI.
