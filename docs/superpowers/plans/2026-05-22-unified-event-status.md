# Unified Event Status Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `_pipeline/events/YYMMDD-approved.txt` and `YYMMDD-status.txt` into one sidecar with full per-event lifecycle state (`candidate`/`selected`/`researched`/`drafted`/`reviewed`/`published`/`abort`).

**Architecture:** The sidecar stores only user decisions (`selected`, `published`, `abort`). Pipeline-stage states (`researched`/`drafted`/`reviewed`) are derived from file presence at read time. `candidate` is the default for any index in `YYMMDD.md` that the sidecar doesn't mention. A reader function (`event_status`) applies precedence rules to merge stored + derived state.

**Tech Stack:** Python 3 stdlib (`pathlib`, `re`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-22-unified-event-status-design.md`

---

## File Structure

- Modify: `src/utils/pipeline.py` — add `record_selected`, `record_aborted`, `event_status`, `event_statuses`; receive moved `record_published` and `_post_slug` from publisher; later remove `approved_path`.
- Modify: `src/publisher.py` — remove `record_published` and `_post_slug` (moved); import them from `utils.pipeline`.
- Create: `src/tests/test_pipeline_status.py` — new home for all sidecar-related tests.
- Delete: `src/tests/test_publisher_status.py` — contents merged into `test_pipeline_status.py`.
- Create then delete (same commit): `src/migrate_status.py` — one-shot migration.
- Modify: `_pipeline/events/*-status.txt` — rewritten by migration; `*-approved.txt` deleted.
- Modify: `.claude/skills/blog-orchestrator/SKILL.md` — 1c writer + Filter terminal subsection.
- Modify: `CLAUDE.md` — Pipeline Overview file tree.

Tests are all in one file (`test_pipeline_status.py`) because all functions tested live in one module (`pipeline.py`). Splitting tests across files would obscure that.

---

### Task 1: TDD `record_selected` and `record_aborted` in `pipeline.py`

**Files:**
- Modify: `src/utils/pipeline.py` — append new helpers near the existing path helpers (after `get_event_titles`, around line 84).
- Create: `src/tests/test_pipeline_status.py`.

- [ ] **Step 1: Write the failing tests**

Create `src/tests/test_pipeline_status.py`:

```python
import pytest
from pathlib import Path

from src.utils.pipeline import record_selected, record_aborted


def _events_dir(tmp_path: Path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    return d


# ---- record_selected ----

def test_record_selected_creates_file_if_missing(tmp_path):
    _events_dir(tmp_path)
    record_selected("260326", 3, pipeline_dir=tmp_path)
    assert (tmp_path / "events" / "260326-status.txt").read_text() == "3:selected\n"


def test_record_selected_idempotent(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:selected\n")
    record_selected("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:selected\n"


def test_record_selected_raises_if_published(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    with pytest.raises(RuntimeError, match="published"):
        record_selected("260326", 3, pipeline_dir=tmp_path)


def test_record_selected_raises_if_abort(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:abort\n")
    with pytest.raises(RuntimeError, match="abort"):
        record_selected("260326", 3, pipeline_dir=tmp_path)


def test_record_selected_keeps_other_events_sorted(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("10:published\n1:abort\n")
    record_selected("260326", 5, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == (
        "1:abort\n5:selected\n10:published\n"
    )


# ---- record_aborted ----

def test_record_aborted_creates_file_if_missing(tmp_path):
    _events_dir(tmp_path)
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (tmp_path / "events" / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_idempotent(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:abort\n")
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_overwrites_selected(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:selected\n")
    record_aborted("260326", 3, pipeline_dir=tmp_path)
    assert (events / "260326-status.txt").read_text() == "3:abort\n"


def test_record_aborted_raises_if_published(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    with pytest.raises(RuntimeError, match="published"):
        record_aborted("260326", 3, pipeline_dir=tmp_path)
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_pipeline_status.py -v`
Expected: `ImportError: cannot import name 'record_selected' from 'src.utils.pipeline'`.

- [ ] **Step 3: Implement both writers**

In `src/utils/pipeline.py`, append after `get_event_titles` (around line 84):

```python
_STORED_STATES = ("selected", "abort", "published")


def _status_path(date_str: str, pipeline_dir: Path) -> Path:
    return pipeline_dir / "events" / f"{date_str}-status.txt"


def _read_status_entries(status_path: Path) -> dict[int, str]:
    if not status_path.exists():
        return {}
    entries: dict[int, str] = {}
    for raw in status_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        idx_str, _, state = line.partition(":")
        if not state:
            raise RuntimeError(f"Malformed status line in {status_path}: {raw!r}")
        if state not in _STORED_STATES:
            raise RuntimeError(
                f"Unknown status value in {status_path}: {raw!r} "
                f"(allowed: {', '.join(_STORED_STATES)})"
            )
        n = int(idx_str)
        if n in entries:
            raise RuntimeError(f"Duplicate event index {n} in {status_path}")
        entries[n] = state
    return entries


def _write_status_entries(status_path: Path, entries: dict[int, str]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{n}:{entries[n]}\n" for n in sorted(entries)]
    status_path.write_text("".join(lines), encoding="utf-8")


def record_selected(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = _status_path(date_str, pipeline_dir)
    entries = _read_status_entries(status_path)
    prior = entries.get(n)
    if prior == "selected":
        return
    if prior == "published":
        raise RuntimeError(
            f"Event {date_str}-{n} is already published in {status_path}; "
            "edit the sidecar by hand if you really mean to revert it."
        )
    if prior == "abort":
        raise RuntimeError(
            f"Event {date_str}-{n} is already marked abort in {status_path}; "
            "edit the sidecar by hand if you really mean to revert it."
        )
    entries[n] = "selected"
    _write_status_entries(status_path, entries)


def record_aborted(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = _status_path(date_str, pipeline_dir)
    entries = _read_status_entries(status_path)
    prior = entries.get(n)
    if prior == "abort":
        return
    if prior == "published":
        raise RuntimeError(
            f"Event {date_str}-{n} is already published in {status_path}; "
            "edit the sidecar by hand if you really mean to abort it."
        )
    entries[n] = "abort"
    _write_status_entries(status_path, entries)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_pipeline_status.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add src/utils/pipeline.py src/tests/test_pipeline_status.py
git commit -m "feat(pipeline): add record_selected and record_aborted sidecar helpers"
```

---

### Task 2: TDD `event_status` and `event_statuses`

**Files:**
- Modify: `src/utils/pipeline.py` — append `event_status` and `event_statuses` after `record_aborted`.
- Modify: `src/tests/test_pipeline_status.py` — add tests.

- [ ] **Step 1: Write the failing tests**

Append to `src/tests/test_pipeline_status.py`:

```python
from src.utils.pipeline import event_status, event_statuses


def _setup_pipeline(tmp_path: Path) -> Path:
    """Create a fake _pipeline structure under tmp_path. Returns pipeline_dir."""
    for sub in ("events", "research", "draft", "review"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _write_events_file(pipeline_dir: Path, date_str: str, indexes: list[int]) -> None:
    body = "\n".join(f"## {i}. 标题{i}\n**Brief**: x" for i in indexes)
    (pipeline_dir / "events" / f"{date_str}.md").write_text(body, encoding="utf-8")


# ---- event_status ----

def test_event_status_candidate_when_unknown(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [1, 3])
    assert event_status("260326", 1, pipeline_dir=pipeline) == "candidate"


def test_event_status_selected_when_sidecar_says_selected(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "selected"


def test_event_status_researched_when_research_file_exists(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "researched"


def test_event_status_drafted_overrides_researched(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "drafted"


def test_event_status_reviewed_overrides_drafted(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "reviewed"


def test_event_status_published_overrides_review_files(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:published\n")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "published"


def test_event_status_abort_overrides_everything(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [3])
    (pipeline / "events" / "260326-status.txt").write_text("3:abort\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    (pipeline / "draft" / "260326-3-标题3-v1.md").write_text("x")
    (pipeline / "review" / "260326-3-标题3-v1.md").write_text("x")
    assert event_status("260326", 3, pipeline_dir=pipeline) == "abort"


# ---- event_statuses ----

def test_event_statuses_returns_all_indexes_from_events_file(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    _write_events_file(pipeline, "260326", [1, 3, 7])
    (pipeline / "events" / "260326-status.txt").write_text("3:selected\n7:published\n")
    (pipeline / "research" / "260326-3-标题3.md").write_text("x")
    result = event_statuses("260326", pipeline_dir=pipeline)
    assert result == {1: "candidate", 3: "researched", 7: "published"}


def test_event_statuses_empty_when_events_file_missing(tmp_path):
    pipeline = _setup_pipeline(tmp_path)
    assert event_statuses("260326", pipeline_dir=pipeline) == {}
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_pipeline_status.py -v`
Expected: ImportError on `event_status`/`event_statuses`.

- [ ] **Step 3: Implement the readers**

In `src/utils/pipeline.py`, append after `record_aborted`:

```python
def event_status(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> str:
    entries = _read_status_entries(_status_path(date_str, pipeline_dir))
    stored = entries.get(n)
    if stored == "abort":
        return "abort"
    if stored == "published":
        return "published"
    if (pipeline_dir / "review").exists() and any(
        (pipeline_dir / "review").glob(f"{date_str}-{n}-*-v*.md")
    ):
        return "reviewed"
    if (pipeline_dir / "draft").exists() and any(
        (pipeline_dir / "draft").glob(f"{date_str}-{n}-*-v*.md")
    ):
        return "drafted"
    if (pipeline_dir / "research").exists() and any(
        (pipeline_dir / "research").glob(f"{date_str}-{n}-*.md")
    ):
        return "researched"
    if stored == "selected":
        return "selected"
    return "candidate"


def event_statuses(date_str: str, pipeline_dir: Path = PIPELINE) -> dict[int, str]:
    events_file = pipeline_dir / "events" / f"{date_str}.md"
    if not events_file.exists():
        return {}
    indexes = []
    for raw in events_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\.\s", raw)
        if m:
            indexes.append(int(m.group(1)))
    return {n: event_status(date_str, n, pipeline_dir=pipeline_dir) for n in indexes}
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_pipeline_status.py -v`
Expected: 18 PASS (9 from Task 1 + 9 new).

- [ ] **Step 5: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add src/utils/pipeline.py src/tests/test_pipeline_status.py
git commit -m "feat(pipeline): add event_status and event_statuses with file-presence precedence"
```

---

### Task 3: Move `record_published` and `_post_slug` from publisher to pipeline, rename `aborted`→`abort`

This task atomically moves the two functions, renames the stored token, updates the publisher imports, merges the old test file's tests into `test_pipeline_status.py`, and deletes `test_publisher_status.py`. All tests pass at the end.

**Files:**
- Modify: `src/utils/pipeline.py` — paste `record_published` and `_post_slug` near other status helpers; rename `aborted` → `abort` in the check.
- Modify: `src/publisher.py` — delete the two local function definitions; add `from src.utils.pipeline import record_published, _post_slug` at the top.
- Modify: `src/tests/test_pipeline_status.py` — append all 11 tests from `test_publisher_status.py`, rewriting import path to `src.utils.pipeline`, renaming `aborted` → `abort` in fixture writes and `match=` regexes, renaming the relevant test (`test_raises_if_already_aborted` → `test_raises_if_already_abort`).
- Delete: `src/tests/test_publisher_status.py`.

- [ ] **Step 1: Move the two functions into `src/utils/pipeline.py`**

Append after `event_statuses`:

```python
def record_published(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = _status_path(date_str, pipeline_dir)
    entries = _read_status_entries(status_path)
    prior = entries.get(n)
    if prior == "published":
        return
    if prior == "abort":
        raise RuntimeError(
            f"Event {date_str}-{n} is already marked abort in {status_path}; "
            "edit the sidecar by hand if you really mean to publish it."
        )
    entries[n] = "published"
    _write_status_entries(status_path, entries)


def _post_slug(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> str:
    entries = _read_status_entries(_status_path(date_str, pipeline_dir))
    for idx, state in entries.items():
        if state == "published" and idx != n:
            return f"{date_str}-{n}"
    return date_str
```

Note: this version of `record_published` uses `_read_status_entries`/`_write_status_entries` (which produce sorted, rewritten files) instead of the old append-only approach. Behavior is equivalent for callers; the file format is now consistent across all writers.

- [ ] **Step 2: Remove the old definitions from `src/publisher.py`**

In `src/publisher.py`:

1. Delete the entire `record_published` function (current lines ~40–61).
2. Delete the entire `_post_slug` function (current lines ~128–138).
3. At the top of the file, add to the existing pipeline import line:

```python
from src.utils.pipeline import REPO_ROOT, PIPELINE, record_published, _post_slug
```

(The existing import is `from src.utils.pipeline import REPO_ROOT, PIPELINE` — extend it.)

- [ ] **Step 3: Migrate the tests**

Open `src/tests/test_publisher_status.py`. Copy each test function body, paste at the end of `src/tests/test_pipeline_status.py`, and edit as you paste:

- Change `from src.publisher import _post_slug, record_published` to `from src.utils.pipeline import _post_slug, record_published` at the top of `test_pipeline_status.py` (or merge with existing imports).
- In test bodies, rewrite every `:aborted\n` literal to `:abort\n`.
- In `pytest.raises(RuntimeError, match="aborted")` patterns, change `match="aborted"` to `match="abort"`.
- Rename `test_raises_if_already_aborted` → `test_raises_if_already_abort`.
- The `test_idempotent_on_duplicate_published` test currently writes `"3:published\n"` and expects the file to be unchanged. With the new rewrite-and-sort behavior, the output is still `"3:published\n"` (one entry, sorted trivially). The assertion stays valid.

The 10 tests to move:
- `test_creates_file_if_missing`
- `test_appends_to_existing_file` → after the rename rewrite, this still tests appending to an existing file with `1:abort` already present
- `test_idempotent_on_duplicate_published`
- `test_raises_if_already_abort` (renamed)
- `test_ignores_blank_and_comment_lines` — this exercises the old append-only behavior of preserving comments. The new rewrite-on-write behavior does NOT preserve comments. **Rewrite this test** to verify the reader still ignores blank/comment lines without erroring (no assertion about file content after write):

```python
def test_reader_ignores_blank_and_comment_lines(tmp_path):
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("# notes\n\n3:published\n")
    # Should not raise on the comment / blank line.
    record_published("260326", 3, pipeline_dir=tmp_path)
    # After write, file is normalized (comments NOT preserved).
    assert (events / "260326-status.txt").read_text() == "3:published\n"
```

- `test_raises_on_unknown_state_value`
- `test_post_slug_no_sidecar_returns_bare`
- `test_post_slug_only_aborts_returns_bare` — rewrite the sidecar fixture: `(events / "260326-status.txt").write_text("1:abort\n3:abort\n")`
- `test_post_slug_other_published_returns_suffixed` — rewrite: `(events / "260503-status.txt").write_text("1:published\n4:abort\n")`
- `test_post_slug_own_published_returns_bare` — rewrite: `(events / "260326-status.txt").write_text("1:abort\n7:published\n")`

- [ ] **Step 4: Delete the old test file**

```bash
rm /home/jc/Projects/auto-watcher/src/tests/test_publisher_status.py
```

- [ ] **Step 5: Run all tests**

```bash
cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/ -v --ignore=tests/test_tracker.py --ignore=tests/utils/test_web.py
```

(The two ignored files require `requests`, which the publisher venv doesn't have — pre-existing env issue, unrelated.)

Expected: all publisher + pipeline_status tests pass. Count: 7 (existing test_publisher.py) + 18 (Tasks 1–2) + 10 (moved + adapted) = 35 PASS.

- [ ] **Step 6: Smoke-test the publisher entry point still imports cleanly**

```bash
cd /home/jc/Projects/auto-watcher && src/venv/bin/python -c "from src.publisher import publish, record_published, _post_slug; print('imports ok')"
```

Expected: `imports ok`.

- [ ] **Step 7: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add src/publisher.py src/utils/pipeline.py src/tests/test_pipeline_status.py
git rm src/tests/test_publisher_status.py
git commit -m "refactor(pipeline): move sidecar helpers from publisher and rename aborted→abort"
```

---

### Task 4: Write `src/migrate_status.py`

**Files:**
- Create: `src/migrate_status.py` — standalone one-shot migration. Will be deleted in Task 5.

- [ ] **Step 1: Write the script**

Create `src/migrate_status.py`:

```python
"""One-shot migration: merge YYMMDD-approved.txt into YYMMDD-status.txt and rename aborted→abort.

Run from repo root: `src/venv/bin/python src/migrate_status.py`

Deleted in the same commit that lands the migrated sidecars.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVENTS_DIR = REPO_ROOT / "_pipeline" / "events"

STORED = ("selected", "abort", "published")
# Precedence for conflict resolution (higher index wins).
PRECEDENCE = {"abort": 3, "published": 2, "selected": 1}


def parse_status_file(path: Path) -> dict[int, str]:
    entries: dict[int, str] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        idx_str, _, state = line.partition(":")
        if not state:
            raise RuntimeError(f"Malformed line in {path}: {raw!r}")
        # Rename legacy token.
        if state == "aborted":
            state = "abort"
        if state not in STORED:
            raise RuntimeError(f"Unknown state {state!r} in {path}: {raw!r}")
        entries[int(idx_str)] = state
    return entries


def parse_approved_file(path: Path) -> list[int]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        out.append(int(line))
    return out


def merge(status_entries: dict[int, str], approved_indexes: list[int]) -> dict[int, str]:
    merged = dict(status_entries)
    for n in approved_indexes:
        existing = merged.get(n)
        if existing is None:
            merged[n] = "selected"
            continue
        # Conflict: prefer the more-advanced state.
        if PRECEDENCE[existing] >= PRECEDENCE["selected"]:
            print(f"  conflict on {n}: keeping {existing!r} over selected")
            continue
        merged[n] = "selected"
    return merged


def write_status(path: Path, entries: dict[int, str]) -> None:
    if not entries:
        if path.exists():
            path.unlink()
        return
    lines = [f"{n}:{entries[n]}\n" for n in sorted(entries)]
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    if not EVENTS_DIR.exists():
        print(f"No events dir at {EVENTS_DIR}", file=sys.stderr)
        return 1
    dates = sorted({p.stem for p in EVENTS_DIR.glob("*.md")})
    print(f"Found {len(dates)} tracked dates: {', '.join(dates)}")
    for date_str in dates:
        status_path = EVENTS_DIR / f"{date_str}-status.txt"
        approved_path = EVENTS_DIR / f"{date_str}-approved.txt"
        if not status_path.exists() and not approved_path.exists():
            continue
        status_entries = parse_status_file(status_path)
        approved_indexes = parse_approved_file(approved_path)
        merged = merge(status_entries, approved_indexes)
        print(f"  {date_str}: {merged}")
        write_status(status_path, merged)
        if approved_path.exists():
            approved_path.unlink()
            print(f"  removed {approved_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit (script only, no migration run yet)**

```bash
cd /home/jc/Projects/auto-watcher
git add src/migrate_status.py
git commit -m "chore: add one-shot migration script for unified sidecar"
```

---

### Task 5: Run the migration and delete the script

**Files:**
- Modify: `_pipeline/events/*-status.txt` — rewritten.
- Delete: `_pipeline/events/*-approved.txt` — all of them.
- Delete: `src/migrate_status.py`.

- [ ] **Step 1: Capture pre-state for verification**

```bash
cd /home/jc/Projects/auto-watcher && ls _pipeline/events/*-status.txt _pipeline/events/*-approved.txt 2>/dev/null
```

Expected pre-state:
```
_pipeline/events/260325-status.txt
_pipeline/events/260326-status.txt
_pipeline/events/260501-status.txt
_pipeline/events/260503-status.txt
_pipeline/events/260504-approved.txt
```

- [ ] **Step 2: Run the migration**

```bash
cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/migrate_status.py
```

Expected output (key lines):
```
Found 12 tracked dates: 260322, 260323, ...
  260325: {3: 'published'}
  260326: {1: 'abort', 3: 'abort', 7: 'published', 10: 'published'}
  260501: {2: 'abort', 3: 'abort', 5: 'abort'}
  260503: {1: 'published', 2: 'abort', 3: 'published', 4: 'abort'}
  260504: {1: 'selected', 3: 'selected', 5: 'selected', 6: 'selected', 7: 'selected'}
  removed 260504-approved.txt
```

- [ ] **Step 3: Verify each migrated file**

```bash
cd /home/jc/Projects/auto-watcher && for f in _pipeline/events/26{0325,0326,0501,0503,0504}-status.txt; do echo "=== $f ==="; cat "$f"; done
```

Expected:
```
=== _pipeline/events/260325-status.txt ===
3:published
=== _pipeline/events/260326-status.txt ===
1:abort
3:abort
7:published
10:published
=== _pipeline/events/260501-status.txt ===
2:abort
3:abort
5:abort
=== _pipeline/events/260503-status.txt ===
1:published
2:abort
3:published
4:abort
=== _pipeline/events/260504-status.txt ===
1:selected
3:selected
5:selected
6:selected
7:selected
```

And `ls _pipeline/events/*-approved.txt` should report no matches.

- [ ] **Step 4: Smoke-test that `event_statuses` reads them all correctly**

```bash
cd /home/jc/Projects/auto-watcher && src/venv/bin/python -c "
from src.utils.pipeline import event_statuses
for d in ('260325', '260326', '260501', '260503', '260504'):
    print(d, event_statuses(d))
"
```

Expected: prints a dict per date. 260326 shows `{1: 'abort', 3: 'abort', 7: 'published', 10: 'published'}`. 260504 shows `{1: 'selected', 2: 'candidate', 3: 'selected', 4: 'candidate', 5: 'selected', 6: 'selected', 7: 'selected'}` (events 2 and 4 surface as `candidate` because they're in the events file but the user didn't approve them).

- [ ] **Step 5: Delete the migration script**

```bash
cd /home/jc/Projects/auto-watcher && rm src/migrate_status.py
```

- [ ] **Step 6: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add _pipeline/events/
git rm src/migrate_status.py
git commit -m "chore(pipeline): migrate sidecars to unified format, delete one-shot script"
```

---

### Task 6: Update the `blog-orchestrator` skill

**Files:**
- Modify: `/home/jc/.claude/skills/blog-orchestrator/SKILL.md` (symlinked into the repo at `.claude/skills/blog-orchestrator/SKILL.md`).

- [ ] **Step 1: Replace the approval writer in section 1c**

Locate the block in `1c. Human gate — Approve events`:

```python
from src.utils.pipeline import approved_path
approved_path(date_str).write_text("\n".join(str(i) for i in approved_indexes) + "\n")
```

Replace with:

```python
from src.utils.pipeline import record_selected
for i in approved_indexes:
    record_selected(date_str, i)
```

- [ ] **Step 2: Update the "Filter terminal events" subsection**

Locate (under `## Stage 2+3+4 — Research → Write → Review loop`):

> Before iterating, read `_pipeline/events/YYMMDD-status.txt` for each date if the file exists. Each non-blank, non-`#` line has the form `N:state` where state is `published` or `aborted`. Remove any matching (date, index) pair from the approved list — these are terminal and must not be re-dispatched.

Rewrite to:

> Before iterating, query `event_statuses(date_str)` from `src.utils.pipeline` for each date. It returns `{index: state}` for every event in the date's events file. Remove any (date, index) where state is `published` or `abort` — these are terminal and must not be re-dispatched. The remaining states (`candidate`, `selected`, `researched`, `drafted`, `reviewed`) all represent in-flight work.
>
> Example:
>
> ```
> >>> event_statuses("260326")
> {1: 'abort', 3: 'abort', 7: 'published', 10: 'published'}
> ```
>
> → For 260326, every event is terminal; nothing to dispatch.

- [ ] **Step 3: Sanity-check the skill still parses**

```bash
head -10 /home/jc/.claude/skills/blog-orchestrator/SKILL.md
```

Expected: frontmatter block (`---` with `name:` and `description:`) intact.

- [ ] **Step 4: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add .claude/skills/blog-orchestrator/SKILL.md
git commit -m "feat(blog-orchestrator): use unified event_statuses and record_selected"
```

---

### Task 7: Remove `approved_path` from `pipeline.py`

Only safe after Task 6 (the skill no longer imports it).

**Files:**
- Modify: `src/utils/pipeline.py` — delete the function.

- [ ] **Step 1: Confirm no callers remain**

```bash
cd /home/jc/Projects/auto-watcher && grep -rn "approved_path" --include="*.py" --include="*.md" .
```

Expected: no matches (or only matches inside docs/superpowers/ — those are spec/plan files and don't import).

- [ ] **Step 2: Delete the function**

In `src/utils/pipeline.py`, remove (currently around lines 15–16):

```python
def approved_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}-approved.txt"
```

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_publisher.py tests/test_pipeline_status.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add src/utils/pipeline.py
git commit -m "refactor(pipeline): remove unused approved_path"
```

---

### Task 8: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` — Pipeline Overview file tree (lines 22–31).

- [ ] **Step 1: Read the current block**

```bash
sed -n '21,32p' /home/jc/Projects/auto-watcher/CLAUDE.md
```

Expected:

```
_pipeline/
  events/YYMMDD.md           # Stage 1: tracked Weibo events (one per date)
  events/YYMMDD-approved.txt # line-separated approved event indexes (e.g. "1\n3")
  events/YYMMDD-status.txt   # per-date terminal status, one "N:published" / "N:aborted" per line
  research/YYMMDD-N-title.md # Stage 2: research output
  draft/YYMMDD-N-title-vN.md # Stage 3: draft post
  draft/YYMMDD-N-assets/     # images for this draft
  review/YYMMDD-N-title-vN.md# Stage 4: review notes
  .state                     # last tracked date (plain text: "20260325")
```

- [ ] **Step 2: Replace the two YYMMDD-... lines**

Replace these two lines:

```
  events/YYMMDD-approved.txt # line-separated approved event indexes (e.g. "1\n3")
  events/YYMMDD-status.txt   # per-date terminal status, one "N:published" / "N:aborted" per line
```

With one line:

```
  events/YYMMDD-status.txt   # per-event status, "N:selected" / "N:abort" / "N:published" (one per line). researched/drafted/reviewed/candidate are derived from file presence.
```

- [ ] **Step 3: Verify**

```bash
grep -n -E "events/YYMMDD" /home/jc/Projects/auto-watcher/CLAUDE.md
```

Expected: two lines — `events/YYMMDD.md` and `events/YYMMDD-status.txt`. No `approved.txt` line.

- [ ] **Step 4: Commit (this PR's CLAUDE.md changes only)**

If there are other unrelated uncommitted CLAUDE.md changes from prior work, stash them, commit the status-format edit alone, then pop:

```bash
cd /home/jc/Projects/auto-watcher
git stash push CLAUDE.md   # only if pre-existing edits present
# (make the edit per Steps 1–3)
git add CLAUDE.md && git commit -m "docs: document unified event status format and 7-state model"
git stash pop              # only if stashed above
```

If no pre-existing changes, the stash dance is unnecessary — just `git add` and commit.

---

## Final verification

- [ ] All pytest passes: `cd /home/jc/Projects/auto-watcher/src && ./venv/bin/python -m pytest tests/test_publisher.py tests/test_pipeline_status.py -v` — 36 tests.
- [ ] `event_statuses` spot-check: `src/venv/bin/python -c "from src.utils.pipeline import event_statuses; print(event_statuses('260504'))"` returns `{1: 'selected', 2: 'candidate', 3: 'selected', 4: 'candidate', 5: 'researched', 6: 'researched', 7: 'researched'}` (events 5/6/7 should be `researched` because the prior research subagents wrote their files; events 1/3 should also be `researched` for the same reason — verify against actual disk state).
- [ ] No `approved.txt` remains: `ls _pipeline/events/*-approved.txt 2>&1` → "No such file or directory".
- [ ] No `approved_path` in code: `grep -rn "approved_path" --include="*.py" src/`.
- [ ] Migration script deleted: `ls src/migrate_status.py 2>&1` → not found.
- [ ] CLAUDE.md mentions the 7-state model: `grep -n "candidate\|selected.*abort.*published" CLAUDE.md`.
