# Pipeline Event Terminal Status — Design

## Problem

The pipeline tracks per-event progress only by file presence in `_pipeline/{research,draft,review}/`. There is no way to record that a tracked event has reached a terminal state (published or aborted). Two consequences:

1. `blog-orchestrator` resurfaces events that the user has already decided are done or dropped.
2. Status checks ("what's actionable?") cannot distinguish "in flight" from "intentionally terminated."

## Approach

One sidecar file per tracked date: `_pipeline/events/YYMMDD-status.txt`. Each line is `N:<state>` where `N` is the event index from `YYMMDD.md` and `<state>` is `published` or `aborted`. Only terminal states are recorded; non-terminal stages stay inferable from research/draft/review file presence, as today.

Example — `_pipeline/events/260326-status.txt`:
```
1:aborted
7:published
```

## Format rules

- One `N:state` per line. Blank lines and lines starting with `#` are ignored.
- Allowed states: `published`, `aborted`. Any other value is a format error and should be reported, not silently skipped.
- An event index may appear at most once. A duplicate is a format error and readers should raise.
- Missing file = no terminal events for that date. Not an error.

## Consumers

**`src/publisher.py`** — after a successful publish, append `N:published` to `_pipeline/events/YYMMDD-status.txt`. Create the file if missing. The append is idempotent: if `N:published` already present, no write happens (no duplicate line is produced). If `N:aborted` already present, raise an exception and halt — the user is re-publishing something they previously aborted, and that should be an explicit decision (edit the sidecar by hand), not an accident.

**`blog-orchestrator` skill** — when listing actionable events for a date, read the sidecar and skip any event whose index appears with `published` or `aborted`. Document this step explicitly in the skill so future agents apply it.

**Manual status check** — `cat _pipeline/events/*-status.txt` combined with directory listings is sufficient. No new CLI command.

## Backfill (this PR)

Create sidecars for the four dates the user has terminal decisions on:

| File | Contents |
|---|---|
| `260325-status.txt` | `3:published` |
| `260326-status.txt` | `1:aborted`<br>`7:published` |
| `260501-status.txt` | `2:aborted` |
| `260503-status.txt` | `1:published`<br>`4:aborted` |

Other already-published dates without pipeline traces (e.g., 260330, 260502, 260503) are out of scope — they predate the mechanism and the orchestrator only looks at dates with active `_pipeline/` files.

## Out of scope

- A standalone `status` CLI command. Bash + ls is enough until it isn't.
- Non-terminal states in the sidecar (`in-research`, `in-review`, etc.) — file presence already captures these.
- Auto-aborting an event by deleting its `_pipeline/` files. Abort is an explicit user decision recorded in the sidecar.
- Migrating historical published posts to sidecars.

## CLAUDE.md update

Add `events/YYMMDD-status.txt` to the Pipeline Overview file tree with a one-line description: "per-date terminal status (published/aborted), one `N:state` per line."
