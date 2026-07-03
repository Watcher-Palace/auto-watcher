# Pipeline Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rate-limit-proof Weibo tracking (incremental state, request budget, anonymous URL fetch), a mechanical draft linter that runs before Sonnet review, and a fed skill-evolution loop (publisher harvest queue + distillation with a user gate for exception rules).

**Architecture:** Three independent workstreams per spec `docs/superpowers/specs/2026-07-03-pipeline-efficiency-design.md`. New modules: `src/linter.py`, `src/wbfetch.py`, `src/utils/tracker_state.py`. Surgical additions to `src/tracker.py` (`--daily`, `--urls`) and `src/publisher.py` (lint gate, harvest queue). Doc/skill edits wire the loop.

**Tech Stack:** Python 3.12 (venv at `src/venv/`), pytest (hermetic; monkeypatch module globals per existing convention), playwright-python driving system Chrome (`channel="chrome"`), existing Haiku-via-claude-CLI filter untouched.

**Checkpoint discipline:** after EVERY green test step: `git add -A && git commit && git push`. Test command (from repo root): `src/venv/bin/python -m pytest src/tests/ -q`.

---

### Task 1: Draft linter `src/linter.py`

**Files:**
- Create: `src/linter.py`
- Create: `src/tests/test_linter.py`
- Modify: `src/publisher.py` (lint gate in `publish()`)
- Modify: `.claude/skills/blog-write/SKILL.md` (writer must pass lint)

- [x] **Step 1: Write failing tests**

```python
# src/tests/test_linter.py
import pytest
from datetime import date
from src.linter import lint_text

REGISTRY = {"犯罪", "性侵", "AI", "PING", "TODO"}
TODAY = date(2026, 7, 3)


def make_draft(body="", date_str="2026-06-01", categories="B", tags=("犯罪",)):
    tag_lines = "\n".join(f"- {t}" for t in tags)
    return (
        f"---\ntitle: 测试\ndate: {date_str}\ncategories: {categories}\n"
        f"tags:\n{tag_lines}\n---\n\n## 概述\n正文。\n\n"
        f"## 信息来源\n2026.06.01，来源。*标题*。https://example.com/a\n" + body
    )


def test_clean_draft_passes():
    assert lint_text(make_draft(), REGISTRY, TODAY) == []


def test_em_dash_flagged():
    v = lint_text(make_draft(body="\n他说——这样。\n"), REGISTRY, TODAY)
    assert any("破折号" in x for x in v)


def test_yulun_without_numbers_flagged():
    v = lint_text(make_draft(body="\n## 舆论\n网友纷纷表示愤怒。\n"), REGISTRY, TODAY)
    assert any("舆论" in x for x in v)


def test_yulun_with_metric_passes():
    body = "\n## 舆论\n### 微博词条\n#某某案# 访问日期：2026.6.1。阅读量：1.2亿。\n"
    assert lint_text(make_draft(body=body), REGISTRY, TODAY) == []


def test_bad_source_line_flagged():
    draft = make_draft().replace(
        "2026.06.01，来源。*标题*。https://example.com/a", "来源：某新闻网 2026年6月"
    )
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("信息来源" in x for x in v)


def test_unknown_tag_flagged():
    v = lint_text(make_draft(tags=("不存在的标签",)), REGISTRY, TODAY)
    assert any("不存在的标签" in x for x in v)


def test_standalone_qianqing_flagged():
    v = lint_text(make_draft(body="\n## 前情\n旧事。\n"), REGISTRY, TODAY)
    assert any("前情" in x for x in v)


def test_future_date_flagged():
    v = lint_text(make_draft(date_str="2026-07-04"), REGISTRY, TODAY)
    assert any("未来" in x for x in v)


def test_missing_required_section_flagged():
    draft = make_draft().replace("## 概述\n正文。\n\n", "")
    v = lint_text(draft, REGISTRY, TODAY)
    assert any("概述" in x for x in v)


def test_bad_category_flagged():
    v = lint_text(make_draft(categories="X"), REGISTRY, TODAY)
    assert any("categories" in x for x in v)
```

- [x] **Step 2: Run, verify failure** — `src/venv/bin/python -m pytest src/tests/test_linter.py -q` → ImportError.

- [x] **Step 3: Implement `src/linter.py`**

```python
from __future__ import annotations
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.publisher import read_frontmatter, load_tag_registry

VALID_CATEGORIES = {"S", "A", "B", "C", "D", "N"}
METRIC_RE = re.compile(r"(阅读量|讨论量|转发量|评论量|投票|票数)")
SOURCE_LINE_RE = re.compile(r"^(- )?\d{4}\.\d{1,2}\.\d{1,2}，.+?。\*.+?\*。\S+")


def _sections(body: str) -> dict[str, str]:
    """Map '## X' heading → section text (up to next ## heading)."""
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def lint_text(content: str, registry: set[str] | None, today: date) -> list[str]:
    violations: list[str] = []
    fm = read_frontmatter(content)
    body = content.split("---", 2)[-1] if content.startswith("---") else content

    if "—" in content:
        violations.append("破折号 — 出现（风格规则：重组句子，不用破折号）")

    secs = _sections(body)
    for required in ("概述", "信息来源"):
        if required not in secs:
            violations.append(f"缺少必需章节 ## {required}")

    if "舆论" in secs:
        s = secs["舆论"]
        if not (METRIC_RE.search(s) and re.search(r"\d", s)):
            violations.append("## 舆论 无具体数据（阅读量/讨论量/转发量/评论量）——无数据时整节删除")

    for banned in ("前情", "后续"):
        if banned in secs:
            violations.append(f"独立 ## {banned} 章节（应并入 ## 概述 的 #### 子节）")

    if "信息来源" in secs:
        for ln in secs["信息来源"].splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("<!--"):
                continue
            if not SOURCE_LINE_RE.match(ln):
                violations.append(f"信息来源 行格式不符（YYYY.MM.DD，来源。*标题*。URL）：{ln[:50]}")

    cats = fm.get("categories")
    cat_list = cats if isinstance(cats, list) else [cats]
    for c in cat_list:
        if c not in VALID_CATEGORIES:
            violations.append(f"categories 非法值：{c!r}（允许 S/A/B/C/D/N）")

    if registry:
        for t in fm.get("tags") or []:
            if t not in registry:
                violations.append(f"未注册 tag：{t}（见 src/tags.yml）")

    d = fm.get("date")
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            d = None
            violations.append(f"date 无法解析：{fm.get('date')!r}")
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date) and d > today:
        violations.append(f"date 在未来：{d.isoformat()}")

    return violations


def lint_file(path: Path) -> list[str]:
    return lint_text(path.read_text(encoding="utf-8"), load_tag_registry(), date.today())


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python src/linter.py <draft.md>...")
        return 2
    rc = 0
    for p in argv:
        vs = lint_file(Path(p))
        if vs:
            rc = 1
            print(f"LINT FAIL {p}")
            for v in vs:
                print(f"  - {v}")
        else:
            print(f"LINT OK {p}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [x] **Step 4: Green** — same pytest command, all pass. Full suite too.

- [x] **Step 5: Publisher gate** — in `src/publisher.py` `publish()` right after `validate_tags(...)`:

```python
    from src.linter import lint_text
    from datetime import date as _date
    violations = lint_text(draft_path.read_text(encoding="utf-8"), load_tag_registry(), _date.today())
    if violations:
        raise SystemExit("Draft fails lint:\n" + "\n".join(f"  - {v}" for v in violations))
```

Add test in `test_linter.py` (monkeypatch style of `test_publish_finalizes_terminal_date`) that `publish()` raises SystemExit on a draft with an em dash, `deploy=False`.

- [x] **Step 6: blog-write SKILL.md** — append to the end of the "Style Rules" section:

```markdown
- **Lint gate (mandatory):** after writing the draft file, run
  `src/venv/bin/python /home/jc/Projects/auto-watcher/src/linter.py <draft-path>`
  and fix every violation before finishing. Do not report completion with a failing lint.
```

- [x] **Step 7: Full suite green → commit + push.**

### Task 2: Tracker incremental state + budget + `--daily`

**Files:**
- Create: `src/utils/tracker_state.py`
- Create: `src/tests/test_tracker_daily.py`
- Modify: `src/tracker.py`
- Modify: `CLAUDE.md` (Stage 1 commands; pitfalls row already fixed)

- [x] **Step 1: Failing tests for state store**

```python
# src/tests/test_tracker_daily.py
import json
import pytest
from datetime import date, datetime, timedelta
from src.utils.tracker_state import load_state, save_state, DEFAULT_STATE


def test_load_missing_returns_default(tmp_path):
    s = load_state(tmp_path / "none.json")
    assert s == DEFAULT_STATE


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = load_state(p)
    s["uids"]["111"] = {"last_seen_id": "5300000000000001", "pending": None}
    save_state(s, p)
    assert load_state(p)["uids"]["111"]["last_seen_id"] == "5300000000000001"
```

- [x] **Step 2: Implement `src/utils/tracker_state.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
from src.utils.pipeline import PIPELINE

DEFAULT_STATE: dict = {"uids": {}}


def state_path() -> Path:
    return PIPELINE / ".tracker-state.json"


def load_state(path: Path | None = None) -> dict:
    p = path or state_path()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(state: dict, path: Path | None = None) -> None:
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
```

- [x] **Step 3: Failing tests for `run_tracker_daily`** (patch `src.tracker.fetch_weibo_posts`, `src.tracker.filter_feminist_events`, `src.utils.pipeline.PIPELINE` → tmp; no sleeps: patch `time.sleep`):

```python
def _post(pid, day, text="家暴 事件", top=False):
    dt = datetime(2026, 7, day, 12, 0, tzinfo=__import__("src.tracker", fromlist=["CN_TZ"]).CN_TZ)
    return {"id": pid, "url": f"u/{pid}", "text": text, "retweet_text": "", "created_dt": dt, "is_top": top}


@pytest.fixture
def env(tmp_path, monkeypatch):
    pipe = tmp_path / "_pipeline"
    (pipe / "events").mkdir(parents=True)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", pipe)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("TRACKED_UIDS", "111")
    monkeypatch.setattr(
        "src.tracker.filter_feminist_events",
        lambda posts: [{"title": p["text"][:5], "brief": p["text"], "sources": [p["url"]]} for p in posts],
    )
    return pipe


def test_daily_stops_at_last_seen(env, monkeypatch):
    pages = {1: [_post("200", 2), _post("150", 1)], 2: [_post("100", 1)]}
    calls = []
    def fake_fetch(web, uid, page=1):
        calls.append(page)
        return pages.get(page, [])
    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    from src.tracker import run_tracker_daily
    state = {"uids": {"111": {"last_seen_id": "150", "pending": None}}}
    sp = env / ".tracker-state.json"
    __import__("src.utils.tracker_state", fromlist=["save_state"]).save_state(state, sp)
    run_tracker_daily(cookie="c", budget=10, state_path=sp, today=date(2026, 7, 3))
    assert calls == [1]                      # page 2 never fetched
    from src.utils.tracker_state import load_state
    assert load_state(sp)["uids"]["111"]["last_seen_id"] == "200"
    assert (env / "events" / "260702.md").exists()


def test_daily_budget_exhaustion_persists_cursor(env, monkeypatch):
    def fake_fetch(web, uid, page=1):
        return [_post(str(1000 - page * 10 - i), 2) for i in range(2)]
    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    from src.tracker import run_tracker_daily
    sp = env / ".tracker-state.json"
    run_tracker_daily(cookie="c", budget=1, state_path=sp, today=date(2026, 7, 3))
    from src.utils.tracker_state import load_state
    pend = load_state(sp)["uids"]["111"]["pending"]
    assert pend and pend["next_page"] == 2


def test_daily_rate_limited_persists_and_exits_2(env, monkeypatch):
    from src.tracker import RateLimited
    def fake_fetch(web, uid, page=1):
        raise RateLimited()
    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    from src.tracker import run_tracker_daily
    sp = env / ".tracker-state.json"
    with pytest.raises(SystemExit) as ei:
        run_tracker_daily(cookie="c", budget=10, state_path=sp, today=date(2026, 7, 3))
    assert ei.value.code == 2
```

- [x] **Step 4: Implement `run_tracker_daily` in `src/tracker.py`**

```python
DAILY_BUDGET = 40
DAILY_FIRST_RUN_DAYS = 3


def run_tracker_daily(
    cookie: str,
    budget: int = DAILY_BUDGET,
    state_path: Path | None = None,
    today: date | None = None,
) -> None:
    """Incremental fetch since last_seen_id per UID, budget-capped, merge-append.

    Budget exhaustion persists a resume cursor and exits 0 (resume next run).
    RateLimited persists the cursor and exits 2. Never suggests cookie swaps:
    the throttle is account-level.
    """
    from src.utils.tracker_state import load_state, save_state, state_path as _sp
    sp = state_path or _sp()
    state = load_state(sp)
    today = today or date.today()
    uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    web = WebClient(cookie=cookie)
    first_run_cutoff = datetime.combine(
        today - timedelta(days=DAILY_FIRST_RUN_DAYS), datetime.min.time(), tzinfo=CN_TZ
    )
    remaining = budget
    all_new: list[dict] = []
    rate_limited = False

    for i, uid in enumerate(uids):
        ustate = state["uids"].setdefault(uid, {"last_seen_id": None, "pending": None})
        last_seen = int(ustate["last_seen_id"]) if ustate["last_seen_id"] else None
        page = (ustate["pending"] or {}).get("next_page", 1)
        if i > 0 and remaining > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        max_id_seen = last_seen or 0
        while remaining > 0:
            remaining -= 1
            try:
                posts = fetch_weibo_posts(web, uid, page=page)
            except RateLimited:
                ustate["pending"] = {"next_page": page}
                rate_limited = True
                break
            except WebClient.FetchError as e:
                print(f"  uid {uid} page {page}: fetch error {e}", file=sys.stderr)
                break
            if not posts:
                ustate["pending"] = None
                break
            fresh = [
                p for p in posts
                if p["id"] and not p["is_top"]
                and (last_seen is None or int(p["id"]) > last_seen)
            ]
            for p in fresh:
                max_id_seen = max(max_id_seen, int(p["id"]))
            all_new.extend(fresh)
            organic = [p for p in posts if not p["is_top"] and p["created_dt"]]
            reached_old = (
                (last_seen is not None and len(fresh) < len(organic))
                or (last_seen is None and organic and min(p["created_dt"] for p in organic) < first_run_cutoff)
            )
            if reached_old:
                ustate["pending"] = None
                break
            page += 1
            if remaining > 0:
                time.sleep(random.uniform(PAGINATION_DELAY_SEC, PAGINATION_DELAY_SEC * 3))
        else:
            ustate["pending"] = {"next_page": page}
        if max_id_seen:
            ustate["last_seen_id"] = str(max_id_seen)
        if rate_limited:
            break

    target_dates = [(today - timedelta(days=k)).strftime("%y%m%d") for k in range(0, 15)]
    buckets = bucket_posts_by_date(all_new, target_dates)
    for date_str in sorted(buckets):
        events = filter_feminist_events(buckets[date_str])
        out = append_events_to_file(date_str, events)
        print(f"  {date_str}: {len(buckets[date_str])} posts → {len(events)} events appended → {out}")
    save_state(state, sp)

    pending_uids = [u for u, s in state["uids"].items() if s.get("pending")]
    if rate_limited:
        print(
            "\nRATE LIMITED (account-level throttle; a new cookie for the same account "
            "does NOT reset it). Progress saved — the next --daily run resumes "
            "automatically. Meanwhile you can add events manually via --urls.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if pending_uids:
        print(f"Budget exhausted; resume cursor saved for uids: {','.join(pending_uids)}. "
              "Next --daily run continues automatically.")
```

Wire into `main()`:

```python
    parser.add_argument("--daily", action="store_true",
                        help="incremental fetch since last seen post per UID (cron-safe)")
    parser.add_argument("--budget", type=int, default=None,
                        help="max page fetches this run (daily mode; default 40)")
```

and before existing dispatch:

```python
        if args.daily:
            run_tracker_daily(cookie, budget=args.budget or DAILY_BUDGET)
            return
```

Also replace both legacy "fresh WEIBO_COOKIE from another browser session" error strings with the account-level wording used above.

- [x] **Step 5: Green; full suite; commit + push.**

- [x] **Step 6: CLAUDE.md Stage 1** — add to the run block: `python src/tracker.py --daily             # incremental (cron-safe); resumes budget/rate-limit cursors` and one sentence under Implementation details: state lives in `_pipeline/.tracker-state.json`.

### Task 3: `src/wbfetch.py` anonymous fetcher

**Files:**
- Create: `src/wbfetch.py`
- Create: `src/tests/test_wbfetch.py`
- Modify: `requirements.txt` (add pinned playwright)

- [ ] **Step 1: Install** — `src/venv/bin/pip install playwright` (no `playwright install`: `channel="chrome"` uses `/usr/bin/google-chrome`). Pin exact installed version in `requirements.txt`.

- [ ] **Step 2: Failing tests** (playwright fully mocked; no network):

```python
# src/tests/test_wbfetch.py
import pytest
from unittest.mock import MagicMock, patch
from src.wbfetch import fetch_post, WbFetchError


def make_pw(text="正文内容", author="作者", when="2026-05-28 10:00", fail_first=False):
    pw = MagicMock()
    page = pw.chromium.launch.return_value.new_context.return_value.new_page.return_value
    if fail_first:
        from src.wbfetch import PWTimeout
        page.wait_for_selector.side_effect = [PWTimeout("t"), None]
    def locator(sel):
        loc = MagicMock()
        val = {"detail_wbtext": text, "head_name": author, "head-info_time": when}
        for k, v in val.items():
            if k in sel:
                loc.first.inner_text.return_value = v
                break
        else:
            loc.first.inner_text.return_value = ""
        loc.all.return_value = []
        return loc
    page.locator.side_effect = locator
    cm = MagicMock()
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    return cm


def test_fetch_post_extracts_fields():
    with patch("src.wbfetch.sync_playwright", return_value=make_pw()):
        d = fetch_post("https://weibo.com/1/x")
    assert d["text"] == "正文内容"
    assert d["author"] == "作者"
    assert d["url"] == "https://weibo.com/1/x"


def test_fetch_post_retries_then_succeeds():
    with patch("src.wbfetch.sync_playwright", return_value=make_pw(fail_first=True)):
        d = fetch_post("https://weibo.com/1/x", retries=2)
    assert d["text"] == "正文内容"


def test_fetch_post_raises_after_retries():
    cm = make_pw()
    page = cm.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
    from src.wbfetch import PWTimeout
    page.wait_for_selector.side_effect = PWTimeout("t")
    with patch("src.wbfetch.sync_playwright", return_value=cm):
        with pytest.raises(WbFetchError):
            fetch_post("https://weibo.com/1/x", retries=2)
```

- [ ] **Step 3: Implement `src/wbfetch.py`**

```python
"""Anonymous Weibo post fetcher: headless system Chrome passes the Sina
Visitor System (tourist cookies) — no account, no account-level rate limit.
Discovery (timelines) is NOT possible here; single post URLs only."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TEXT_SEL = '[class*="detail_wbtext"]'


class WbFetchError(Exception):
    pass


def fetch_post(url: str, timeout_ms: int = 30000, retries: int = 3, headless: bool = True) -> dict:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=headless)
                try:
                    ctx = browser.new_context(user_agent=UA, locale="zh-CN")
                    page = ctx.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_selector(TEXT_SEL, timeout=timeout_ms)
                    text = page.locator(TEXT_SEL).first.inner_text()
                    author = page.locator('[class*="head_name"]').first.inner_text()
                    created = page.locator('[class*="head-info_time"]').first.inner_text()
                    images = [
                        img.get_attribute("src") or ""
                        for img in page.locator('article img[class*="picture"]').all()
                    ]
                    return {
                        "url": url,
                        "author": author.strip(),
                        "created_at": created.strip(),
                        "text": " ".join(text.split()),
                        "retweet_text": "",
                        "image_urls": [i for i in images if i],
                    }
                finally:
                    browser.close()
        except PWTimeout as e:
            last_err = e
        except Exception as e:          # visitor flow / chrome launch failures
            last_err = e
    raise WbFetchError(f"failed to fetch {url}: {last_err}")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python src/wbfetch.py <weibo-post-url>...")
        return 2
    for u in argv:
        print(json.dumps(fetch_post(u), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Green (hermetic).** Then live smoke: `src/venv/bin/python src/wbfetch.py https://weibo.com/1699432410/5306536081752889` → expect JSON with 通报 text. If chrome sandbox errors under WSL, add `args=["--no-sandbox"]` to launch. Record outcome in commit message.

- [ ] **Step 5: Commit + push** (include requirements.txt pin; CI stays hermetic — playwright import only, no browser needed).

### Task 4: `tracker.py --urls` mode

**Files:**
- Modify: `src/tracker.py`
- Create: `src/tests/test_tracker_urls.py`
- Modify: `CLAUDE.md`, `.claude/skills/blog-orchestrator/SKILL.md` (document mode)

- [ ] **Step 1: Failing tests**

```python
# src/tests/test_tracker_urls.py
import pytest
from datetime import date
from src.tracker import run_tracker_urls


@pytest.fixture
def env(tmp_path, monkeypatch):
    pipe = tmp_path / "_pipeline"
    (pipe / "events").mkdir(parents=True)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", pipe)
    monkeypatch.setattr(
        "src.tracker.filter_feminist_events",
        lambda posts: [{"title": "事件", "brief": p["text"], "sources": [p["url"]]} for p in posts],
    )
    return pipe


def test_urls_mode_appends_events(env, monkeypatch):
    monkeypatch.setattr(
        "src.tracker._fetch_url_post",
        lambda u: {"url": u, "text": "家暴事件通报", "retweet_text": ""},
    )
    run_tracker_urls(["https://weibo.com/1/a", "https://weibo.com/1/b"], "260702")
    content = (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "## 1." in content and "## 2." in content


def test_urls_mode_skips_failed_fetch(env, monkeypatch, capsys):
    from src.wbfetch import WbFetchError
    def fetch(u):
        if u.endswith("bad"):
            raise WbFetchError("nope")
        return {"url": u, "text": "性侵案进展", "retweet_text": ""}
    monkeypatch.setattr("src.tracker._fetch_url_post", fetch)
    run_tracker_urls(["https://weibo.com/1/ok", "https://weibo.com/1/bad"], "260702")
    assert "## 1." in (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "bad" in capsys.readouterr().err
```

- [ ] **Step 2: Implement** in `src/tracker.py`:

```python
def _fetch_url_post(url: str) -> dict:
    from src.wbfetch import fetch_post
    d = fetch_post(url)
    return {"url": url, "text": d["text"], "retweet_text": d.get("retweet_text", "")}


def run_tracker_urls(urls: list[str], date_str: str) -> None:
    """Anonymous URL-list mode: no cookie, no account, merge-append."""
    from src.wbfetch import WbFetchError
    posts = []
    for u in urls:
        try:
            posts.append(_fetch_url_post(u))
        except WbFetchError as e:
            print(f"  skip {u}: {e}", file=sys.stderr)
    events = filter_feminist_events(posts) if posts else []
    out = append_events_to_file(date_str, events)
    print(f"{date_str}: {len(posts)} posts → {len(events)} events appended → {out}")
```

`main()` additions: `parser.add_argument("--urls", help="comma-separated post URLs or @file (one URL per line); anonymous fetch")`; dispatch before other modes:

```python
        if args.urls:
            raw = args.urls
            if raw.startswith("@"):
                urls = [l.strip() for l in Path(raw[1:]).read_text().splitlines() if l.strip()]
            else:
                urls = [u.strip() for u in raw.split(",") if u.strip()]
            date_arg = args.date or (date.today() - timedelta(days=1)).strftime("%y%m%d")
            run_tracker_urls(urls, date_arg)
            return
```

- [ ] **Step 3: Green; docs (CLAUDE.md Stage 1 run block + pitfalls row: rate-limited → use `--urls`; orchestrator 1b alternative); commit + push.**

### Task 5: Harvest queue + curate/orchestration docs

**Files:**
- Modify: `src/publisher.py`
- Create: `src/tests/test_harvest_queue.py`
- Modify: `.claude/skills/blog-curate/SKILL.md`, `CLAUDE.md`

- [x] **Step 1: Failing test** — reuse `test_publish_finalizes_terminal_date` fixture pattern; after `publish(..., deploy=False)` assert `(root / "harvest-queue.txt").read_text() == "990101-1\n"`; publishing twice doesn't duplicate the line.

- [x] **Step 2: Implement** in `publish()` after `record_published(...)`:

```python
    queue = PIPELINE / "harvest-queue.txt"
    entry = f"{date_str}-{n}"
    existing = queue.read_text(encoding="utf-8").splitlines() if queue.exists() else []
    if entry not in existing:
        queue.open("a", encoding="utf-8").write(entry + "\n")
    print(f"Queued {entry} for skill harvest — run blog-curate to distill corrections")
```

- [x] **Step 3: blog-curate SKILL.md** — add a `## Harvest (feed the notes)` section before "Curation Process":

```markdown
## Harvest (feed the notes)

`_pipeline/harvest-queue.txt` lists published events (`YYMMDD-N`) whose corrections
have not yet been distilled. For each entry (files may be in `_pipeline/` or
`_pipeline_archive/` after archiving):

1. Read every review version's user input (`## 人类意见` / `<!-- [USER]: -->`) and
   diff draft v1 against the final version (frontmatter and structure included).
2. Distill into the relevant skill's `notes.md` as **general principles only** —
   state the rule and its why; never case names, dates, or one-off specifics.
   If a correction cannot be stated as a general rule, do not record it.
3. Remove processed entries from the queue.

**Exception gate (mandatory):** a rule that holds for most posts but conflicts
with even one published post or user decision must NOT be silently adopted or
dropped — list the exception cases and ask the user to keep/drop/refine it.
The same gate applies at promotion time for `[CANDIDATE]` entries.
```

- [x] **Step 4: CLAUDE.md Stage 5** — append: `After a successful publish the event is appended to _pipeline/harvest-queue.txt; run the blog-curate skill periodically to distill queued corrections into skill notes.`

- [x] **Step 5: Green; commit + push.**

### Task 6: Daily cron prep (no install)

**Files:**
- Create: `setup/cron.md`

- [ ] Write `setup/cron.md`: the crontab line
  `15 9 * * * cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/tracker.py --daily >> _pipeline/tracker.log 2>&1`,
  install command (`crontab -e`), WSL caveats (cron service must run: `sudo service cron start` or systemd `sudo systemctl enable --now cron`; machine must be on; missed days harmless — state resumes), and the Windows Task Scheduler alternative (`wsl.exe -d <distro> -- bash -lc '...'`). Commit + push.

### Task 7: Distillation (analysis, user-gated)

**Files:**
- Create: `_pipeline/skill-evolution-questions.md`
- Modify: `.claude/skills/blog-write/SKILL.md` (only zero-counterexample rules)

- [ ] **Step 1:** Extract all user corrections: every `## 人类意见`/`<!-- [USER]: -->` block in `_pipeline{,_archive}/review/`, plus v1→final frontmatter diffs (categories, date, tags) via a throwaway `src/venv/bin/python` script writing `/tmp/corrections.md`.
- [ ] **Step 2:** Group into candidate principles; draft a category rubric (S/A/B/C/D/N boundary criteria + why, 2 contrastive examples each from published posts).
- [ ] **Step 3:** Validate: re-classify all published posts in `source/_posts/` with the rubric; record agreement vs final categories.
- [ ] **Step 4:** Zero-counterexample rules → integrate into blog-write SKILL.md sections (Categories/Style). Rules with exceptions → `_pipeline/skill-evolution-questions.md`, one entry per rule: statement, supporting count, exception cases, keep/drop/refine question.
- [ ] **Step 5:** Commit + push. Handoff summary points user at the questions file.

## Self-Review Notes

- Spec coverage: A1→Task 3, A2→Task 4, A3→Task 2, A4→Task 6, B1→Task 7, B2→Task 5, C→Task 1. CLAUDE.md pitfalls row for account-level throttle already committed (c7cfdff).
- Types: `fetch_post` returns dict consumed by `_fetch_url_post` (Task 4) — field names match. `run_tracker_daily(cookie, budget, state_path, today)` signature matches tests. `PWTimeout` exported from wbfetch for tests.
- Live smoke test in Task 3 Step 4 is best-effort: chrome launch happens inside python (allowed command path); failure does not block the hermetic suite.
