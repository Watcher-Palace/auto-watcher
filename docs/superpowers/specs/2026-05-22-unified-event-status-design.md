# Unified Event Status Sidecar — Design

## Problem

Per-date pipeline state currently splits across two files:

- `_pipeline/events/YYMMDD-approved.txt` — line-separated user-approved event indexes (one per line, no state).
- `_pipeline/events/YYMMDD-status.txt` — terminal states only (`N:published` / `N:aborted`).

Consequences:

1. Querying "what is event N doing right now?" requires checking three places: the approved file, the status file, and `_pipeline/{research,draft,review}/` for file presence.
2. Two separate writers (orchestrator and publisher) means two file formats to maintain.
3. There is no explicit "candidate" state for events that exist in `YYMMDD.md` but the user hasn't decided on yet — they are absent from both files, which is indistinguishable from "haven't tracked yet."

## Approach

Collapse the two files into one: `_pipeline/events/YYMMDD-status.txt`. Each line is `N:state`. The file is rewritten on every change (one line per event index, sorted ascending). The sidecar stores only **user decisions**; transient pipeline-stage states are derived from file presence at read time.

## State model

| State | Source | Meaning |
|---|---|---|
| `candidate` | derived (default) | Index appears in `YYMMDD.md` but not in sidecar. Not yet decided. |
| `selected` | stored | User approved for processing. |
| `researched` | derived | `_pipeline/research/YYMMDD-N-*.md` exists. |
| `drafted` | derived | `_pipeline/draft/YYMMDD-N-*-v*.md` exists. |
| `reviewed` | derived | `_pipeline/review/YYMMDD-N-*-v*.md` exists. |
| `published` | stored | Publisher recorded after a successful deploy. |
| `abort` | stored | User dropped the event. |

Stored states (written to sidecar): `selected`, `published`, `abort`. Three values; everything else is computed.

### Precedence on read

When resolving `event_status(date, n)`:

1. If sidecar has `N:abort` → return `abort`. Terminal; overrides everything.
2. If sidecar has `N:published` → return `published`.
3. Otherwise walk derived states in this order, returning the first match:
   - `_pipeline/review/{date}-{n}-*-v*.md` exists → `reviewed`
   - `_pipeline/draft/{date}-{n}-*-v*.md` exists → `drafted`
   - `_pipeline/research/{date}-{n}-*.md` exists → `researched`
4. If sidecar has `N:selected` → return `selected`.
5. Otherwise → `candidate`.

This ordering is "highest stage reached wins, except terminal user decisions trump derived state."

## Helpers (`src/utils/pipeline.py`)

All sidecar-aware code moves to `pipeline.py`. `record_published` and `_post_slug` migrate out of `src/publisher.py` (they currently live there for historical reasons; this is a good moment to consolidate).

### Writers

Each writer loads the full sidecar, sets/replaces the line for `n`, and writes the file back sorted by integer index ascending, one line per event, trailing newline.

- **`record_selected(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None`**
  - If sidecar already has `n` as `published` or `abort` → raise `RuntimeError` (the prior decision should be explicitly reversed by hand).
  - Otherwise write `n:selected`. Idempotent if already `selected`.

- **`record_aborted(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None`**
  - If sidecar already has `n` as `published` → raise `RuntimeError` (don't abort what already shipped).
  - Otherwise write `n:abort`. Overwrites any prior `selected`. Idempotent if already `abort`.

- **`record_published(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None`**
  - If sidecar already has `n` as `published` → no-op (idempotent).
  - If sidecar already has `n` as `abort` → raise `RuntimeError`.
  - Otherwise write `n:published`. Overwrites any prior `selected`.

All three writers reject lines with unknown stored states when reading existing files (matches current `record_published` behavior).

### Readers

- **`event_status(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> str`** — returns one of the 7 states per the precedence rules.
- **`event_statuses(date_str: str, pipeline_dir: Path = PIPELINE) -> dict[int, str]`** — returns `{n: state}` for every index that appears in `_pipeline/events/{date_str}.md`. Indexes are parsed from `## N. ...` headings (matching existing convention). If the events file is missing, returns `{}`.

`event_statuses` is the single function the orchestrator's "Show pipeline status" and "Filter terminal events" steps both call.

### Removed helper

`approved_path` is removed from `pipeline.py`. It has one caller (the orchestrator skill) which is updated in this PR.

## Sidecar format

```
1:abort
3:selected
7:published
```

- One line per event. Sorted by integer index ascending.
- `state ∈ {selected, abort, published}` only. Any other value is a format error (readers raise).
- Blank lines and `#`-prefixed comments are ignored (matches existing behavior). When rewriting, comments are NOT preserved — the file is regenerated from parsed state. (This is a behavior change for the existing `record_published` helper, which currently preserves comments via append-only. With rewrite, comments don't survive. None of the 9 current sidecars have comments, so no live data is affected.)

## Migration

One-shot script `src/migrate_status.py`. Created, run once, and deleted in the same PR. The script:

For each `_pipeline/events/YYMMDD.md`:
1. Initialize `entries: dict[int, str] = {}`.
2. If `YYMMDD-status.txt` exists: parse each line; rename `aborted` → `abort`; populate `entries`.
3. If `YYMMDD-approved.txt` exists: for each line `N`, set `entries[int(N)] = "selected"` only if `N` is not already in `entries` (existing `published`/`abort` wins by precedence).
4. Write the merged result back to `YYMMDD-status.txt`, sorted by index.
5. Delete `YYMMDD-approved.txt`.

The same commit that lands the migrated sidecars also deletes `src/migrate_status.py`. No backward-compatibility code stays in the codebase. The script remains recoverable from git history if ever needed for re-running.

Today's state to migrate:

| Date | approved.txt | status.txt | After migration |
|---|---|---|---|
| 260325 | absent | `3:published` | `3:published` |
| 260326 | absent | `1:aborted`, `3:aborted`, `7:published`, `10:published` | `1:abort`, `3:abort`, `7:published`, `10:published` |
| 260501 | absent | `2:aborted`, `3:aborted`, `5:aborted` | `2:abort`, `3:abort`, `5:abort` |
| 260503 | absent | `1:published`, `2:aborted`, `4:aborted`, `3:published` | `1:published`, `2:abort`, `3:published`, `4:abort` |
| 260504 | `1`, `3`, `5`, `6`, `7` | absent | `1:selected`, `3:selected`, `5:selected`, `6:selected`, `7:selected` |

## Code touchpoints

| File | Change |
|---|---|
| `src/utils/pipeline.py` | Add `record_selected`, `record_aborted`, `record_published` (moved from publisher), `_post_slug` (moved from publisher), `event_status`, `event_statuses`. Remove `approved_path`. |
| `src/publisher.py` | Import `record_published` and `_post_slug` from `utils.pipeline`. Remove local definitions. |
| `src/tracker.py` | No change. |
| `_pipeline/events/*-status.txt` | Migrated by script. |
| `_pipeline/events/*-approved.txt` | Deleted by script. |
| `.claude/skills/blog-orchestrator/SKILL.md` | 1c: replace `approved_path(...).write_text(...)` with a loop calling `record_selected(date, n)` for each approved index. "Filter terminal events" subsection: update to call `event_statuses(date_str)` and filter where state in `{abort, published}`. Update the state-name reference (now `abort`, not `aborted`). |
| `CLAUDE.md` | Pipeline Overview file tree: remove `events/YYMMDD-approved.txt` line, expand `events/YYMMDD-status.txt` description to list the 7-state model. |
| `src/tests/test_publisher_status.py` | Rename `:aborted` → `:abort` in fixtures and `match=` regexes. Tests for `record_published` stay valid (moved import path). |
| `src/tests/test_pipeline_status.py` (new) | TDD tests for `record_selected`, `record_aborted`, `event_status`, `event_statuses`. |

## Testing

Unit tests (in `src/tests/test_pipeline_status.py`):

For `record_selected`:
- Creates file with `n:selected` if sidecar absent.
- Idempotent if `n:selected` already present.
- Raises `RuntimeError` if `n:published` already present.
- Raises `RuntimeError` if `n:abort` already present.
- Overwrites file with sorted single-line-per-event when other events exist.

For `record_aborted`:
- Creates file with `n:abort` if sidecar absent.
- Idempotent if `n:abort` already present.
- Raises `RuntimeError` if `n:published` already present.
- Overwrites `n:selected` → `n:abort` cleanly.

For `event_status`:
- Returns `candidate` when events file lists `n` and sidecar is absent.
- Returns `selected` when sidecar has `n:selected` and no derived files exist.
- Returns `researched` when only the research file exists.
- Returns `drafted` when draft file exists (precedence over research).
- Returns `reviewed` when review file exists (precedence over draft).
- Returns `published` when sidecar says published, even if review files exist.
- Returns `abort` when sidecar says abort, even if all derived files exist.

For `event_statuses`:
- Returns `{n: state}` for every index parsed from the events file.
- Returns `{}` if events file is missing.

Existing `src/tests/test_publisher_status.py` tests pass after rename `aborted` → `abort`, plus the import path moves from `src.publisher` to `src.utils.pipeline`.

Migration script: tested by running it against the live `_pipeline/events/` directory and asserting the migrated files match the expected outputs above.

## Out of scope

- Enriching `pipeline_summary()` with per-event status counts. Useful follow-up but separate change.
- A standalone CLI to query state (`python src/status.py 260326`). `event_statuses()` is enough for the orchestrator; users can write a one-liner if needed.
- Storing transition history (when did this event move from `selected` to `published`?). Git log on the sidecar is sufficient.
- Renaming `abort` to `aborted` or vice versa across the codebase beyond what's documented here. (We're already changing the stored token from `aborted` to `abort` once, here. No further bikeshedding.)
