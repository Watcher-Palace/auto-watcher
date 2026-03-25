# Blog Pipeline Agents & Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full blog automation pipeline as Claude Code skills + Python scripts, leave the old `blog-coordinator` skill untouched.

**Architecture:** Five project-local skills (`blog-orchestrator`, `blog-research`, `blog-write`, `blog-review`, `blog-curate`) live in `.claude/skills/` and are symlinked to `~/.claude/skills/`. Python handles only Weibo fetching (tracker) and final deployment (publisher). All research, writing, and review is done by Claude Code subagents directly.

**Tech Stack:** Python 3.11+, requests, beautifulsoup4, python-dotenv, openai (OpenRouter), pytest, pyyaml; Hexo (pnpm); Claude Code skills (Markdown prompt files)

**Spec:** `docs/superpowers/specs/2026-03-25-blog-pipeline-agents-design.md`

---

## File Map

```
.claude/skills/
  blog-orchestrator/SKILL.md
  blog-research/SKILL.md
  blog-research/notes.md
  blog-write/SKILL.md
  blog-write/notes.md
  blog-review/SKILL.md
  blog-review/notes.md
  blog-curate/SKILL.md

scripts/
  __init__.py
  tracker.py          ← replaces existing (new OpenRouter interface)
  publisher.py        ← replaces existing (adds move_assets)
  config.yaml
  .env.example
  pytest.ini          ← already exists (pythonpath = .., testpaths = tests)
  tests/              ← all tests live here (run: cd scripts && pytest)
    __init__.py
    utils/
      __init__.py
      test_pipeline.py
      test_web.py
    test_tracker.py
    test_publisher.py
  utils/
    __init__.py
    pipeline.py
    web.py
    llm.py            ← new thin OpenRouter wrapper

setup/
  symlink-skills.sh
  venv.sh
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/utils/__init__.py`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/utils/__init__.py`
- Create: `scripts/tests/test_tracker.py` (stub)
- Create: `scripts/tests/test_publisher.py` (stub)
- Create: `scripts/config.yaml`
- Create: `scripts/.env.example`
- Create: `setup/symlink-skills.sh`
- Create: `setup/venv.sh`

- [ ] **Step 1: Create empty `__init__.py` files and directories**

```bash
mkdir -p scripts/utils scripts/tests/utils setup
touch scripts/__init__.py scripts/utils/__init__.py scripts/tests/__init__.py scripts/tests/utils/__init__.py
```

- [ ] **Step 2: Create `scripts/config.yaml`**

```yaml
llm:
  tracker_model: stepfun/step-3.5-flash:free
  tracker_base_url: https://openrouter.ai/api/v1
```

- [ ] **Step 3: Create `scripts/.env.example`**

```
WEIBO_COOKIE=_T_WM=...; ALF=...; SSOloginstate=...; SUB=...; SUBP=...
OPENROUTER_API_KEY=sk-or-...
```

- [ ] **Step 4: Create `setup/venv.sh`**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python3 -m venv scripts/venv
scripts/venv/bin/pip install --upgrade pip
scripts/venv/bin/pip install requests beautifulsoup4 python-dotenv openai pytest pyyaml
echo "Venv ready. Activate with: source scripts/venv/bin/activate"
```

- [ ] **Step 5: Create `setup/symlink-skills.sh`**

```bash
#!/bin/bash
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_SRC="$REPO/.claude/skills"
SKILLS_DST="$HOME/.claude/skills"

mkdir -p "$SKILLS_DST"

for skill_dir in "$SKILLS_SRC"/blog-*/; do
  name="$(basename "$skill_dir")"
  target="$SKILLS_DST/$name"
  if [ -L "$target" ]; then
    echo "Updating symlink: $name"
    ln -sf "$skill_dir" "$target"
  elif [ -e "$target" ]; then
    echo "WARNING: $target exists and is not a symlink — skipping $name"
  else
    echo "Creating symlink: $name"
    ln -s "$skill_dir" "$target"
  fi
done

echo "Done. Skills linked:"
ls -la "$SKILLS_DST" | grep blog-
```

- [ ] **Step 6: Create stub test files** (so pytest discovers them)

`scripts/tests/test_tracker.py`:
```python
# Tests added in Task 5
```

`scripts/tests/test_publisher.py`:
```python
# Tests added in Task 6
```

- [ ] **Step 7: Set up venv and run pytest to confirm zero failures**

```bash
cd /home/jc/Projects/auto-watcher
bash setup/venv.sh
source scripts/venv/bin/activate
cd scripts && pytest -v
```
Expected: `0 passed, 0 failed` (stubs only)

- [ ] **Step 8: Commit**

```bash
git add scripts/ setup/
git commit -m "chore: scaffold scripts, tests, setup"
```

---

## Task 2: `scripts/utils/pipeline.py`

The full pipeline path and state API used by all scripts and referenced by skills.
Includes all functions already imported by the existing `tracker.py`, `writer.py`, `reviewer.py`, and `publisher.py`.

**Files:**
- Create: `scripts/tests/utils/test_pipeline.py`
- Create: `scripts/utils/pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/utils/test_pipeline.py`:

```python
import pytest
from pathlib import Path
from datetime import date, timedelta

from scripts.utils.pipeline import (
    events_path, approved_path, research_path,
    next_draft_path, latest_draft, latest_review,
    review_path, next_review_path,
    get_event_titles, find_research_file,
    get_state, set_state, set_last_tracked_date,
    get_untracked_dates, pipeline_summary,
)

REPO = Path(__file__).parent.parent.parent.parent  # scripts/tests/utils/ → repo root


def test_events_path():
    p = events_path("260325")
    assert p == REPO / "_pipeline" / "events" / "260325.md"


def test_approved_path():
    p = approved_path("260325")
    assert p == REPO / "_pipeline" / "events" / "260325-approved.txt"


def test_research_path():
    p = research_path("260325", 1, "兰州铁路 女性事件")
    assert p.name == "260325-1-兰州铁路 女性事件.md"
    assert p.parent == REPO / "_pipeline" / "research"


def test_next_draft_path_initial(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "draft").mkdir(parents=True)
    path, v = next_draft_path("260325", 1, "兰州铁路 女性事件")
    assert v == 1
    assert path.name == "260325-1-兰州铁路 女性事件-v1.md"


def test_next_draft_path_increments(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    draft_dir = tmp_path / "_pipeline" / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "260325-1-兰州铁路 女性事件-v1.md").touch()
    path, v = next_draft_path("260325", 1, "兰州铁路 女性事件")
    assert v == 2
    assert path.name == "260325-1-兰州铁路 女性事件-v2.md"


def test_latest_draft_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "draft").mkdir(parents=True)
    assert latest_draft("260325", 1) is None


def test_latest_draft_returns_highest_version(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    d = tmp_path / "_pipeline" / "draft"
    d.mkdir(parents=True)
    (d / "260325-1-测试-v1.md").touch()
    (d / "260325-1-测试-v2.md").touch()
    path, v = latest_draft("260325", 1)
    assert v == 2
    assert "v2" in path.name


def test_review_path():
    p = review_path("260325", 1, "兰州铁路 女性事件", 2)
    assert p.name == "260325-1-兰州铁路 女性事件-v2.md"
    assert p.parent == REPO / "_pipeline" / "review"


def test_pipeline_summary_missing_subdirs(tmp_path, monkeypatch):
    # On first run, pipeline subdirs don't exist yet — must not crash
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr("scripts.utils.pipeline.STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    # research/, draft/, review/ intentionally absent
    result = pipeline_summary()
    assert isinstance(result, str)


def test_get_state_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.STATE_FILE", tmp_path / ".state")
    assert get_state() is None


def test_get_state_reads_date(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    state.write_text("20260325\n")
    monkeypatch.setattr("scripts.utils.pipeline.STATE_FILE", state)
    assert get_state() == "20260325"


def test_set_state_writes(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    monkeypatch.setattr("scripts.utils.pipeline.STATE_FILE", state)
    set_state("20260325")
    assert state.read_text().strip() == "20260325"


def test_set_last_tracked_date(tmp_path, monkeypatch):
    state = tmp_path / ".state"
    monkeypatch.setattr("scripts.utils.pipeline.STATE_FILE", state)
    set_last_tracked_date(date(2026, 3, 25))
    assert state.read_text().strip() == "20260325"


def test_get_untracked_dates_returns_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    dates = get_untracked_dates(days=3)
    assert len(dates) == 3


def test_get_untracked_dates_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    events_dir = tmp_path / "_pipeline" / "events"
    events_dir.mkdir(parents=True)
    yesterday = (date.today() - timedelta(days=1)).strftime("%y%m%d")
    (events_dir / f"{yesterday}.md").touch()
    dates = get_untracked_dates(days=3)
    assert yesterday not in dates


def test_get_event_titles_parses_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    events_dir = tmp_path / "_pipeline" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "260325.md").write_text(
        "# Events\n\n## 1. 测试事件\n**Brief**: 描述\n\n## 2. 另一事件\n**Brief**: 描述2\n"
    )
    titles = get_event_titles("260325")
    assert titles[1] == "测试事件"
    assert titles[2] == "另一事件"


def test_find_research_file_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "research").mkdir(parents=True)
    assert find_research_file("260325", 1) is None


def test_find_research_file_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    d = tmp_path / "_pipeline" / "research"
    d.mkdir(parents=True)
    f = d / "260325-1-测试.md"
    f.touch()
    assert find_research_file("260325", 1) == f
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/utils/test_pipeline.py -v
```
Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Implement `scripts/utils/pipeline.py`**

```python
from __future__ import annotations
import re
from pathlib import Path
from datetime import date, timedelta

REPO_ROOT = Path(__file__).parent.parent.parent
PIPELINE = REPO_ROOT / "_pipeline"
STATE_FILE = PIPELINE / ".state"


def events_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}.md"


def approved_path(date_str: str) -> Path:
    return PIPELINE / "events" / f"{date_str}-approved.txt"


def research_path(date_str: str, n: int, title: str) -> Path:
    return PIPELINE / "research" / f"{date_str}-{n}-{title}.md"


def find_research_file(date_str: str, n: int) -> Path | None:
    d = PIPELINE / "research"
    if not d.exists():
        return None
    matches = list(d.glob(f"{date_str}-{n}-*.md"))
    return matches[0] if matches else None


def next_draft_path(date_str: str, n: int, title: str) -> tuple[Path, int]:
    # Raw title — matches existing file convention (e.g. 260325-1-兰州铁路…-v1.md)
    existing = sorted((PIPELINE / "draft").glob(f"{date_str}-{n}-{title}-v*.md"))
    v = len(existing) + 1
    return PIPELINE / "draft" / f"{date_str}-{n}-{title}-v{v}.md", v


def latest_draft(date_str: str, n: int) -> tuple[Path, int] | None:
    d = PIPELINE / "draft"
    if not d.exists():
        return None
    matches = sorted(d.glob(f"{date_str}-{n}-*-v*.md"))
    if not matches:
        return None
    p = matches[-1]
    v = int(p.stem.rsplit("-v", 1)[-1])
    return p, v


def review_path(date_str: str, n: int, title: str, v: int) -> Path:
    return PIPELINE / "review" / f"{date_str}-{n}-{title}-v{v}.md"


def next_review_path(date_str: str, n: int) -> tuple[Path, int] | None:
    draft = latest_draft(date_str, n)
    if not draft:
        return None
    draft_path, v = draft
    title = draft_path.stem.rsplit("-v", 1)[0].split(f"{date_str}-{n}-", 1)[-1]
    return PIPELINE / "review" / f"{date_str}-{n}-{title}-v{v}.md", v


def latest_review(date_str: str, n: int) -> tuple[Path, int] | None:
    d = PIPELINE / "review"
    if not d.exists():
        return None
    matches = sorted(d.glob(f"{date_str}-{n}-*-v*.md"))
    if not matches:
        return None
    p = matches[-1]
    v = int(p.stem.rsplit("-v", 1)[-1])
    return p, v


def get_event_titles(date_str: str) -> dict[int, str]:
    p = events_path(date_str)
    if not p.exists():
        return {}
    content = p.read_text(encoding="utf-8")
    titles = {}
    for m in re.finditer(r'^## (\d+)\. (.+)$', content, re.MULTILINE):
        titles[int(m.group(1))] = m.group(2).strip()
    return titles


def get_state() -> str | None:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip() or None
    return None


def set_state(date_yyyymmdd: str) -> None:
    STATE_FILE.write_text(date_yyyymmdd + "\n")


def set_last_tracked_date(d: date) -> None:
    set_state(d.strftime("%Y%m%d"))


def get_untracked_dates(days: int = 7) -> list[str]:
    today = date.today()
    result = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        yymmdd = d.strftime("%y%m%d")
        if not events_path(yymmdd).exists():
            result.append(yymmdd)
    return result


def pipeline_summary() -> str:
    state = get_state()
    untracked = get_untracked_dates()
    lines = [f"Last tracked: {state or 'never'}"]
    if untracked:
        lines.append(f"Untracked dates (last 7 days): {', '.join(untracked)}")
    else:
        lines.append("All dates tracked (last 7 days)")

    def _count(subdir: str) -> int:
        d = PIPELINE / subdir
        return len(list(d.glob("*.md"))) if d.exists() else 0

    lines.append(
        f"Pipeline: {_count('research')} research, "
        f"{_count('draft')} drafts, {_count('review')} reviews"
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/utils/test_pipeline.py -v
```
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/pipeline.py scripts/tests/utils/test_pipeline.py
git commit -m "feat: add pipeline path utilities and state management"
```

---

## Task 3: `scripts/utils/web.py`

**Files:**
- Create: `scripts/tests/utils/test_web.py`
- Create: `scripts/utils/web.py`

- [ ] **Step 1: Write failing tests**

Create `scripts/tests/utils/test_web.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from scripts.utils.web import WebClient, WEIBO_UA


def test_extract_text_strips_tags():
    html = "<p>Hello <b>world</b></p>"
    assert WebClient.extract_text(html) == "Hello world"


def test_extract_text_handles_empty():
    assert WebClient.extract_text("") == ""


def test_webclient_sets_ua():
    client = WebClient()
    assert WEIBO_UA in client.session.headers["User-Agent"]


def test_webclient_sets_referer():
    client = WebClient()
    assert client.session.headers.get("Referer") == "https://m.weibo.cn/"


def test_webclient_sets_cookie():
    client = WebClient(cookie="SUB=abc")
    assert client.session.headers.get("Cookie") == "SUB=abc"


def test_webclient_fetch_returns_text():
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.text = "hello"
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        result = client.fetch("https://example.com")
    assert result == "hello"
    mock_get.assert_called_once_with("https://example.com", timeout=10)


def test_webclient_fetch_raises_fetch_error_on_http_error():
    import requests
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
    with patch.object(client.session, "get", return_value=mock_resp):
        with pytest.raises(WebClient.FetchError):
            client.fetch("https://example.com")


def test_webclient_fetch_json_parses():
    client = WebClient()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client.session, "get", return_value=mock_resp):
        result = client.fetch_json("https://example.com")
    assert result == {"ok": True}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/utils/test_web.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `scripts/utils/web.py`**

```python
from __future__ import annotations
import requests
from bs4 import BeautifulSoup

WEIBO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class WebClient:
    class FetchError(Exception):
        pass

    def __init__(self, cookie: str | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": WEIBO_UA,
            "Referer": "https://m.weibo.cn/",
        })
        if cookie:
            self.session.headers["Cookie"] = cookie

    def fetch(self, url: str, timeout: int = 10) -> str:
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            raise WebClient.FetchError(str(e)) from e

    def fetch_json(self, url: str, timeout: int = 10) -> dict:
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise WebClient.FetchError(str(e)) from e

    @staticmethod
    def extract_text(html: str) -> str:
        return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/utils/test_web.py -v
```
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/web.py scripts/tests/utils/test_web.py
git commit -m "feat: add WebClient for Weibo fetch"
```

---

## Task 4: `scripts/utils/llm.py`

Thin OpenRouter wrapper with the same `simple(system, user)` interface used by the existing scripts (`tracker.py`, `researcher.py`, etc.). No test file — it's a pure API wrapper; exercised by tracker's integration test in Task 5.

**Files:**
- Create: `scripts/utils/llm.py`

- [ ] **Step 1: Implement `scripts/utils/llm.py`**

```python
from __future__ import annotations
from openai import OpenAI


class LLMClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def simple(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content.strip()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/utils/llm.py
git commit -m "feat: add LLMClient OpenRouter wrapper"
```

---

## Task 5: `scripts/tracker.py`

Replaces the existing `scripts/tracker.py` (which used an injected `claude` object). New version reads credentials from env/config and calls OpenRouter directly. The `_extract_posts`, `_fetch_weibo_content` logic from the original is preserved as `parse_weibo_cards` / `fetch_weibo_posts`.

**Files:**
- Create: `scripts/tests/test_tracker.py`
- Modify: `scripts/tracker.py` (overwrite existing)

- [ ] **Step 1: Write failing tests**

Replace the stub `scripts/tests/test_tracker.py`:

```python
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.tracker import parse_weibo_cards, format_events


SAMPLE_CARDS = [
    {
        "mblog": {
            "id": "abc",
            "bid": "Abc123",
            "text": "<a>link</a> 女性遭受家暴事件",
            "retweeted_status": {
                "text": "<b>转发内容</b> 详细描述"
            }
        }
    },
    {
        "mblog": {
            "id": "def",
            "bid": "Def456",
            "text": "无关内容",
        }
    },
    {
        "card_type": 9,  # non-mblog card, should be skipped
    }
]


def test_parse_weibo_cards_extracts_text():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert len(posts) == 2
    assert posts[0]["text"] == "link 女性遭受家暴事件"


def test_parse_weibo_cards_includes_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[0]["retweet_text"] == "转发内容 详细描述"


def test_parse_weibo_cards_empty_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[1]["retweet_text"] == ""


def test_parse_weibo_cards_skips_non_mblog():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert len(posts) == 2


def test_parse_weibo_cards_builds_url():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[0]["url"] == "https://weibo.com/1114030772/Abc123"


def test_format_events_markdown():
    events = [
        {"index": 1, "title": "测试事件", "brief": "简短描述", "sources": ["https://example.com"]},
    ]
    md = format_events("260325", events)
    assert "## 1. 测试事件" in md
    assert "简短描述" in md
    assert "https://example.com" in md


def test_format_events_header():
    md = format_events("260325", [])
    assert "2026-03-25" in md


def test_run_tracker_writes_events_file(tmp_path, monkeypatch):
    import scripts.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)

    with patch("scripts.tracker.fetch_weibo_posts", return_value=[]):
        with patch("scripts.tracker.filter_feminist_events", return_value=[
            {"title": "测试事件", "brief": "简短描述", "sources": ["https://example.com"]}
        ]):
            from scripts.tracker import run_tracker
            run_tracker("260325", api_key="test", model="test-model", cookie="")

    events_file = tmp_path / "_pipeline" / "events" / "260325.md"
    assert events_file.exists()
    assert "测试事件" in events_file.read_text(encoding="utf-8")
    assert (tmp_path / ".state").read_text().strip() == "20260325"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/test_tracker.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Overwrite `scripts/tracker.py`**

```python
from __future__ import annotations
import os
import sys
import json
import yaml
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from openai import OpenAI
from scripts.utils.web import WebClient
from scripts.utils.pipeline import events_path, set_state

WEIBO_API = "https://m.weibo.cn/api/container/getIndex"
TRACKED_UIDS = ["1114030772"]
FEMINIST_KEYWORDS = ["女性", "女权", "性别", "婚姻", "家暴", "性侵", "拐卖", "生育", "就业歧视"]


def parse_weibo_cards(cards: list[dict], uid: str) -> list[dict]:
    posts = []
    for card in cards:
        mblog = card.get("mblog")
        if not mblog:
            continue
        text = WebClient.extract_text(mblog.get("text", ""))
        retweet = mblog.get("retweeted_status") or {}
        retweet_text = WebClient.extract_text(retweet.get("text", "")) if retweet else ""
        posts.append({
            "id": mblog.get("id", ""),
            "url": f"https://weibo.com/{uid}/{mblog.get('bid', '')}",
            "text": text,
            "retweet_text": retweet_text,
        })
    return posts


def fetch_weibo_posts(web: WebClient, uid: str) -> list[dict]:
    url = f"{WEIBO_API}?type=uid&value={uid}&containerid=107603{uid}"
    data = web.fetch_json(url)
    cards = data.get("data", {}).get("cards", [])
    return parse_weibo_cards(cards, uid)


def filter_feminist_events(posts: list[dict], api_key: str, model: str) -> list[dict]:
    """Call OpenRouter to filter and deduplicate feminist-relevant events."""
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    posts_text = "\n\n".join(
        f"[{i+1}] URL: {p['url']}\nText: {p['text']}\nRetweet: {p['retweet_text']}"
        for i, p in enumerate(posts)
    )
    keywords = "、".join(FEMINIST_KEYWORDS)
    prompt = f"""以下是微博帖子。请筛选出与女性权益、性别议题相关的事件，关键词包括：{keywords}。

对于相同事件的多个帖子，请合并为一条。每条事件用以下格式输出（JSON数组）：
[
  {{
    "title": "标题简述（10字以内）",
    "brief": "一两句话概述",
    "sources": ["url1", "url2"]
  }}
]

如无相关内容，返回空数组 []。

帖子列表：
{posts_text}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    start = content.find("[")
    end = content.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    return json.loads(content[start:end])


def format_events(date_str: str, events: list[dict]) -> str:
    year = "20" + date_str[:2]
    month = date_str[2:4]
    day = date_str[4:6]
    lines = [f"# Events — {year}-{month}-{day}\n"]
    for i, ev in enumerate(events, 1):
        sources = " ".join(f"[{url}]" for url in ev.get("sources", []))
        lines.append(
            f"## {i}. {ev['title']}\n"
            f"**Sources**: {sources}\n"
            f"**Brief**: {ev['brief']}\n"
        )
    return "\n".join(lines)


def run_tracker(date_str: str, api_key: str, model: str, cookie: str) -> None:
    web = WebClient(cookie=cookie)
    all_posts = []
    for uid in TRACKED_UIDS:
        try:
            all_posts.extend(fetch_weibo_posts(web, uid))
        except WebClient.FetchError as e:
            print(f"Warning: failed to fetch uid {uid}: {e}")
    events = filter_feminist_events(all_posts, api_key, model)
    numbered = [dict(e, index=i + 1) for i, e in enumerate(events)]
    out = events_path(date_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_events(date_str, numbered), encoding="utf-8")
    set_state("20" + date_str)
    print(f"Wrote {len(numbered)} events to {out}")


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent / ".env")
    import sys as _sys
    date_arg = _sys.argv[1] if len(_sys.argv) > 1 else (
        (date.today() - __import__("datetime").timedelta(days=1)).strftime("%y%m%d")
    )
    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    run_tracker(
        date_str=date_arg,
        api_key=os.environ["OPENROUTER_API_KEY"],
        model=cfg["llm"]["tracker_model"],
        cookie=os.environ.get("WEIBO_COOKIE", ""),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/test_tracker.py -v
```
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add scripts/tracker.py scripts/tests/test_tracker.py
git commit -m "feat: rewrite tracker with OpenRouter filtering"
```

---

## Task 6: `scripts/publisher.py`

Replaces the existing `scripts/publisher.py`. Preserves the calendar injection and month-generation logic from the original; adds `move_assets()` for the draft asset lifecycle, and exposes testable pure functions.

**Files:**
- Create: `scripts/tests/test_publisher.py`
- Modify: `scripts/publisher.py` (overwrite existing)

- [ ] **Step 1: Write failing tests**

Replace the stub `scripts/tests/test_publisher.py`:

```python
import pytest
import shutil
from pathlib import Path

from scripts.publisher import (
    copy_draft, move_assets, read_frontmatter,
    calendar_color, inject_calendar_entry,
)


def test_copy_draft(tmp_path):
    src = tmp_path / "draft.md"
    src.write_text("content")
    dst = tmp_path / "out.md"
    copy_draft(src, dst)
    assert dst.read_text() == "content"


def test_move_assets_directory(tmp_path):
    assets_src = tmp_path / "src-assets"
    assets_src.mkdir()
    (assets_src / "img.jpg").write_bytes(b"data")
    assets_dst = tmp_path / "dst"
    move_assets(assets_src, assets_dst)
    assert (assets_dst / "img.jpg").exists()
    assert not assets_src.exists()


def test_move_assets_noop_if_missing(tmp_path):
    # Should not raise if source doesn't exist
    move_assets(tmp_path / "nonexistent", tmp_path / "dst")


def test_read_frontmatter_extracts_fields():
    content = "---\ntitle: 测试\ncategories: A\n---\n## 内容"
    fm = read_frontmatter(content)
    assert fm["title"] == "测试"
    assert fm["categories"] == "A"


def test_calendar_color_categories():
    assert calendar_color("A") == "red"
    assert calendar_color("B") == "yellow"
    assert calendar_color("C") == "orange"
    assert calendar_color("D") == "orange"
    assert calendar_color("N") == "black"


def test_inject_calendar_entry_inserts_link(tmp_path):
    index = tmp_path / "index.md"
    index.write_text(
        "## 2026年三月\n<td>25</td>\n",
        encoding="utf-8",
    )
    inject_calendar_entry(
        index_path=index,
        date_str="260325",
        title="测试事件",
        category="A",
        post_slug="260325",
    )
    content = index.read_text(encoding="utf-8")
    assert "260325" in content
    assert "测试" in content
    assert "red" in content


def test_inject_calendar_entry_appends_to_existing_cell(tmp_path):
    index = tmp_path / "index.md"
    index.write_text(
        '## 2026年三月\n<td>25<br>\n<a href="old">old</a>\n</td>\n',
        encoding="utf-8",
    )
    inject_calendar_entry(
        index_path=index,
        date_str="260325",
        title="新事件",
        category="B",
        post_slug="260325-new",
    )
    content = index.read_text(encoding="utf-8")
    assert "old" in content
    assert "新" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/test_publisher.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Overwrite `scripts/publisher.py`**

```python
from __future__ import annotations
import calendar as cal
import re
import shutil
import subprocess
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.pipeline import REPO_ROOT, PIPELINE

CATEGORY_COLORS = {"A": "red", "B": "yellow", "C": "orange", "D": "orange", "N": "black"}
MONTH_NAMES_ZH = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def read_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.index("---", 3)
    return yaml.safe_load(content[3:end]) or {}


def calendar_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "black")


def copy_draft(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def move_assets(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def inject_calendar_entry(
    index_path: Path, date_str: str, title: str, category: str, post_slug: str
) -> None:
    year = "20" + date_str[:2]
    month = int(date_str[2:4])
    day = int(date_str[4:6])
    color = calendar_color(category)
    link = (
        f'\n        <a style="color: {color};"'
        f'\n           href="{{{{ site.root }}}}{year}/{post_slug}/"'
        f'\n           title="{title}">{title[:6]}</a>'
    )

    content = index_path.read_text(encoding="utf-8")
    month_header = f"## {year}年{MONTH_NAMES_ZH[month - 1]}月"
    if month_header not in content:
        content = _append_new_month(content, int(year), month)

    # Case 1: empty cell <td>DAY</td>
    empty = re.compile(rf'<td>{day}</td>')
    if empty.search(content):
        new_content = empty.sub(f'<td>{day}<br>{link}\n      </td>', content, count=1)
    else:
        # Case 2: cell with existing link(s) — append before </td>
        existing = re.compile(rf'(<td>{day}<br>(?:(?!</td>).)*?)(</td>)', re.DOTALL)
        new_content = existing.sub(
            lambda m: m.group(1) + link + '\n      ' + m.group(2),
            content,
            count=1,
        )

    index_path.write_text(new_content, encoding="utf-8")


def _append_new_month(content: str, year: int, month: int) -> str:
    month_name = MONTH_NAMES_ZH[month - 1]
    header = f"## {year}年{month_name}月"
    month_cal = cal.monthcalendar(year, month)
    rotated = [[week[6]] + week[:6] for week in month_cal]
    rows = []
    for week in rotated:
        cells = "\n".join(
            f"      <td>{day if day else ''}</td>" for day in week
        )
        rows.append(f"    <tr>\n{cells}\n    </tr>")
    table = (
        f"\n\n{header}\n\n"
        "<table class=\"calendar-table\">\n"
        "  <thead>\n    <tr>\n"
        "      <th>日</th><th>一</th><th>二</th><th>三</th>"
        "<th>四</th><th>五</th><th>六</th>\n"
        "    </tr>\n  </thead>\n  <tbody>\n"
        + "\n".join(rows) + "\n"
        "  </tbody>\n</table>\n"
    )
    return content.rstrip() + table


def publish(date_str: str, n: int, title: str, draft_path: Path, deploy: bool = True) -> None:
    fm = read_frontmatter(draft_path.read_text(encoding="utf-8"))
    posts_dir = REPO_ROOT / "source" / "_posts"
    post_slug = date_str

    copy_draft(draft_path, posts_dir / f"{date_str}.md")
    print(f"Copied draft → {posts_dir / f'{date_str}.md'}")

    assets_src = PIPELINE / "draft" / f"{date_str}-{n}-assets"
    move_assets(assets_src, posts_dir / date_str)
    if (posts_dir / date_str).exists():
        print(f"Moved assets → {posts_dir / date_str}")

    inject_calendar_entry(
        index_path=REPO_ROOT / "source" / "index.md",
        date_str=date_str,
        title=fm.get("title", title),
        category=str(fm.get("categories", "N")),
        post_slug=post_slug,
    )
    print("Updated index.md calendar")

    if deploy:
        subprocess.run(["pnpm", "run", "deploy"], cwd=REPO_ROOT, check=True)
        print("Deployed to GitHub Pages")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    import sys as _sys
    date_str = _sys.argv[1]
    n = int(_sys.argv[2])
    drafts = sorted(
        (PIPELINE / "draft").glob(f"{date_str}-{n}-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not drafts:
        print(f"No draft found for {date_str}-{n}")
        _sys.exit(1)
    draft_path = drafts[0]
    title = draft_path.stem.split("-", 2)[-1].rsplit("-v", 1)[0]
    publish(date_str, n, title, draft_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest tests/test_publisher.py -v
```
Expected: all green

- [ ] **Step 5: Run all tests to confirm no regressions**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest -v
```
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add scripts/publisher.py scripts/tests/test_publisher.py
git commit -m "feat: rewrite publisher (copy, move assets, calendar inject, deploy)"
```

---

## Task 7: `blog-research` skill

**Files:**
- Create: `.claude/skills/blog-research/SKILL.md`
- Create: `.claude/skills/blog-research/notes.md`

- [ ] **Step 1: Create `.claude/skills/blog-research/SKILL.md`**

```markdown
---
name: blog-research
description: Research subagent for the feminist blog — researches one event using WebSearch and WebFetch
---

# Blog Research Agent

You are a research subagent for a feminist news blog. Your job is to thoroughly research a single event and produce a structured research file.

## Your Inputs

The orchestrator will tell you:
- `date`: YYMMDD (e.g. `260325`)
- `index`: event number N (e.g. `1`)
- `title`: event title in Chinese
- `brief`: one-sentence summary
- `sources`: initial Weibo source URLs

Repo root: `/home/jc/Projects/auto-watcher`

## Search Strategy

Search in this order:

1. Search the event title in Chinese (exact phrase in quotes) → find news coverage
2. Search each key party's name + "声明" or "回应" → find official responses
3. Search victim/party Weibo handles if mentioned → find direct statements
4. Search title + "律师" or "量刑" or "判决" → find legal/expert commentary
5. Search title + "微博" or "词条" → find public reaction and hashtag metrics

Use WebFetch on the most relevant URLs to extract verbatim quotes. Prioritise: 澎湃新闻, 新京报, 红星新闻, 极目新闻, 观察者网, official government/court notices.

## Coverage Standard

Research is sufficient when you have:
- Core facts established with at least 2 independent sources
- Statements or positions from all key parties (or noted as unavailable)
- Any official response (police, court, institution, government body)
- Legal/expert commentary if the case involves criminal law or sentencing
- Weibo topic hashtag name and read count if one exists

## Output

Write to `_pipeline/research/{date}-{index}-{title}.md`:

```markdown
# Research: {title} ({date}, #{index})

## Facts
[Key facts in chronological order. Use <font color="blue">text</font> for the most recent update.]

## Parties
[Each key party — victim, perpetrator, institution. Their actions, statements, Weibo posts.
Include Weibo handles/usernames where known.]

## Sources
- [来源名称](url) — 关键摘录（原文引号）
```

Read `.claude/skills/blog-research/notes.md` before starting — it contains accumulated search patterns and known sources.
```

- [ ] **Step 2: Create `.claude/skills/blog-research/notes.md`**

```markdown
# Research Notes

Accumulated knowledge for the blog-research skill. Max ~15 entries.
Add new entries as [NOTE] or [CANDIDATE] (ready to promote to SKILL.md).

---
```

- [ ] **Step 3: Verify skill file matches spec format**

Check that SKILL.md:
- Has valid YAML frontmatter with `name` and `description`
- Covers: search strategy, coverage standard, output format
- References notes.md

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/blog-research/
git commit -m "feat: add blog-research skill"
```

---

## Task 8: `blog-write` skill

**Files:**
- Create: `.claude/skills/blog-write/SKILL.md`
- Create: `.claude/skills/blog-write/notes.md`

- [ ] **Step 1: Create `.claude/skills/blog-write/SKILL.md`**

```markdown
---
name: blog-write
description: Writing subagent for the feminist blog — writes or revises a single post draft
---

# Blog Write Agent

You are a writing subagent for a feminist news blog. You write or revise one post draft.

## Your Inputs

The orchestrator will tell you:
- `date`: YYMMDD
- `index`: N
- `title`: post title in Chinese
- `mode`: `initial` or `revision`
- `research_path`: path to research file (always provided)
- `draft_path`: path to current draft (revision mode only)
- `review_path`: path to review file (revision mode only)

Repo root: `/home/jc/Projects/auto-watcher`

## Modes

**Initial mode:** Read the research file. Use WebSearch + WebFetch for additional sources or missing details not covered in research. Write the first draft.

**Revision mode:** Read the current draft and review file together. Apply every `<!-- [REVIEWER]: ... -->` suggestion. Preserve every `<!-- [USER]: ... -->` annotation exactly as written — if a reviewer suggestion conflicts with a user annotation, follow the user annotation. Use WebSearch + WebFetch to verify or supplement facts if needed.

## Output Path

```python
import sys
sys.path.insert(0, '/home/jc/Projects/auto-watcher')
from scripts.utils.pipeline import next_draft_path
path, v = next_draft_path(date, index, title)
# Write draft to str(path)
```

## Draft Format

Follow `source/_drafts/template.md` for structure. Use published posts in `source/_posts/` as style reference.

```
---
title: [post title]
date: [YYYY-MM-DD HH:MM:SS]
categories: [A/B/C/D/N]
tags:
- [tag]
---

## 概述
[Summary paragraph. Add #### 时间线 subsection only if the story spans multiple dates —
use bold dates: **YYYY年M月D日**：...]

## 信息来源
[YYYY.MM.DD，来源名称。*标题*。URL or asset]

## 前情
[Optional: prior background. Same source format.]

## 后续
[Optional: follow-up. Format: （年）月日：...]

## 舆论
[Optional: public reaction]
### 微博词条
[#词条名# 访问日期：年.月.日。阅读量：N万。]

## 相关内容
[Optional: related cases, context, documents]
```

## Inline Formatting

- `<font color="red">text</font>` — legally/factually significant statements, key findings
- `<font color="blue">text</font>` — most recent update in the story
- `<font color="grey">text</font>` — verbatim quote from a party or document

All verbatim quotes from parties, courts, or official notices MUST use `<font color="grey">`.

## Style Rules

- No em dashes (破折号 —). Restructure the sentence instead.
- No filler phrases: "此事沉寂数月后"、"引发广泛关注" etc. State the fact directly.
- Concise 概述: 2–4 sentences maximum before the timeline.
- Sources section: one line per source, format exactly `YYYY.MM.DD，来源。*标题*。URL`

## Categories

- `A` — 刑事案件；影响极为恶劣的舆论事件
- `B` — 民事案件；影响较大的舆论事件
- `C` — 非官方组织；影响较小的舆论事件
- `D` — 个人行为
- `N` — 中立事件/等待后续

## Special Tags

- `PING` — 插眼等后续（follow-up expected）
- `TODO` — 还需查证（unverified claim）

## Assets

Download images and documents to `_pipeline/draft/{date}-{index}-assets/`.
Reference in post:
```html
<img src="{% asset_path filename.jpg %}" width="300" alt="description">
<embed src="{% asset_path file.pdf %}" type="application/pdf" width="100%" height="600px">
```

Read `.claude/skills/blog-write/notes.md` before writing — it contains accumulated style and voice guidance.
```

- [ ] **Step 2: Create `.claude/skills/blog-write/notes.md`**

```markdown
# Write Notes

Accumulated style and voice guidance for blog-write. Max ~15 entries.

---
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/blog-write/
git commit -m "feat: add blog-write skill"
```

---

## Task 9: `blog-review` skill

**Files:**
- Create: `.claude/skills/blog-review/SKILL.md`
- Create: `.claude/skills/blog-review/notes.md`

- [ ] **Step 1: Create `.claude/skills/blog-review/SKILL.md`**

```markdown
---
name: blog-review
description: Review subagent for the feminist blog — independently fact-checks a draft and annotates issues
---

# Blog Review Agent

You are a review subagent for a feminist news blog. You independently fact-check a draft and produce a review file.

## Your Inputs

The orchestrator will tell you:
- `draft_path`: path to the latest draft version

Repo root: `/home/jc/Projects/auto-watcher`

## Process

1. Read the draft carefully.
2. For each factual claim, use WebSearch + WebFetch to verify it independently. Do not assume the research file is correct — check sources yourself.
3. Annotate issues inline using `<!-- [REVIEWER]: explanation -->` placed directly after the problematic line.
4. Write the review file.

## Review Checklist

Facts:
- [ ] Each date is correct
- [ ] Each name, role, and institution is correct
- [ ] Each verbatim quote is accurately attributed
- [ ] No claim is presented as fact without a verifiable source

Completeness:
- [ ] No significant facts missing that would materially change the story
- [ ] Follow-up status is accurate (tag PING if still developing)
- [ ] Unverifiable claims are tagged TODO

Categorisation:
- [ ] `categories` value (A/B/C/D/N) matches the severity guidelines
- [ ] Tags are appropriate

Wording:
- [ ] No em dashes (破折号 —)
- [ ] No filler phrases
- [ ] Verbatim quotes are in `<font color="grey">` blocks

## Pass Criteria

**STATUS: CLEAN** when: all verifiable facts checked out, no significant omissions, category and tags are correct.

**STATUS: ISSUES** when: any factual error, significant omission that changes the story, wrong category/tag, or misattributed quote.

## Output Format

Write to `_pipeline/review/{same-filename-as-draft}.md`.

**The first line must be exactly `STATUS: CLEAN` or `STATUS: ISSUES`.**

If STATUS: ISSUES, reproduce the full draft below with annotations:

```
STATUS: ISSUES

[draft content with <!-- [REVIEWER]: explanation --> after each flagged line]
```

If STATUS: CLEAN, the file may contain just the status line and a brief note.

Read `.claude/skills/blog-review/notes.md` before reviewing — it contains patterns to watch for.
```

- [ ] **Step 2: Create `.claude/skills/blog-review/notes.md`**

```markdown
# Review Notes

Accumulated patterns and recurring issues for blog-review. Max ~15 entries.

---
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/blog-review/
git commit -m "feat: add blog-review skill"
```

---

## Task 10: `blog-curate` skill

**Files:**
- Create: `.claude/skills/blog-curate/SKILL.md`

- [ ] **Step 1: Create `.claude/skills/blog-curate/SKILL.md`**

```markdown
---
name: blog-curate
description: Curate blog skill notes — promote candidates to SKILL.md, prune stale entries, flag conflicts
---

# Blog Curate

You curate the accumulated knowledge notes for the blog pipeline skills.

## Files to Read

Read all six files:
- `.claude/skills/blog-research/SKILL.md`
- `.claude/skills/blog-research/notes.md`
- `.claude/skills/blog-write/SKILL.md`
- `.claude/skills/blog-write/notes.md`
- `.claude/skills/blog-review/SKILL.md`
- `.claude/skills/blog-review/notes.md`

## Curation Steps

**1. Conflict check**
Flag any note that:
- Directly contradicts a rule in its corresponding SKILL.md (e.g. note says "always do X", SKILL.md says "never do X")
- Duplicates a rule already stated in SKILL.md

**2. Promotion candidates**
For each `[CANDIDATE]` entry:
- Propose exact text to add to SKILL.md
- Propose which section to add it to
- Show the note that would be deleted

**3. Pruning**
Identify notes that are:
- Redundant (same point made by another note or by SKILL.md)
- Outdated (contradicted by a more recent note)
- Too vague to be actionable (e.g. "be careful with quotes")

**4. Present consolidated diff**
Show all proposed changes as a clear before/after list:
- Notes to delete (from notes.md)
- Additions to SKILL.md (from promotions)

**5. Wait for user approval before writing anything.**

**6. After confirmation:** Apply changes using the Edit tool. Delete promoted entries from notes.md. Insert promoted content into the appropriate section of SKILL.md.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/blog-curate/
git commit -m "feat: add blog-curate skill"
```

---

## Task 11: `blog-orchestrator` skill

**Files:**
- Create: `.claude/skills/blog-orchestrator/SKILL.md`

- [ ] **Step 1: Create `.claude/skills/blog-orchestrator/SKILL.md`**

```markdown
---
name: blog-orchestrator
description: Use when running the feminist blog pipeline — track events, research, write, review, and publish posts
---

# Blog Orchestrator

You orchestrate the full feminist news blog pipeline at `/home/jc/Projects/auto-watcher`.

## Session Start

Run pipeline summary and check notes length:

```bash
cd /home/jc/Projects/auto-watcher && python3 -c "
import sys; sys.path.insert(0, '.')
from scripts.utils.pipeline import pipeline_summary
print(pipeline_summary())
"
```

Check each notes.md line count:
```bash
for f in .claude/skills/blog-research/notes.md .claude/skills/blog-write/notes.md .claude/skills/blog-review/notes.md; do
  count=$(grep -c '^\- \[' "$f" 2>/dev/null || echo 0)
  echo "$f: $count entries"
done
```

If any file has more than 15 entries, warn:
> "`[skill]/notes.md` has N entries — consider running `/blog-curate` to prune and promote."

---

## Stage 1 — Track

Show untracked dates:
```bash
cd /home/jc/Projects/auto-watcher && python3 -c "
import sys; sys.path.insert(0, '.')
from scripts.utils.pipeline import get_untracked_dates
dates = get_untracked_dates()
print('Untracked (last 7 days):', dates if dates else 'none')
"
```

Ask: **"Which date to track? (default: yesterday, format YYMMDD)"**

If the events file already exists for that date:
- Ask: **"Events file exists for YYMMDD. [R]etrack (overwrite) or [U]se existing?"**
- If retrack → run tracker (overwrites file)
- If use existing → show file, skip to Gate 1

Run tracker:
```bash
cd /home/jc/Projects/auto-watcher && source scripts/venv/bin/activate && python scripts/tracker.py YYMMDD
```

Show the events file content.

**── GATE 1 ──**
> "Which event indexes do you approve for research? (e.g. `1 3`)"

Write approved indexes (one per line):
```bash
printf "1\n3\n" > /home/jc/Projects/auto-watcher/_pipeline/events/YYMMDD-approved.txt
```

---

## Stage 2 — Research (parallel)

For each approved index N, dispatch a **blog-research** subagent concurrently.

Tell each subagent:
> "Load the blog-research skill. Research this event:
> - date: YYMMDD
> - index: N
> - title: [title from events file]
> - brief: [brief from events file]
> - sources: [source URLs from events file]
> Repo root: /home/jc/Projects/auto-watcher"

Wait for **all** research subagents to complete before proceeding.

---

## Stage 3 — Write (parallel)

For each approved index N, dispatch a **blog-write** subagent concurrently.

Tell each subagent:
> "Load the blog-write skill. Write an initial draft:
> - date: YYMMDD, index: N, title: [title]
> - mode: initial
> - research_path: _pipeline/research/YYMMDD-N-[title].md
> Repo root: /home/jc/Projects/auto-watcher"

Wait for **all** write subagents to complete before proceeding.

**── GATE 2 ──**
List the draft paths. Then say:
> "Drafts are ready. Please review each file and add `<!-- [USER]: your note -->` anywhere you want to override reviewer suggestions. Reply **done** when ready."

Wait for explicit "done" confirmation.

---

## Stage 4 — Review Loop (per draft)

Handle each approved draft independently. For each:

**4a.** Find the latest draft version:
```bash
ls _pipeline/draft/YYMMDD-N-*.md | sort -V | tail -1
```

**4b.** Dispatch a **blog-review** subagent:
> "Load the blog-review skill. Review this draft:
> - draft_path: _pipeline/draft/YYMMDD-N-[title]-vN.md
> Repo root: /home/jc/Projects/auto-watcher"

**4c.** When complete, read the review status:
```bash
head -1 /home/jc/Projects/auto-watcher/_pipeline/review/YYMMDD-N-[title]-vN.md
```

**4d.** If `STATUS: ISSUES`:
- Dispatch a **blog-write** subagent for revision:
  > "Load the blog-write skill. Revise this draft:
  > - date: YYMMDD, index: N, title: [title]
  > - mode: revision
  > - research_path: _pipeline/research/YYMMDD-N-[title].md
  > - draft_path: _pipeline/draft/YYMMDD-N-[title]-vN.md
  > - review_path: _pipeline/review/YYMMDD-N-[title]-vN.md
  > Repo root: /home/jc/Projects/auto-watcher"
- Return to step 4a.

**4e.** If `STATUS: CLEAN` → proceed to Gate 3 for this draft.

**── GATE 3 ──** (per draft)
> "Draft YYMMDD-N ([title]) is clean.
> File: `_pipeline/draft/YYMMDD-N-[title]-vN.md`
>
> **Publish to GitHub Pages?** (yes/no)"

**Always wait for explicit yes before publishing.**

---

## Stage 5 — Publish

For each confirmed draft:
```bash
cd /home/jc/Projects/auto-watcher && source scripts/venv/bin/activate && python scripts/publisher.py YYMMDD N
```

Warn before running: *"This will run `pnpm deploy` and push to GitHub Pages."*

---

## Rules

- Date format in filenames: `YYMMDD` (6 digits)
- Date format in `.state`: `YYYYMMDD` (8 digits)
- Research and writing are **always** done by Claude Code subagents — never call LLM APIs for these stages (feminist content is censored by Chinese models)
- On Weibo fetch failure: ask user to paste content manually
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/blog-orchestrator/
git commit -m "feat: add blog-orchestrator skill"
```

---

## Task 12: Wiring — Symlinks and Settings

**Files:**
- Modify: `~/.claude/settings.json` (add `blog-orchestrator` entry, remove `blog-coordinator`)

- [ ] **Step 1: Create skill directories and run symlink script**

```bash
cd /home/jc/Projects/auto-watcher
mkdir -p .claude/skills/blog-orchestrator \
         .claude/skills/blog-research \
         .claude/skills/blog-write \
         .claude/skills/blog-review \
         .claude/skills/blog-curate
bash setup/symlink-skills.sh
```

Expected output: symlinks created for each `blog-*` skill in `~/.claude/skills/`.

- [ ] **Step 2: Verify symlinks**

```bash
ls -la ~/.claude/skills/ | grep blog-
```

Expected: 5 symlinks pointing into the repo.

- [ ] **Step 3: Update `~/.claude/settings.json`**

Open the file and within the existing `skills` object, **add** the `blog-orchestrator` entry and **remove** the `blog-coordinator` entry. Do not replace the entire `skills` object — other skills may be registered there.

Entry to add:
```json
"blog-orchestrator": {
  "description": "Use when the user wants to run the feminist blog pipeline — tracking Weibo events, researching, writing, reviewing, or publishing posts at /home/jc/Projects/auto-watcher"
}
```

- [ ] **Step 4: Retire old global skill**

```bash
# Rename rather than delete, in case rollback is needed
mv ~/.claude/skills/blog-coordinator ~/.claude/skills/blog-coordinator.retired
```

- [ ] **Step 5: Verify `/blog` resolves to blog-orchestrator**

Start a new Claude Code session and type `/blog`. Confirm the orchestrator skill loads.

- [ ] **Step 6: Commit**

```bash
cd /home/jc/Projects/auto-watcher
git add .claude/skills/
git commit -m "feat: wire skills with symlinks, retire blog-coordinator"
```

---

## Task 13: Smoke Test

End-to-end manual validation of the full pipeline.

- [ ] **Step 1: Run full test suite**

```bash
cd /home/jc/Projects/auto-watcher/scripts && pytest -v
```
Expected: all green

- [ ] **Step 2: Invoke `/blog` and walk through Stage 1**

In a new Claude Code session:
- Type `/blog`
- Confirm pipeline summary appears
- Confirm untracked dates are shown
- Enter a date to track
- Confirm tracker runs and events file is written

- [ ] **Step 3: Walk through Gates 1–3 with a test event**

- Approve one event index at Gate 1
- Confirm research subagent is dispatched and research file written
- Confirm write subagent produces a draft
- Annotate draft at Gate 2 with `<!-- [USER]: test annotation -->`
- Confirm review subagent runs and review file begins with `STATUS:`
- Confirm review loop exits correctly

- [ ] **Step 4: Verify publisher dry-run (no deploy)**

```bash
cd /home/jc/Projects/auto-watcher && source scripts/venv/bin/activate
python -c "
import sys; sys.path.insert(0, '.')
from scripts.publisher import read_frontmatter, calendar_color
print('publisher imports OK')
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: complete pipeline smoke test"
```
