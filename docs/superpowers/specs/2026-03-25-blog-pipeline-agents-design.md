# Blog Pipeline — Agents & Skills Design

**Date:** 2026-03-25
**Status:** Approved

---

## Overview

Encapsulate the feminist blog automation pipeline into Claude Code skills and subagents. Research, writing, and review are done by Claude Code directly (not LLM APIs) to avoid censorship of feminist content.

---

## File Structure

```
/home/jc/Projects/auto-watcher/
  .claude/skills/
    blog-orchestrator/
      SKILL.md              ← main skill, invoked by user as /blog
    blog-research/
      SKILL.md              ← research methodology
      notes.md              ← accumulated knowledge, max ~15 entries
    blog-write/
      SKILL.md              ← draft format, style rules
      notes.md              ← accumulated writing/voice notes
    blog-review/
      SKILL.md              ← review checklist, annotation format
      notes.md              ← accumulated reviewer patterns
    blog-curate/
      SKILL.md              ← curation workflow (promote, prune, conflict-check)

  scripts/
    tracker.py              ← Weibo fetch + LLM filter → events file
    publisher.py            ← copy draft, move assets, update index.md, pnpm deploy
    utils/
      pipeline.py           ← path resolution, state, pipeline_summary()
      web.py                ← WebClient (Weibo fetch + extract_text)
    .env                    ← WEIBO_COOKIE, OPENROUTER_API_KEY
    config.yaml             ← tracker LLM model config

  setup/
    symlink-skills.sh       ← one-time: ln -s .claude/skills/blog-* ~/.claude/skills/
```

Skills are versioned in the repo. A one-time symlink step makes them available to the `Skill` tool:

```bash
bash setup/symlink-skills.sh
```

This symlinks each `.claude/skills/blog-*/` directory into `~/.claude/skills/`. The existing global `~/.claude/skills/blog-coordinator/` is retired — its `description` entry in `~/.claude/settings.json` (under `skills`) is updated to reference `blog-orchestrator` instead.

---

## Pipeline State

`_pipeline/.state` is a plain-text file containing the last tracked date in `YYYYMMDD` format:

```
20260325
```

`pipeline.py` owns reads and writes to this file. `pipeline_summary()` reads it to show the current pipeline status at session start.

---

## Event Index (`N`)

`N` is the 1-based integer index from the `_pipeline/events/YYMMDD.md` events file (e.g., `## 1. Title` → `N=1`). `_pipeline/events/YYMMDD-approved.txt` stores the approved indexes as newline-separated integers. All pipeline file paths (`research/`, `draft/`, `review/`) use this same `N`.

---

## Skills

### `blog-orchestrator` — invoked as `/blog`

Owns the full pipeline flow and all human gates. Does not accumulate notes.

**Flow:**

```
Start
  └─ run pipeline_summary(), show date + pending state
  └─ check notes.md length for blog-research, blog-write, blog-review
     if any exceeds 15 entries → warn: "Consider running /blog-curate"

Stage 1 — Track
  └─ show untracked dates (dates with no events file, up to last 7 days)
  └─ ask user: which date to track? (default: yesterday)
  └─ if events file for that date already exists:
       ask: retrack and overwrite, or use existing?
       if retrack → run scripts/tracker.py, overwrite _pipeline/events/YYMMDD.md
       if use existing → show file and continue
  └─ otherwise: run scripts/tracker.py for the given date
  └─ show _pipeline/events/YYMMDD.md
  └─ ── GATE 1 ── which indexes to approve?
                  write _pipeline/events/YYMMDD-approved.txt

Stage 2 — Research (parallel)
  └─ dispatch one blog-research subagent per approved event (concurrent)
  └─ wait for ALL to complete
  └─ each writes _pipeline/research/YYMMDD-N-title.md

Stage 3 — Write (parallel)
  └─ dispatch one blog-write subagent per approved event (concurrent)
  └─ wait for ALL to complete
  └─ each writes _pipeline/draft/YYMMDD-N-title-v1.md
  └─ ── GATE 2 ── tell user: drafts are ready; annotate with <!-- [USER]: ... -->
                  wait for explicit confirmation before proceeding

Stage 4 — Review loop (per draft, independently; no iteration limit)
  ┌─ dispatch blog-review subagent → reads latest draft vN, writes review file
  │   review file begins with STATUS: CLEAN or STATUS: ISSUES
  └─ if STATUS: ISSUES:
       dispatch blog-write subagent for revision → produces vN+1
       repeat from top of loop
     if STATUS: CLEAN:
       proceed to Gate 3

  └─ ── GATE 3 ── confirm publish for the clean draft

Stage 5 — Publish (per confirmed draft)
  └─ run scripts/publisher.py
  └─ warn user explicitly: this runs pnpm deploy → GitHub Pages
```

---

### Draft Versioning

- `next_draft_path(date_str, N, title)` in `pipeline.py` auto-increments the version number by scanning existing files.
- Old draft versions are retained (not deleted) — full revision history is preserved.
- Review files are versioned to match their corresponding draft: `_pipeline/review/YYMMDD-N-title-v1.md` reviews `draft/YYMMDD-N-title-v1.md`, and so on.

---

### User Annotation Pass-Through

1. Gate 2: user annotates the first draft (`v1`) with `<!-- [USER]: ... -->`.
2. blog-review reads `v1` (with user annotations present).
3. If revision needed: blog-write reads `v1` + its review file → produces `v2`, applying `[REVIEWER]` suggestions but preserving all `[USER]` annotations.
4. blog-review reads `v2`. User annotations from `v1` propagate into `v2` by the writer, so the reviewer always sees the current state.

---

### Review File Format

Every review file produced by blog-review begins with a machine-readable status line, followed by annotated content:

```markdown
STATUS: ISSUES

<!-- [REVIEWER]: ... -->
```

or:

```markdown
STATUS: CLEAN
```

The orchestrator reads the first line of the review file to determine whether to loop or proceed.

---

### `blog-research` — subagent skill

Researches a single event using WebSearch + WebFetch. Writes `_pipeline/research/YYMMDD-N-title.md`.

**SKILL.md contains:** search strategy (Chinese queries, party statements, legal commentary), research file format (Facts / Parties / Sources), what constitutes sufficient coverage.

**notes.md:** accumulated knowledge — recurring sources, known institutions, search patterns that work well.

---

### `blog-write` — subagent skill

Reads the research file, writes or revises a draft. Uses WebSearch + WebFetch to fetch additional sources not in the research file. Writes `_pipeline/draft/YYMMDD-N-title-vN.md`.

**SKILL.md contains:** draft format (frontmatter, sections), style rules (no em dashes, concise, `<font>` tags, asset embedding), revision mode (apply `[REVIEWER]` suggestions unless `[USER]` overrides), category/tag definitions.

**notes.md:** accumulated voice and style notes — phrasings to avoid, tone patterns, recurring formatting decisions.

---

### `blog-review` — subagent skill

Independently fact-checks a draft against its sources. Uses WebSearch + WebFetch to verify claims. Writes `_pipeline/review/YYMMDD-N-title-vN.md` beginning with `STATUS: CLEAN` or `STATUS: ISSUES`, followed by `<!-- [REVIEWER]: ... -->` annotations inline in a copy of the draft.

**SKILL.md contains:** review checklist (accuracy, missing facts, category/tag correctness, wording), annotation format, pass criteria — what constitutes STATUS: CLEAN vs STATUS: ISSUES.

**notes.md:** accumulated patterns — recurring mistakes, common issues to watch for.

---

### `blog-curate` — invoked as `/blog-curate`

On-demand curation of all skill notes. Does not run automatically.

**Flow:**
1. Read all `SKILL.md` + `notes.md` files together (blog-research, blog-write, blog-review)
2. Flag contradictions between notes and skills — e.g., a note saying "always do X" when SKILL.md says "never do X", or a note that duplicates a rule already in SKILL.md
3. Identify `[CANDIDATE]` entries in notes → propose promotion to SKILL.md
4. Identify redundant, outdated, or superseded notes → propose pruning
5. Present a consolidated diff for user approval before writing anything

---

## Notes Format

Each `notes.md` entry is a single dated line tagged `[NOTE]` or `[CANDIDATE]`:

```markdown
- [NOTE] 2026-03-25: Avoid naming victims in headlines unless they have self-identified publicly
- [CANDIDATE] 2026-03-20: Always check 最高人民法院 sentencing guidelines for criminal cases
```

`[CANDIDATE]` = reliable enough to promote to SKILL.md. Once promoted, the note is deleted. Soft cap: ~15 entries per file. The length check at session start covers blog-research, blog-write, and blog-review (the three skills with notes.md files). blog-curate has no notes.md.

---

## Asset Lifecycle

During Stage 3 (Write), blog-write downloads evidence images and other media to `_pipeline/draft/YYMMDD-N-assets/`. Assets are referenced in the draft using Hexo's `{% asset_path filename %}` syntax.

During Stage 5 (Publish), `publisher.py` moves `_pipeline/draft/YYMMDD-N-assets/` to `source/_posts/YYMMDD/` so Hexo can resolve the asset paths at build time.

---

## Python Scripts

| Script | Responsibility |
|---|---|
| `scripts/tracker.py` | Weibo API fetch, strip HTML from `mblog.text` + `mblog.retweeted_status.text`, LLM filter for feminist relevance, deduplicate, write `_pipeline/events/YYMMDD.md` |
| `scripts/publisher.py` | Copy draft → `source/_posts/YYMMDD.md`, move assets to `source/_posts/YYMMDD/`, inject calendar entry into `source/index.md`, run `pnpm deploy` |
| `scripts/utils/pipeline.py` | Path resolution (`research_path`, `next_draft_path`), state read/write (`_pipeline/.state`), `pipeline_summary()` |
| `scripts/utils/web.py` | `WebClient`: Weibo fetch with desktop Chrome UA + `weibo.cn` cookie, `extract_text()` |

Tracker uses OpenRouter (`stepfun/step-3.5-flash:free`) only for event filtering. Research, writing, and review use Claude Code directly.

### Calendar Entry Format (publisher.py)

`source/index.md` contains a monthly calendar table. On publish, `publisher.py` injects a link into the correct date cell:

```html
<a style="color: red;" href="{{ site.root }}2026/YYMMDD/" title="Post title">link text</a>
```

Color convention: red = category A, yellow = B, orange = C/mixed, black = N/PING.

---

## Cron Compatibility

The current design is manual-first (`/blog` invokes the full flow). To make Stage 1 cron-driven later:

- `tracker.py` can run standalone on a schedule
- The orchestrator checks `_pipeline/.state` and skips tracking if today's date matches the stored date (events file already written)
- Gate 1 becomes an async notification — user runs `/blog` to continue from Gate 1

No structural changes are needed — cron compatibility is achieved by running the tracker independently.
