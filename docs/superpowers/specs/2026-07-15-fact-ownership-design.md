# Single-Owner Fact Base — Pipeline Restructure Design

Date: 2026-07-15
Status: awaiting user review

## Problem

Three pipeline agents search the web. The reviewer's independent search is a
deliberate control and stays. But researcher and writer overlap: the writer's
initial mode re-searches the story ("track to today") and its revision mode
re-verifies disputed facts. That overlap exists for two reasons:

1. **Staleness** — the research file could be days old at write time.
2. **Quality backstop** — Haiku research is sometimes incomplete or too narrow,
   so the Sonnet writer patched the gaps.

The result is paid-for duplication (Sonnet redoes search work on every event)
and muddled ownership (nobody solely owns the fact base — both half-own it).

Two secondary problems ride along:

- **Reviewer format drift.** `blog-review/SKILL.md` specifies a standalone
  review file, but historically the reviewer sometimes produced an annotated
  copy of the draft instead. Annotated copies leak unmarked prose edits.
- **Protocol compliance rests on model discipline.** Nothing but instructions
  stops the writer from searching, the reviewer from hallucinating anchors, or
  a revision from silently dropping a factual comment.

## Design principles

1. **Researcher owns facts for the event's entire lifetime** — initial
   gathering and updates during revision cycles. The research file
   `_pipeline/research/YYMMDD-N-title.md` is the single authoritative fact
   base: a fact not in it does not appear in the draft.
2. **Writer owns prose, category, and tags — and never touches the web** in
   any mode. Enforced by tool allowlist, not instruction.
3. **Reviewer owns independent challenge** — unchanged in substance; its
   output format is hardened.
4. **Never fabricate: report instead.** Any gap the fact base does not resolve
   is reported back, never improvised around.
5. **Protocol compliance is code where possible** — tool allowlists, format
   validators, completeness greps, freshness checks. Model judgment is
   reserved for search coverage, verification reasoning, prose, and
   adjudication.

## Model assignment

| Job | Model | Rationale |
|---|---|---|
| Tracker LLM filtering | Haiku 4.5 (unchanged) | High-volume binary relevance classification; mechanical. |
| Research (initial + update) | **Sonnet 5** (was Haiku) | Coverage judgment: which thread to pull, noticing unlisted angles, deciding sufficiency, weighing sources. Haiku's observed failure mode is exactly "incomplete / too narrow". The old Haiku assignment was premised on the writer backstopping it; the backstop is removed. |
| Write (initial + revision) | Sonnet 5 (unchanged) | No-inference rule, feminist framing, A/B boundary calibration, style discipline. |
| Review | Sonnet 5 (unchanged) | Independent fact-check plus the same judgment rules. |
| Monthly summary | Sonnet 5 (unchanged) | Synthesis into neutral-descriptive prose. |

Net cost stays roughly flat: search tokens move from the write run into the
research run; the untrusted Haiku research pass disappears; update-mode
research fires only when a review disputes facts. If Sonnet research coverage
still disappoints, escalating research to Opus is a one-line change in the
agent definition (out of scope now).

## The new revision cycle

```
draft-vN ──► Reviewer (sonnet, independent web search)
                │   writes review-vN: STATUS + numbered, typed, anchored items
                ▼
             STOP — user reads review, annotates, approves
                │
    ┌───────────┴───────────────┐
    │ 0 items of 类型：事实      │ ≥1 item of 类型：事实   (deterministic count)
    ▼                           ▼
    │                Researcher, update mode (sonnet)
    │                    verifies each 事实 item; edits research file
    │                    in place with 补充/更正/查证失败 marks
    │                           ▼
    │                STOP — user inspects marked fact-base changes
    │                           │
    └───────────┬───────────────┘
                ▼
             Writer, revision mode (sonnet, NO web tools)
                 adjudicates 事实 items against research rulings,
                 style items on own judgment; fills 处理： lines;
                 writes draft-v(N+1); runs linter
                ▼
             STOP — back to review or on to publish (user decides)
```

A style-only review (zero 事实 items) skips the research hop entirely.

## Changes by file

### `.claude/agents/` (new directory, three self-contained agents)

The three stage roles become **full agents, not skill-loading shims**. An
agent definition's body is the subagent's system prompt, injected by the
harness with certainty; a body that says "read SKILL.md first" would
reintroduce a model-dependent hop. The skill/agent split only pays when
knowledge has multiple consumers — each stage skill has exactly one (its
subagent), so the content migrates wholesale:

- **`blog-researcher.md`** — `model: sonnet`; tools include WebSearch,
  WebFetch, Read, Write, Edit, Glob, Grep, Bash. Body = full research
  instructions (see below) + `## 累积经验` (migrated from
  `blog-research/notes.md`).
- **`blog-writer.md`** — `model: sonnet`; tools: Read, Write, Edit, Glob,
  Grep, Bash. **No WebSearch, no WebFetch.** Body = full write instructions
  + `## 累积经验` (migrated from `blog-write/notes.md`).
  (Caveat noted: Bash could in principle fetch the web; removing the search
  tools kills the actual failure mode — habitual WebSearch — and the body
  rule forbids the rest.)
- **`blog-reviewer.md`** — `model: sonnet`; tools include WebSearch, WebFetch,
  Read, Write, Edit, Glob, Grep, Bash. Body = full review instructions +
  `## 累积经验` (migrated from `blog-review/notes.md`).

Frontmatter pins tools and model, so "writer never searches" and "research
runs on Sonnet" are harness-enforced facts, not instructions the
orchestrator must remember. The orchestrator dispatches these subagent types
passing only per-event parameters.

**Deleted:** `.claude/skills/blog-research/`, `.claude/skills/blog-write/`,
`.claude/skills/blog-review/` (SKILL.md + notes.md each), after migration.

**Irreducible read-first files** (shared canonical specs; inlining them into
agent bodies would violate CLAUDE.md's anti-drift rule):
`source/_drafts/template.md` (writer + reviewer) and `src/tags.yml`
(writer; publisher validates against it). These remain read-on-instruction.

### `blog-researcher` agent body (migrates `blog-research/SKILL.md`)

- New input `mode: initial | update`. Update mode adds `review_path` and
  `draft_path` (context only).
- **Absorbs track-to-today** from blog-write, including the strict
  enforcement language: searches must reach today's actual date; the
  `<font color="blue">` mark goes on the last *real* development (never a
  "no update as of X" statement); the marked development's **date is stated
  explicitly** — the writer sets the post's `date:` frontmatter from it.
- **Update mode:** verify each review item of 类型：事实. Edit the research
  file **in place, never destructively**, using marks tied to the review
  version and item number:
  - `**补充（评审vN-问题K）**：…` — new fact added
  - `**更正（评审vN-问题K）**：…（原错误信息：…）` — correction; original
    text preserved adjacent, never deleted
  - `**查证失败（评审vN-问题K）**：X 无法证实` — ruling for a failed
    verification (e.g. a 删除或核查 item)
  - Completeness rule: every 事实 item gets exactly one mark. Verified by
    code (see review validator) before the researcher reports done.
- 5-angle strategy, coverage standard, Simplified-Chinese-only, output
  sections: unchanged.

### `blog-writer` agent body (migrates `blog-write/SKILL.md`)

- **Initial mode:** read the research file, write the draft. Delete the
  "track the story to today" instruction, the "Tracking to today (strictly
  enforced)" paragraph, and all WebSearch/WebFetch references. Blue font and
  `date:` are transcribed from the research file's marked latest development.
- **New authority rule:** the research file is the sole source of facts —
  the existing no-inference rule with a named source of truth.
- **Report, never fabricate (hard rule, both modes):** if the fact base is
  thin, contradictory, or missing something the template requires, do not
  invent and do not guess. Initial mode: write **no draft**; report the
  specific gaps. Revision mode: mark the affected item
  `处理：未解决：<缺口说明>`; finish what is resolvable; report the
  unresolved items. The orchestrator re-dispatches research. (Ledger property: no new file means
  the event state does not advance — a reported failure is state-neutral.)
- **Revision mode:** delete the "verify via WebSearch" and 删除或核查
  verification instructions. For each review item:
  - 类型：事实 → adjudicate by the research file's mark for that item
    (apply 补充/更正 by editing prose; act on 查证失败 by removing the
    content, citing the ruling). **Before closing any 事实 item, its mark
    must exist in the research file** — no mark, no action, report it.
  - 类型：格式 → writer's own judgment.
  - Record the disposition on the item's `处理：` line in the review file:
    `已修改` / `拒绝：<理由>` / `已删除（查证失败）` /
    `未解决：<缺口说明>`. This **replaces** the
    inline `<!-- [WRITER-REJECTED]: -->` convention — the review file is the
    single checklist the user audits at the gate.
  - User annotations (`<!-- [USER]: -->` / `## 人类意见`) take precedence
    over reviewer suggestions, unchanged.
- Template spec, style rules, linter gate, categories (incl. A/B and B/D
  boundary calibrations), tags + TAG-PROPOSAL protocol: **unchanged; the
  writer keeps tag selection and proposal.** The migrated body explicitly
  retains the read-first instructions for `source/_drafts/template.md`
  (canonical format spec — single source of truth, never inlined) and
  `src/tags.yml` (tag registry) before writing.

### `blog-reviewer` agent body (migrates `blog-review/SKILL.md`)

- Keep the standalone review file (already the spec; annotated draft copies
  were drift). Harden the format — per item:

  ```
  STATUS: ISSUES                ← line 1, exactly CLEAN or ISSUES

  ## 问题 1
  类型：事实                     ← or 格式
  原文：`<exact verbatim quote from the draft>`
  <!-- [REVIEWER]: <suggested correction or question> -->
  处理：                         ← left empty; filled by the writer
  ```

- 类型 definitions: 事实 = wrong/unverifiable/stale/missing facts (anything
  requiring the fact base to change); 格式 = template, structure, style,
  wording, colour-convention violations.
- **Mandatory validation gate** (mirrors the writer's lint gate): run
  `src/venv/bin/python src/review_linter.py <review-path>` and fix every
  violation before finishing.
- Review process steps (independent verification, quote tracing, blue-marker
  check, template comparison), 标签提案 transcription, style notes: unchanged.

### `.claude/skills/blog-orchestrator/SKILL.md`

- **Stage 2:** dispatch the `blog-researcher` subagent type, `mode: initial`.
  Model comes from the agent definition.
- **Stage 3 freshness check:** before dispatching a write, compare today with
  the research file's date (code helper). If older than 2 days, recommend an
  update-mode refresh; the user decides. No auto-refresh.
- **Stage 4b:** after the review STOP, count 类型：事实 items (code helper,
  not judgment). ≥1 → dispatch update-mode research → STOP (user inspects
  the marked fact-base diff) → on approval dispatch writer revision. 0 →
  straight to writer revision on approval. Two STOPs per factual cycle,
  consistent with Never Auto-Chain.
- Dispatch blocks lose the read-skills-first preambles (instructions live in
  the agent bodies) and the `model:` lines (pinned in agent frontmatter).
- Notes section: batches of 2–3 unchanged, now covering Sonnet research.

### `.claude/skills/blog-curate/SKILL.md`

- Retargets from skill notes to the three agent files: curates each agent's
  `## 累积经验` section and promotes `[CANDIDATE]` entries into that agent's
  instruction sections (one file per role instead of SKILL.md + notes.md).
- All curation logic unchanged: harvest flow, general-principles-only rule,
  exception gate, `[NOTE]`/`[CANDIDATE]` tags, ~15-entry cap,
  prefer-code-over-prose routing (linter / template.md / agent body), and the
  ~180-line compaction flag (now applied to each agent file).

### `CLAUDE.md`

- **Subagent Model Selection** rewritten: all pipeline subagents (research,
  write, review, summary) use Sonnet; Haiku survives only in the tracker's
  LLM filtering (a `claude` CLI subprocess, not a subagent). Models for
  research/write/review are pinned in agent frontmatter, not chosen at
  dispatch. Rationale: the writer no longer backstops research, so research
  needs coverage judgment.
- Stage 2–4 descriptions: "invoke the blog-X skill before dispatching"
  becomes "dispatch the blog-X agent". Stage 2: initial + update modes.
  Stage 3: the writer does not search; the research file is the sole fact
  source. Stage 4: hardened review format, update-mode research hop.
- Post Format pointer updated: judgment rules now live in the
  `blog-writer` agent definition (was: the `blog-write` skill).

### New code

- **`src/review_linter.py`** — validates a review file:
  1. First line is exactly `STATUS: CLEAN` or `STATUS: ISSUES`.
  2. Items are numbered `## 问题 K` (K = 1..n, no gaps), each with a 类型
     line (`事实` or `格式`) and an `原文：` line.
  3. **Anchor check** (default mode, run by the reviewer): every `原文`
     quote appears verbatim in the draft of the **same version** as the
     review's `-vN`. Catches hallucinated anchors deterministically.
  4. `--check-marks` mode (run by the researcher after an update pass):
     every 事实 item K has a `（评审vN-问题K）` mark in the research file.
  5. `--check-dispositions` mode (run by the writer after a revision):
     every item has a non-empty `处理：` line. Skips the anchor check (the
     writer has already produced draft-v(N+1); anchors refer to vN). Exits
     with a distinct code when any `未解决` disposition is present, so the
     orchestrator sees "revision done but research re-dispatch needed"
     mechanically.
- **`src/utils/pipeline.py` helpers** —
  - `review_fact_items(date_str, n) -> list[int]`: item numbers with
    类型：事实 in the latest review (drives the orchestrator's branch).
  - `research_age_days(date_str, n) -> int | None`: age of the research file
    (drives the Stage 3 freshness recommendation; also surfaced by
    `pipeline_cli.py status` for in-flight events past `selected`).
- **`src/publisher.py` pre-flight: no unresolved comments at publish** —
  before build/deploy, two deterministic checks (added alongside the
  existing row/tag/TAG-PROPOSAL checks):
  1. If a review exists for the event, the latest review must be fully
     dispositioned: every 问题 item has a non-empty `处理：` line and none
     is `未解决` (reuses the `--check-dispositions` logic, exposed as an
     importable function from `review_linter`). A `STATUS: CLEAN` review
     has no items and passes trivially; no review at all is not blocked
     (unchanged behavior — the human gate covers that case).
  2. The draft to be published contains no pipeline comment markers:
     `<!-- [USER]:`, `<!-- [REVIEWER]:`, `<!-- [WRITER-`. These are
     work-in-progress annotations and must all be consumed by revision
     before deploy. (Publish-time only — a draft legitimately carries
     `[USER]` annotations before revision, so this does not go in the
     write-time linter.)
- **`.claude/settings.json` (project, committed)** — permission allow-rules
  so subagent gate commands run without prompting:
  - `Bash(src/venv/bin/python src/linter.py:*)`
  - `Bash(src/venv/bin/python src/review_linter.py:*)`
  - the standardized path-helper invocations used by the skills
  Skills standardize on these exact command forms so the rules match.
- **Tests** — hermetic pytest for `review_linter` (fixture review + draft
  files: valid, bad status, missing 类型, non-verbatim anchor, missing mark,
  empty 处理, 未解决 exit code), the two pipeline helpers, and the publisher
  pre-flight (blocks on undispositioned review / 未解决 / lingering comment
  markers; passes on CLEAN or no review). Existing tests untouched.

## What does not change

- `src/utils/ledger.py`, `src/tracker.py`; `src/publisher.py` changes only
  by the added pre-flight checks. No state-machine change: research files
  stay unversioned and are edited in place; `_derive_state` behavior is
  untouched.
- `blog-orchestrator`, `blog-summary`, `blog-curate` remain **skills** —
  main-thread procedures / user-invoked commands, which is what skills are
  for. (`blog-summary` still dispatches a generic Sonnet subagent; converting
  it to an agent is optional-later, not in scope.)
- The reviewer's independent web search (the control).
- Human gates; Never Auto-Chain.
- The earlier URL-specific ideas (skip-research mode, `Source-Mode` marker)
  are **dropped as moot**: under single-owner research, a URL event pays one
  fresh Sonnet research pass like any other event — the duplication it was
  meant to avoid no longer exists.

## What stays model judgment

Search coverage and sufficiency, verification reasoning, prose quality,
类型 classification, adjudication of 格式 suggestions, feminist framing.
Everything about protocol compliance — who touched which file, anchor
veracity, mark/disposition completeness, freshness — is code.

## Out of scope (possible later)

- Requiring that a review exist (and be CLEAN) before publish — today the
  human gate covers this; the new pre-flight only blocks *unresolved*
  comments, not the absence of a review.
- Escalating research to Opus.
- Retrofitting old archived reviews to the new format (never needed; archives
  are read-only history).
