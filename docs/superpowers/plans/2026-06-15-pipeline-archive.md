# Pipeline Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `_pipeline/` into active work plus a sibling `_pipeline_archive/`, auto-moving a date's files there when every event for that date becomes terminal (published/abort).

**Architecture:** Add archive helpers to the central `src/utils/pipeline.py` (path constant + terminal check + move + done-dates append + a `finalize_if_terminal` composer). `publisher.py` calls `finalize_if_terminal` after recording a publish, so publishing the last event of a date auto-archives it. A thin `src/archiver.py` CLI covers the abort-completes-a-date case and a one-time `--backfill` of the dates already in `done-dates.txt`.

**Tech Stack:** Python 3, pytest (hermetic, `tmp_path` + `monkeypatch`), `shutil.move`. No new dependencies.

---

## Conventions for this plan

- All commands assume repo root `/home/jc/Projects/auto-watcher` and the venv active:
  ```bash
  cd /home/jc/Projects/auto-watcher
  source src/venv/bin/activate
  ```
- Run a single test file: `python -m pytest src/tests/test_archiver.py -q`
- Run everything: `python -m pytest src/tests/ -q`
- **Style rule (match existing code):** new helpers keep a frozen
  `pipeline_dir=PIPELINE` / `archive_dir=ARCHIVE` default, exactly like the
  existing `record_selected`/`event_status` helpers. Tests **always pass these
  dirs explicitly** (they never rely on monkeypatching a frozen default). This
  is why the publisher wiring test in Task 6 stubs `finalize_if_terminal`
  instead of running it against the real `_pipeline/`.

## File Structure

- **Modify** `src/utils/pipeline.py` — add `ARCHIVE` constant and the archive
  helpers (`_done_dates_path`, `_read_done_dates`, `mark_done`,
  `is_date_terminal`, `archive_date`, `finalize_if_terminal`). This is the
  single home for all pipeline pathing, so the archive logic belongs here.
- **Create** `src/archiver.py` — CLI entry point (single-date finalize +
  `--backfill`), mirroring `publisher.py`'s header/structure.
- **Modify** `src/publisher.py` — call `finalize_if_terminal` after
  `record_published`.
- **Create** `src/tests/test_archiver.py` — all tests for the new helpers and
  the CLI.
- **Modify** `src/tests/test_publisher.py` — one wiring test.
- **Create** `_pipeline_archive/{events,research,draft,review}/.gitkeep` — the
  archive skeleton.
- **Modify** `CLAUDE.md` and `.claude/skills/blog-orchestrator/SKILL.md` — docs.

---

### Task 1: `ARCHIVE` constant + done-dates helpers

**Files:**
- Modify: `src/utils/pipeline.py` (add constant near line 7; add helpers)
- Test: `src/tests/test_archiver.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `src/tests/test_archiver.py`:

```python
import pytest
from pathlib import Path

from src.utils.pipeline import (
    ARCHIVE, REPO_ROOT,
    _read_done_dates, mark_done,
)


# ---- ARCHIVE constant ----

def test_archive_constant_is_sibling_of_pipeline():
    assert ARCHIVE == REPO_ROOT / "_pipeline_archive"


# ---- done-dates helpers ----

def test_read_done_dates_skips_comments_and_blanks(tmp_path):
    (tmp_path / "done-dates.txt").write_text(
        "# header comment\n\n260501\n260502\n", encoding="utf-8"
    )
    assert _read_done_dates(pipeline_dir=tmp_path) == {"260501", "260502"}


def test_read_done_dates_missing_file_is_empty_set(tmp_path):
    assert _read_done_dates(pipeline_dir=tmp_path) == set()


def test_mark_done_appends_new_date(tmp_path):
    (tmp_path / "done-dates.txt").write_text("# header\n260501\n", encoding="utf-8")
    added = mark_done("260502", pipeline_dir=tmp_path)
    assert added is True
    assert (tmp_path / "done-dates.txt").read_text(encoding="utf-8") == (
        "# header\n260501\n260502\n"
    )


def test_mark_done_is_dedup_noop(tmp_path):
    (tmp_path / "done-dates.txt").write_text("# header\n260501\n", encoding="utf-8")
    added = mark_done("260501", pipeline_dir=tmp_path)
    assert added is False
    assert (tmp_path / "done-dates.txt").read_text(encoding="utf-8") == (
        "# header\n260501\n"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: FAIL with `ImportError: cannot import name 'ARCHIVE'` (or `_read_done_dates`).

- [ ] **Step 3: Add the constant and helpers**

In `src/utils/pipeline.py`, add the constant right after the `PIPELINE` line
(currently line 7):

```python
PIPELINE = REPO_ROOT / "_pipeline"
ARCHIVE = REPO_ROOT / "_pipeline_archive"
```

Then add these helpers (place them near the end of the file, after
`record_published`):

```python
def _done_dates_path(pipeline_dir: Path = PIPELINE) -> Path:
    return pipeline_dir / "done-dates.txt"


def _read_done_dates(pipeline_dir: Path = PIPELINE) -> set[str]:
    p = _done_dates_path(pipeline_dir)
    if not p.exists():
        return set()
    dates: set[str] = set()
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            dates.add(line)
    return dates


def mark_done(date_str: str, pipeline_dir: Path = PIPELINE) -> bool:
    """Append date_str to done-dates.txt if not already present.

    Returns True if it was added, False if it was already there.
    """
    if date_str in _read_done_dates(pipeline_dir):
        return False
    with _done_dates_path(pipeline_dir).open("a", encoding="utf-8") as f:
        f.write(f"{date_str}\n")
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/utils/pipeline.py src/tests/test_archiver.py
git commit -m "feat(archive): add ARCHIVE constant and done-dates helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `is_date_terminal`

**Files:**
- Modify: `src/utils/pipeline.py`
- Test: `src/tests/test_archiver.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/tests/test_archiver.py`:

```python
from src.utils.pipeline import is_date_terminal


def _pipeline_with_events(tmp_path: Path, date_str: str, indexes: list[int]) -> Path:
    """Create events/{date}.md with the given event indexes. Returns pipeline root."""
    (tmp_path / "events").mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"## {i}. 标题{i}\n**Brief**: x" for i in indexes)
    (tmp_path / "events" / f"{date_str}.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_is_date_terminal_true_when_all_terminal(tmp_path):
    _pipeline_with_events(tmp_path, "260601", [1, 2])
    (tmp_path / "events" / "260601-status.txt").write_text(
        "1:published\n2:abort\n", encoding="utf-8"
    )
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is True


def test_is_date_terminal_false_when_one_pending(tmp_path):
    _pipeline_with_events(tmp_path, "260601", [1, 2])
    # event 2 has no terminal status → derived state "candidate"
    (tmp_path / "events" / "260601-status.txt").write_text(
        "1:published\n", encoding="utf-8"
    )
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is False


def test_is_date_terminal_false_when_events_file_missing(tmp_path):
    (tmp_path / "events").mkdir(parents=True, exist_ok=True)
    assert is_date_terminal("260601", pipeline_dir=tmp_path) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: FAIL with `ImportError: cannot import name 'is_date_terminal'`.

- [ ] **Step 3: Implement**

In `src/utils/pipeline.py`, add after the `mark_done` helper:

```python
def is_date_terminal(date_str: str, pipeline_dir: Path = PIPELINE) -> bool:
    """True iff every event for date_str is published or abort.

    False if the events file is missing (cannot determine) or any event is
    still non-terminal.
    """
    statuses = event_statuses(date_str, pipeline_dir=pipeline_dir)
    if not statuses:
        return False
    return all(s in ("published", "abort") for s in statuses.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/utils/pipeline.py src/tests/test_archiver.py
git commit -m "feat(archive): add is_date_terminal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `archive_date`

**Files:**
- Modify: `src/utils/pipeline.py` (needs `import shutil` at top — verify/add)
- Test: `src/tests/test_archiver.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/tests/test_archiver.py`:

```python
from src.utils.pipeline import archive_date


def _make(p: Path, name: str, is_dir: bool = False) -> Path:
    """Create a file (or dir with one file) named `name` under directory p."""
    p.mkdir(parents=True, exist_ok=True)
    target = p / name
    if is_dir:
        target.mkdir()
        (target / "img.jpg").write_bytes(b"x")
    else:
        target.write_text("x", encoding="utf-8")
    return target


def _full_pipeline(tmp_path: Path) -> tuple[Path, Path]:
    """Return (pipeline_dir, archive_dir) with empty stage dirs created."""
    root = tmp_path / "_pipeline"
    archive = tmp_path / "_pipeline_archive"
    for sub in ("events", "research", "draft", "review"):
        (root / sub).mkdir(parents=True)
    return root, archive


def test_archive_date_moves_all_per_date_files(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")
    _make(root / "events", "260601-status.txt")
    _make(root / "research", "260601-1-标题.md")
    _make(root / "draft", "260601-1-标题-v1.md")
    _make(root / "draft", "260601-1-assets", is_dir=True)
    _make(root / "review", "260601-1-标题-v1.md")

    moved = archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert len(moved) == 6
    assert (archive / "events" / "260601.md").exists()
    assert (archive / "events" / "260601-status.txt").exists()
    assert (archive / "research" / "260601-1-标题.md").exists()
    assert (archive / "draft" / "260601-1-标题-v1.md").exists()
    assert (archive / "draft" / "260601-1-assets" / "img.jpg").exists()
    assert (archive / "review" / "260601-1-标题-v1.md").exists()
    # originals gone
    assert not (root / "events" / "260601.md").exists()
    assert not (root / "draft" / "260601-1-assets").exists()


def test_archive_date_leaves_other_dates_untouched(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")
    _make(root / "events", "260602.md")
    _make(root / "draft", "260602-1-x-v1.md")

    archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert (root / "events" / "260602.md").exists()
    assert (root / "draft" / "260602-1-x-v1.md").exists()
    assert not (archive / "events" / "260602.md").exists()


def test_archive_date_is_idempotent(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    _make(root / "events", "260601.md")

    first = archive_date("260601", pipeline_dir=root, archive_dir=archive)
    second = archive_date("260601", pipeline_dir=root, archive_dir=archive)

    assert len(first) == 1
    assert second == []  # nothing left to move
    assert (archive / "events" / "260601.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: FAIL with `ImportError: cannot import name 'archive_date'`.

- [ ] **Step 3: Implement**

First confirm `src/utils/pipeline.py` imports `shutil`. The top currently has
`import re`. Add `import shutil` next to it:

```python
import re
import shutil
```

Then add the function after `is_date_terminal`:

```python
_ARCHIVE_STAGES = ("events", "research", "draft", "review")


def archive_date(
    date_str: str,
    pipeline_dir: Path = PIPELINE,
    archive_dir: Path = ARCHIVE,
) -> list[Path]:
    """Move every per-date file for date_str from pipeline_dir into archive_dir.

    Matches `events/{date}.md` and any entry whose name starts with `{date}-`
    in each stage dir (covers `-status.txt`, `-vN.md` drafts, and
    `{date}-N-assets/` directories). Idempotent: skips entries whose
    destination already exists; never clobbers. Returns the destination paths
    actually moved.
    """
    moved: list[Path] = []
    for stage in _ARCHIVE_STAGES:
        src_dir = pipeline_dir / stage
        if not src_dir.exists():
            continue
        for entry in sorted(src_dir.iterdir()):
            name = entry.name
            if not (name == f"{date_str}.md" or name.startswith(f"{date_str}-")):
                continue
            dst_dir = archive_dir / stage
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / name
            if dst.exists():
                continue  # already archived — don't clobber
            shutil.move(str(entry), str(dst))
            moved.append(dst)
    return moved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: PASS (11 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/utils/pipeline.py src/tests/test_archiver.py
git commit -m "feat(archive): add archive_date file mover

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `finalize_if_terminal`

**Files:**
- Modify: `src/utils/pipeline.py`
- Test: `src/tests/test_archiver.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/tests/test_archiver.py`:

```python
from src.utils.pipeline import finalize_if_terminal


def test_finalize_if_terminal_archives_and_marks_done(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n", encoding="utf-8")
    _make(root / "events", "260601.md")
    (root / "events" / "260601.md").write_text(
        "## 1. 标题1\n**Brief**: x", encoding="utf-8"
    )
    (root / "events" / "260601-status.txt").write_text("1:published\n", encoding="utf-8")

    result = finalize_if_terminal("260601", pipeline_dir=root, archive_dir=archive)

    assert result is True
    assert "260601" in _read_done_dates(pipeline_dir=root)
    assert (archive / "events" / "260601.md").exists()
    assert not (root / "events" / "260601.md").exists()


def test_finalize_if_terminal_noop_when_not_terminal(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n", encoding="utf-8")
    (root / "events" / "260601.md").write_text(
        "## 1. 标题1\n## 2. 标题2", encoding="utf-8"
    )
    (root / "events" / "260601-status.txt").write_text("1:published\n", encoding="utf-8")

    result = finalize_if_terminal("260601", pipeline_dir=root, archive_dir=archive)

    assert result is False
    assert "260601" not in _read_done_dates(pipeline_dir=root)
    assert (root / "events" / "260601.md").exists()  # not moved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: FAIL with `ImportError: cannot import name 'finalize_if_terminal'`.

- [ ] **Step 3: Implement**

In `src/utils/pipeline.py`, add after `archive_date`:

```python
def finalize_if_terminal(
    date_str: str,
    pipeline_dir: Path = PIPELINE,
    archive_dir: Path = ARCHIVE,
) -> bool:
    """If date_str is fully terminal, mark it done and archive its files.

    Returns True when it did work, False when the date is not terminal.
    """
    if not is_date_terminal(date_str, pipeline_dir=pipeline_dir):
        return False
    mark_done(date_str, pipeline_dir=pipeline_dir)
    archive_date(date_str, pipeline_dir=pipeline_dir, archive_dir=archive_dir)
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: PASS (13 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/utils/pipeline.py src/tests/test_archiver.py
git commit -m "feat(archive): add finalize_if_terminal composer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `src/archiver.py` CLI

**Files:**
- Create: `src/archiver.py`
- Test: `src/tests/test_archiver.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/tests/test_archiver.py`:

```python
from src import archiver as archiver_mod


def test_backfill_archives_every_done_date(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n260601\n260602\n", encoding="utf-8")
    _make(root / "events", "260601.md")
    _make(root / "events", "260602.md")
    _make(root / "draft", "260603-1-x-v1.md")  # not done → must stay

    archiver_mod.backfill(pipeline_dir=root, archive_dir=archive)

    assert (archive / "events" / "260601.md").exists()
    assert (archive / "events" / "260602.md").exists()
    assert (root / "draft" / "260603-1-x-v1.md").exists()


def test_backfill_is_idempotent(tmp_path):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n260601\n", encoding="utf-8")
    _make(root / "events", "260601.md")

    archiver_mod.backfill(pipeline_dir=root, archive_dir=archive)
    archiver_mod.backfill(pipeline_dir=root, archive_dir=archive)  # must not raise

    assert (archive / "events" / "260601.md").exists()


def test_main_single_date_finalizes(tmp_path, monkeypatch):
    root, archive = _full_pipeline(tmp_path)
    (root / "done-dates.txt").write_text("# header\n", encoding="utf-8")
    (root / "events" / "260601.md").write_text("## 1. 标题1", encoding="utf-8")
    (root / "events" / "260601-status.txt").write_text("1:abort\n", encoding="utf-8")
    monkeypatch.setattr("src.archiver.PIPELINE", root)
    monkeypatch.setattr("src.archiver.ARCHIVE", archive)

    rc = archiver_mod.main(["260601"])

    assert rc == 0
    assert (archive / "events" / "260601.md").exists()


def test_main_no_args_returns_error(capsys):
    rc = archiver_mod.main([])
    assert rc == 1
```

Note: `test_main_single_date_finalizes` monkeypatches `src.archiver.PIPELINE`
and `src.archiver.ARCHIVE` because `main()` resolves them as module globals at
call time (see implementation: `main` reads `PIPELINE`/`ARCHIVE` from the
`src.archiver` namespace and passes them explicitly into `finalize_if_terminal`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.archiver'`.

- [ ] **Step 3: Implement**

Create `src/archiver.py`:

```python
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import (
    PIPELINE, ARCHIVE,
    archive_date, finalize_if_terminal, _read_done_dates,
)


def backfill(pipeline_dir: Path = PIPELINE, archive_dir: Path = ARCHIVE) -> None:
    """Archive every date already listed in done-dates.txt (idempotent)."""
    for d in sorted(_read_done_dates(pipeline_dir)):
        moved = archive_date(d, pipeline_dir=pipeline_dir, archive_dir=archive_dir)
        print(f"{d}: archived {len(moved)} file(s)" if moved
              else f"{d}: nothing to archive")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python src/archiver.py <YYMMDD> | --backfill")
        return 1
    if argv[0] == "--backfill":
        backfill(PIPELINE, ARCHIVE)
        return 0
    date_str = argv[0]
    if finalize_if_terminal(date_str, PIPELINE, ARCHIVE):
        print(f"{date_str}: complete → archived to _pipeline_archive/")
    else:
        print(f"{date_str}: not fully terminal — nothing archived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_archiver.py -q`
Expected: PASS (17 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/archiver.py src/tests/test_archiver.py
git commit -m "feat(archive): add archiver CLI with backfill

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Wire the publisher

**Files:**
- Modify: `src/publisher.py:9` (import) and `src/publisher.py:75-76` (call)
- Test: `src/tests/test_publisher.py`

- [ ] **Step 1: Write the failing test**

Append to `src/tests/test_publisher.py`:

```python
def test_publish_finalizes_terminal_date(tmp_path, monkeypatch):
    root = tmp_path / "_pipeline"
    (root / "draft").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    draft = root / "draft" / "990101-1-测试-v1.md"
    draft.write_text("---\ntitle: 测试\n---\n## 内容\n", encoding="utf-8")

    monkeypatch.setattr("src.publisher.PIPELINE", root)
    monkeypatch.setattr("src.publisher.REPO_ROOT", tmp_path)
    # isolate from the real _pipeline: stub the pipeline-mutating calls
    monkeypatch.setattr("src.publisher._post_slug", lambda d, n: d)
    monkeypatch.setattr("src.publisher.record_published", lambda d, n: None)
    calls = []
    monkeypatch.setattr(
        "src.publisher.finalize_if_terminal",
        lambda d: calls.append(d) or True,
    )

    from src.publisher import publish
    publish("990101", 1, "测试", draft, deploy=False)

    assert calls == ["990101"]
    assert (tmp_path / "source" / "_posts" / "990101.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/tests/test_publisher.py::test_publish_finalizes_terminal_date -v`
Expected: FAIL — `AttributeError: <module 'src.publisher'> does not have the attribute 'finalize_if_terminal'` (the name isn't imported yet).

- [ ] **Step 3: Implement**

Edit `src/publisher.py` line 9 to add the import:

```python
from src.utils.pipeline import (
    REPO_ROOT, PIPELINE, record_published, _post_slug, finalize_if_terminal,
)
```

Then at the end of the `publish()` function (currently lines 75-76, right after
the `record_published` block), add the finalize call:

```python
    record_published(date_str, n)
    print(f"Recorded {date_str}-{n} as published in events sidecar")

    if finalize_if_terminal(date_str):
        print(f"Date {date_str} complete → archived to _pipeline_archive/")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/tests/test_publisher.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/publisher.py src/tests/test_publisher.py
git commit -m "feat(archive): publisher auto-archives a date it completes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Create the archive skeleton + backfill the existing done dates

This task performs the one-time data migration. It has no unit test; verify by
inspecting the filesystem.

**Files:**
- Create: `_pipeline_archive/{events,research,draft,review}/.gitkeep`
- Moves: the 24 dates in `_pipeline/done-dates.txt` into `_pipeline_archive/`

- [ ] **Step 1: Create the archive skeleton**

```bash
cd /home/jc/Projects/auto-watcher
mkdir -p _pipeline_archive/events _pipeline_archive/research _pipeline_archive/draft _pipeline_archive/review
touch _pipeline_archive/events/.gitkeep _pipeline_archive/research/.gitkeep _pipeline_archive/draft/.gitkeep _pipeline_archive/review/.gitkeep
```

- [ ] **Step 2: Record the before-state**

```bash
echo "done dates: $(grep -c '^[0-9]' _pipeline/done-dates.txt)"
echo "active events md: $(ls _pipeline/events/*.md | wc -l)"
```
Expected: 24 done dates; ~32 active event md files. Note these numbers.

- [ ] **Step 3: Run the backfill**

```bash
source src/venv/bin/activate
python src/archiver.py --backfill
```
Expected: one `260321: archived N file(s)` line per done date (24 lines).

- [ ] **Step 4: Verify the migration**

```bash
# A known done date must now live in the archive, not active:
test -f _pipeline_archive/events/260501.md && echo "ARCHIVED ok"
test ! -f _pipeline/events/260501.md && echo "REMOVED from active ok"
# An in-flight date (NOT in done-dates.txt, e.g. 260416) must remain active:
test -f _pipeline/events/260416.md && echo "ACTIVE date retained ok"
```
Expected: all three `ok` lines print. If a done date had no files (already
gone), that is fine — backfill prints `nothing to archive` and skips it.

- [ ] **Step 5: Commit the migration**

```bash
git add -A _pipeline _pipeline_archive
git commit -m "chore(archive): migrate completed dates into _pipeline_archive

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Update docs

**Files:**
- Modify: `CLAUDE.md` (Pipeline Overview block + Known Pitfalls / stage notes)
- Modify: `.claude/skills/blog-orchestrator/SKILL.md` (step 5b + abort handling)

- [ ] **Step 1: Update CLAUDE.md Pipeline Overview**

In `CLAUDE.md`, find the `_pipeline/` tree in the "Pipeline Overview" section.
Add the archive sibling and a done-dates note. Replace the `done-dates.txt`
line and append the archive block so the tree reads:

```
_pipeline/
  events/YYMMDD.md           # Stage 1: tracked Weibo events (one per date)
  events/YYMMDD-status.txt   # per-event status, "N:selected" / "N:abort" / "N:published" (one per line). researched/drafted/reviewed/candidate are derived from file presence.
  research/YYMMDD-N-title.md # Stage 2: research output
  draft/YYMMDD-N-title-vN.md # Stage 3: draft post
  draft/YYMMDD-N-assets/     # images for this draft
  review/YYMMDD-N-title-vN.md# Stage 4: review notes
  summary/YYMM.md            # On-demand monthly summary draft (Stage A; not the regular pipeline)
  .state                     # last tracked date (plain text: "20260325")
  done-dates.txt             # dates where all events are terminal (published/abort). Auto-appended by the publisher when a publish completes a date; for an abort that completes a date, run `python src/archiver.py YYMMDD`.
_pipeline_archive/           # Completed dates moved out of the active pipeline (mirrors events/research/draft/review). Populated automatically; nothing here is part of the active pipeline check.
  events/ research/ draft/ review/
```

- [ ] **Step 2: Add an Archiving note to CLAUDE.md**

Immediately after the `**Pipeline check:**` paragraph in CLAUDE.md, add:

```markdown
**Archiving:** When a date becomes fully terminal (every event published or aborted), its per-date files (events/status/research/draft/review) move to `_pipeline_archive/`. This happens automatically inside `publisher.py` when a publish completes a date. If an **abort** is what completes a date, run `python src/archiver.py YYMMDD` to finalize it. `python src/archiver.py --backfill` archives every date already in `done-dates.txt` (idempotent). Archiving never bypasses a human gate — it only moves already-completed work.
```

- [ ] **Step 3: Update the orchestrator skill**

In `.claude/skills/blog-orchestrator/SKILL.md`, after the step 5b paragraph
(the line ending "...the publisher does not touch it."), add:

```markdown
When a publish completes the last event of a date, the publisher also appends the date to `done-dates.txt` and moves that date's files to `_pipeline_archive/` automatically — no manual step. If instead an **abort** completes a date (no publish runs), finalize it after recording the abort: `python src/archiver.py YYMMDD`.
```

- [ ] **Step 4: Verify docs reference reality**

Run: `grep -n "_pipeline_archive\|archiver.py" CLAUDE.md .claude/skills/blog-orchestrator/SKILL.md`
Expected: matches in both files; the CLI name is `src/archiver.py`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md .claude/skills/blog-orchestrator/SKILL.md
git commit -m "docs(archive): document _pipeline_archive and the archiver CLI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Full suite + final verification

- [ ] **Step 1: Run the whole test suite**

Run: `python -m pytest src/tests/ -q`
Expected: all tests pass (existing suite + new archive tests). If any
pre-existing test broke, fix it before proceeding.

- [ ] **Step 2: Smoke-test the CLI is idempotent against real data**

```bash
python src/archiver.py --backfill
```
Expected: every line says `nothing to archive` (Task 7 already moved them);
no errors, no files move. This confirms idempotency on the live tree.

- [ ] **Step 3: Confirm clean working tree**

Run: `git status --short`
Expected: no unexpected modifications (only intended, already-committed work).
Any leftover changes should be reviewed and committed or reverted.

---

## Self-Review notes (already applied)

- **Spec coverage:** layout (Task 7), `ARCHIVE`/`is_date_terminal`/`archive_date`/
  `finalize_if_terminal`/done-dates helpers (Tasks 1-4), publisher hook (Task 6),
  archiver CLI + `--backfill` (Task 5), one-time migration of the 24 done dates
  (Task 7), docs (Task 8), tests incl. idempotency/partial-terminal/backfill
  (Tasks 1-6), unaffected-consumers — no code change needed, asserted in spec.
- **Type consistency:** function names and signatures
  (`archive_date(date_str, pipeline_dir, archive_dir)`,
  `finalize_if_terminal(date_str, pipeline_dir, archive_dir)`,
  `mark_done(date_str, pipeline_dir)`) are used identically across Tasks 1-6.
- **No placeholders:** every code/test step shows full content; commands have
  expected output.
```
