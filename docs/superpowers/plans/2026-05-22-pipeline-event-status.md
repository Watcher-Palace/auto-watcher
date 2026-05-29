# Pipeline Event Terminal Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-event terminal status (`published`/`aborted`) recorded in sidecar files so the orchestrator stops resurfacing finished events and status checks stay accurate.

**Architecture:** One sidecar `_pipeline/events/YYMMDD-status.txt` per tracked date. Lines `N:published` / `N:aborted`. Publisher appends idempotently on successful publish. Orchestrator skips listed events. Non-terminal stages remain inferable from existing file presence.

**Tech Stack:** Python 3 stdlib (`pathlib`), pytest, plain-text data files. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-22-pipeline-event-status-design.md`

---

## File Structure

- Create: `_pipeline/events/260325-status.txt` — backfill
- Create: `_pipeline/events/260326-status.txt` — backfill
- Create: `_pipeline/events/260501-status.txt` — backfill
- Create: `_pipeline/events/260503-status.txt` — backfill
- Modify: `src/publisher.py` — add `record_published(date_str, n)` helper and call it at the end of `publish()`
- Create: `src/tests/test_publisher_status.py` — tests for the new helper
- Modify: `/home/jc/.claude/skills/blog-orchestrator/SKILL.md` — teach the orchestrator to consult sidecars
- Modify: `CLAUDE.md` — document sidecar in the Pipeline Overview file tree

---

### Task 1: Backfill the four sidecar files

**Files:**
- Create: `_pipeline/events/260325-status.txt`
- Create: `_pipeline/events/260326-status.txt`
- Create: `_pipeline/events/260501-status.txt`
- Create: `_pipeline/events/260503-status.txt`

- [ ] **Step 1: Write the four files**

`_pipeline/events/260325-status.txt`:
```
3:published
```

`_pipeline/events/260326-status.txt`:
```
1:aborted
7:published
```

`_pipeline/events/260501-status.txt`:
```
2:aborted
```

`_pipeline/events/260503-status.txt`:
```
1:published
4:aborted
```

- [ ] **Step 2: Verify**

Run: `cat _pipeline/events/26{0325,0326,0501,0503}-status.txt`
Expected: the four bodies above printed in order, no errors.

- [ ] **Step 3: Commit**

```bash
git add _pipeline/events/260325-status.txt _pipeline/events/260326-status.txt _pipeline/events/260501-status.txt _pipeline/events/260503-status.txt
git commit -m "feat(pipeline): backfill terminal status sidecars for 0325/0326/0501/0503"
```

---

### Task 2: Add `record_published` helper to `publisher.py` (TDD)

The helper is the only piece of real logic in this change, so it gets TDD. It must: create the file if missing, append `N:published` if not already present, no-op on duplicate, raise if the same `N` is already recorded as `aborted`.

**Files:**
- Modify: `src/publisher.py` — add `record_published(date_str, n, pipeline_dir=PIPELINE)` near `move_assets`
- Create: `src/tests/test_publisher_status.py`

- [ ] **Step 1: Write the failing tests**

Create `src/tests/test_publisher_status.py`:

```python
import pytest
from pathlib import Path

from src.publisher import record_published


def _events_dir(tmp_path: Path) -> Path:
    d = tmp_path / "events"
    d.mkdir()
    return d


def test_creates_file_if_missing(tmp_path):
    pipeline = tmp_path
    _events_dir(tmp_path)
    record_published("260326", 3, pipeline_dir=pipeline)
    assert (pipeline / "events" / "260326-status.txt").read_text() == "3:published\n"


def test_appends_to_existing_file(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("1:aborted\n")
    record_published("260326", 7, pipeline_dir=pipeline)
    assert (events / "260326-status.txt").read_text() == "1:aborted\n7:published\n"


def test_idempotent_on_duplicate_published(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("3:published\n")
    record_published("260326", 3, pipeline_dir=pipeline)
    # No duplicate line written.
    assert (events / "260326-status.txt").read_text() == "3:published\n"


def test_raises_if_already_aborted(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("1:aborted\n")
    with pytest.raises(RuntimeError, match="aborted"):
        record_published("260326", 1, pipeline_dir=pipeline)


def test_ignores_blank_and_comment_lines(tmp_path):
    pipeline = tmp_path
    events = _events_dir(tmp_path)
    (events / "260326-status.txt").write_text("# notes\n\n3:published\n")
    record_published("260326", 3, pipeline_dir=pipeline)
    assert (events / "260326-status.txt").read_text() == "# notes\n\n3:published\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src && python -m pytest tests/test_publisher_status.py -v`
Expected: FAIL — `cannot import name 'record_published' from 'src.publisher'`.

- [ ] **Step 3: Implement `record_published`**

In `src/publisher.py`, after the `move_assets` function (around line 50), add:

```python
def record_published(date_str: str, n: int, pipeline_dir: Path = PIPELINE) -> None:
    status_path = pipeline_dir / "events" / f"{date_str}-status.txt"
    existing = {}
    if status_path.exists():
        for raw in status_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            idx_str, _, state = line.partition(":")
            if not state:
                raise RuntimeError(f"Malformed status line in {status_path}: {raw!r}")
            existing[int(idx_str)] = state
    prior = existing.get(n)
    if prior == "published":
        return
    if prior == "aborted":
        raise RuntimeError(
            f"Event {date_str}-{n} is already marked aborted in {status_path}; "
            "edit the sidecar by hand if you really mean to publish it."
        )
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{n}:published\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src && python -m pytest tests/test_publisher_status.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full publisher suite to confirm no regressions**

Run: `cd src && python -m pytest tests/test_publisher.py tests/test_publisher_status.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/publisher.py src/tests/test_publisher_status.py
git commit -m "feat(publisher): add record_published sidecar helper"
```

---

### Task 3: Call `record_published` from `publish()`

**Files:**
- Modify: `src/publisher.py` — add the call at the end of `publish()` (currently around line 128, after the deploy block)

- [ ] **Step 1: Edit `publish()`**

In `src/publisher.py`, at the end of `publish()` (after the `if deploy:` block, before the function returns), add:

```python
    record_published(date_str, n)
    print(f"Recorded {date_str}-{n} as published in events sidecar")
```

This runs whether `deploy=True` or not — the file is on disk in `source/_posts/` either way, which is the definition of "published" for this repo.

- [ ] **Step 2: Smoke-test against a real already-published event**

Run:
```bash
python -c "
from pathlib import Path
from src.publisher import record_published
record_published('260326', 7)
print(open('_pipeline/events/260326-status.txt').read())
"
```
Expected: file contents unchanged from Task 1 (still `1:aborted\n7:published\n`) — idempotency confirmed end-to-end.

- [ ] **Step 3: Commit**

```bash
git add src/publisher.py
git commit -m "feat(publisher): record sidecar status after publish"
```

---

### Task 4: Teach `blog-orchestrator` skill to skip terminal events

**Files:**
- Modify: `/home/jc/.claude/skills/blog-orchestrator/SKILL.md`

- [ ] **Step 1: Locate the section that surfaces actionable events per date**

Run: `grep -n -E "actionable|stage|events/" /home/jc/.claude/skills/blog-orchestrator/SKILL.md`
Read the surrounding context to find the right insertion point. The skill walks dates and per-event stages — the skip step belongs immediately after loading events for a date, before deciding what stage each one is in.

- [ ] **Step 2: Add the terminal-status step**

Insert a new subsection (heading depth matching the surrounding skill structure) titled "Skip terminal events" with this body:

````markdown
For each date being considered, read `_pipeline/events/YYMMDD-status.txt` if it exists. Each non-blank, non-`#` line is `N:state` where state is `published` or `aborted`. Skip those event indexes — they are terminal and should not appear in the actionable list or be re-dispatched to research/write/review.

Example:

```
$ cat _pipeline/events/260326-status.txt
1:aborted
7:published
```

→ For 260326, skip events 1 and 7. Continue evaluating the others against file presence in `research/`, `draft/`, `review/`.
````

- [ ] **Step 3: Sanity-check the skill still parses**

Run: `head -20 /home/jc/.claude/skills/blog-orchestrator/SKILL.md`
Expected: frontmatter intact (`---` block with `name:` and `description:`), no accidental edits to the header.

- [ ] **Step 4: Commit**

```bash
cd /home/jc/.claude/skills/blog-orchestrator && git add SKILL.md && git commit -m "feat(blog-orchestrator): skip events marked published/aborted in sidecar" 2>/dev/null || echo "skills dir not a git repo — skip commit, edit is in place"
```

(The user's `~/.claude/skills/` directory may or may not be under version control. If not, the edit-in-place is the deliverable.)

---

### Task 5: Document the sidecar in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` — Pipeline Overview file tree

- [ ] **Step 1: Edit the file tree**

In `CLAUDE.md`, find the Pipeline Overview block:

```
_pipeline/
  events/YYMMDD.md           # Stage 1: tracked Weibo events (one per date)
  events/YYMMDD-approved.txt # line-separated approved event indexes (e.g. "1\n3")
```

Add a new line directly below the `approved.txt` line:

```
  events/YYMMDD-status.txt   # per-date terminal status, one "N:published" / "N:aborted" per line
```

- [ ] **Step 2: Verify it lands in the right block**

Run: `grep -n -E "events/YYMMDD" CLAUDE.md`
Expected: three lines for `events/YYMMDD.md`, `events/YYMMDD-approved.txt`, `events/YYMMDD-status.txt` — in that order, contiguous.

- [ ] **Step 3: Commit (bundle with any other CLAUDE.md changes from this PR)**

```bash
git add CLAUDE.md
git commit -m "docs: document YYMMDD-status.txt sidecar in pipeline overview"
```

---

## Final verification

- [ ] Run the full test suite: `cd src && python -m pytest -v` — all pass.
- [ ] `cat _pipeline/events/*-status.txt` — shows the four backfilled files.
- [ ] `grep -n status.txt CLAUDE.md` — finds the new doc line.
- [ ] `grep -n "status.txt\|Skip terminal" /home/jc/.claude/skills/blog-orchestrator/SKILL.md` — finds the new orchestrator step.
