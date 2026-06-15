# Pipeline Archive — Design

**Date:** 2026-06-15
**Status:** Approved (design)

## Problem

`_pipeline/` holds the full working footprint of every tracked date — events,
research, drafts, reviews — across the entire history of the blog (~66 event
dates, ~250 tracked files at time of writing). Completed dates (every event
published or aborted) stay mixed in with in-flight work, so the active stage
dirs grow without bound and it gets harder to see what is actually in progress.

We want to split the pipeline into two areas:

- `_pipeline/` — **active** work only (dates still moving through the pipeline).
- `_pipeline_archive/` — **completed** dates (all events terminal).

Files move from active to archive automatically when a date becomes fully
terminal.

## Definitions

- **Terminal event** — an event whose status is `published` or `abort`
  (the existing terminal states in `src/utils/pipeline.py`).
- **Terminal / done date** — a date for which *every* event listed in
  `events/{date}.md` is terminal. This is exactly the criterion already used
  for `done-dates.txt`.

## Layout

`_pipeline_archive/` mirrors the active stage dirs:

```
_pipeline/                  # ACTIVE: dates still in flight
  events/  research/  draft/  review/
  done-dates.txt   .state   summary/   category-tag-heatmap.csv
_pipeline_archive/          # COMPLETED: fully-terminal dates
  events/  research/  draft/  review/
```

What moves into the archive, per archived date `{date}`:

- `events/{date}.md`
- `events/{date}-status.txt`
- every `research/{date}-*` entry
- every `draft/{date}-*` entry (the `-vN.md` drafts **and** any leftover
  `{date}-N-assets/` directories — published events' assets have already been
  moved to `source/_posts/` by the publisher; aborted events may still have an
  assets dir)
- every `review/{date}-*` entry

What stays in `_pipeline/` (cross-date or summary artifacts, not per-date stage
files): `done-dates.txt`, `.state`, `summary/`, `category-tag-heatmap.csv`,
`.gitkeep`.

## Trigger (Approach A — code-driven at terminal transitions)

Archiving fires when a date becomes fully terminal:

- **Publish completes a date (the common path):** `publisher.py`, after
  `record_published`, calls `finalize_if_terminal(date_str)`. If that publish
  made the date fully terminal, the date is appended to `done-dates.txt` and its
  files are moved to `_pipeline_archive/`. Fully automatic — no extra step.
- **Abort completes a date:** aborts are not driven by any script (the
  orchestrator records them via `record_aborted`). The orchestrator runs the
  archiver CLI for that date after recording the abort. The CLI is also the
  manual escape hatch.

This auto-move happens *after* the publish human gate (orchestrator step 5a),
so no content advances through a stage without review — archiving is housekeeping
of already-completed work. It does not bypass any human gate.

## Components

### `src/utils/pipeline.py` (additions)

```python
ARCHIVE = REPO_ROOT / "_pipeline_archive"
```

- `is_date_terminal(date_str, pipeline_dir=PIPELINE) -> bool`
  - True iff `events/{date}.md` exists and every event in it is `published` or
    `abort`. Reuses `event_statuses`. Returns False if the events file is
    missing (cannot determine) or any event is non-terminal.

- `archive_date(date_str, pipeline_dir=PIPELINE, archive_dir=ARCHIVE) -> list[Path]`
  - Moves the per-date files listed in **Layout** from `pipeline_dir` into the
    mirror subdirs of `archive_dir`, creating archive subdirs as needed.
  - Membership test for a stage dir entry: name `== f"{date}.md"` (events only)
    or `name.startswith(f"{date}-")`. (Dates are a fixed 6 digits followed by
    `.` or `-`, so this cannot collide with another date.)
  - **Idempotent:** if a destination already exists, skip that entry (do not
    clobber, do not error). Safe to re-run.
  - Returns the list of paths actually moved (for logging/printing).

- `finalize_if_terminal(date_str, pipeline_dir=PIPELINE, archive_dir=ARCHIVE) -> bool`
  - If `is_date_terminal`: append `date_str` to `done-dates.txt` when not
    already present, then `archive_date`. Returns True when it did work.
  - If not terminal: no-op, returns False.

`done-dates.txt` append: read existing non-comment date lines into a set; if
`date_str` not present, append a single `{date}\n` line. Preserve the existing
header comment block and existing ordering (append at end — the file is a set,
order is not significant to any consumer).

Helper functions take `pipeline_dir` / `archive_dir` parameters defaulting to
the module constants so tests can point both at `tmp_path` (matching the
existing `event_status*` signatures and the `monkeypatch.setattr(PIPELINE, ...)`
test pattern).

### `src/publisher.py` (change)

After the existing `record_published(date_str, n)` line, add:

```python
if finalize_if_terminal(date_str):
    print(f"Date {date_str} complete → archived to _pipeline_archive/")
```

Import `finalize_if_terminal` alongside the existing `pipeline` imports.

### `src/archiver.py` (new CLI)

```
python src/archiver.py <YYMMDD>     # finalize one date (abort-completes-a-date case, or manual)
python src/archiver.py --backfill   # sweep every date already in done-dates.txt
```

- Single-date mode: call `finalize_if_terminal(date)`; print what moved (or
  "not terminal / nothing to do").
- `--backfill`: read the date entries from `done-dates.txt`, call
  `archive_date` for each (these are known-done; no need to re-check terminal),
  print a per-date summary. Idempotent — running it again is a no-op. Used once
  during rollout to migrate the 24 existing done dates.

## Consumers — verified unaffected

- **Orchestrator pipeline-check** only scans dates **not** in `done-dates.txt`,
  so it never looks in `_pipeline/` for an archived (done) date. Archived status
  files living in `_pipeline_archive/` are therefore fine.
- **`pipeline_summary()`** counts `_pipeline/{research,draft,review}` — after
  archiving it naturally reports active-only counts, which is the desired
  behaviour.
- **`blog-summary`** computes stats over `source/_posts/`, not `_pipeline/`.
- **Landing-page calendar** (`scripts/calendar.js`) reads post frontmatter in
  `source/_posts/`. Hexo build does not read `_pipeline/` at all, so a new
  top-level `_pipeline_archive/` cannot affect the generated site.

## Edge cases / error handling

- **Partial-terminal date:** `finalize_if_terminal` no-ops.
- **Missing events file:** `is_date_terminal` returns False; nothing archived.
- **Re-run / already archived:** `archive_date` skips entries whose destination
  exists; `done-dates.txt` append dedups. Whole flow is idempotent.
- **Already in `done-dates.txt` but files still in active:** backfill (or a
  single-date run) moves the stragglers; the append step is skipped.
- The archiver performs plain `shutil.move`; it does **not** run git. `_pipeline`
  is git-tracked, so git will detect the moves as renames on the next commit.
  Committing the moves is left to the user.

## Git / tracking

`_pipeline_archive/` is a normal tracked directory (not gitignored), same as
`_pipeline/`. No `.gitignore` change needed. A `.gitkeep` is added to each
archive subdir so the structure exists before the first archive.

## Docs to update

- **CLAUDE.md** — Pipeline Overview gains `_pipeline_archive/{events,research,
  draft,review}/`; add a short "Archiving" note (auto on a publish that
  completes a date; `src/archiver.py` CLI for the abort case and `--backfill`);
  update the `done-dates.txt` line to note it is auto-appended by the publisher
  when a publish completes a date.
- **blog-orchestrator SKILL.md** — step 5b notes the publisher auto-archives a
  completed date; the abort handling notes running
  `python src/archiver.py <date>` after recording an abort that completes a date.

## Tests

`src/tests/test_archiver.py` (hermetic; `PIPELINE` and `ARCHIVE` monkeypatched
to `tmp_path` subdirs):

- `is_date_terminal`: all-terminal → True; one non-terminal → False; missing
  events file → False.
- `archive_date`: moves events md + status + research/draft/review entries +
  an assets dir into the mirror subdirs; leaves a non-matching date untouched.
- Idempotency: second `archive_date` call is a no-op and does not error.
- `finalize_if_terminal`: terminal date → appends to `done-dates.txt` (once,
  dedup on re-run) and archives; non-terminal → no-op, returns False.
- `--backfill`: archives every date in a fixture `done-dates.txt`; re-run no-op.

Update `src/tests/` for the publisher: a publish that completes the last event
of a date triggers archiving (and one that does not leaves files in place).

## Rollout

1. Implement `pipeline.py` helpers + `archiver.py` + publisher hook + tests.
2. Create `_pipeline_archive/{events,research,draft,review}/` with `.gitkeep`s.
3. Run `python src/archiver.py --backfill` to migrate the 24 dates currently in
   `done-dates.txt`.
4. Update CLAUDE.md and the orchestrator skill.
5. Run the test suite; commit.

## Out of scope (YAGNI)

- No un-archive / restore command (revise-a-published-post is rare; move by hand
  if ever needed).
- No automatic git commit from the archiver.
- No change to how aborts are recorded (still orchestrator-driven).
- Path-builder helpers (`latest_draft`, `find_research_file`, …) are **not**
  taught to fall back to the archive — once a date is done, its stage files are
  not looked up by the pipeline.
