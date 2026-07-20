from __future__ import annotations
import os
import sys
import json
import time
import random
import argparse
import email.utils
import re
import yaml
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from src.utils.web import WebClient
from src.utils.pipeline import events_path
from src.utils import ledger

WEIBO_API = "https://m.weibo.cn/api/container/getIndex"
# Date-filtered per-UID post search (the weibo.com profile 筛选 feature).
# Accepts the same weibo.cn-domain cookie; visitors get an empty {} instead
# of data, so ok!=1 must be treated as an error, never as "no posts".
SEARCHPROFILE_API = "https://weibo.com/ajax/statuses/searchProfile"
FEMINIST_KEYWORDS = ["女性", "女权", "性别", "婚姻", "家暴", "性侵", "拐卖", "生育", "就业歧视"]
CN_TZ = timezone(timedelta(hours=8))
PAGINATION_MAX_PAGES = 20
PAGINATION_DELAY_SEC = 3.0   # base; actual = uniform(base, base*3) → 3–9s per page
INTER_UID_DELAY_SEC = 5.0    # base; actual = uniform(base, base*3) → 5–15s between UIDs
URL_FETCH_DELAY_SEC = 3.0    # base; actual = uniform(base, base*3) → 3–9s between --urls fetches


class RateLimited(Exception):
    """Weibo throttle hit (ok:-100 captcha challenge).

    What is actually known (observed, not measured):
    - Triggers on request volume AND frequency. The threshold is unknown; no
      one has measured it. PAGINATION_DELAY_SEC / INTER_UID_DELAY_SEC /
      DAILY_BUDGET are guesses, not calibration.
    - Waiting does NOT clear it. There is no cooldown window. (Earlier versions
      of this file claimed "persists 6–24h" — that was fiction, never observed.)
    - Refreshing the cookie for the same account cleared it the first few
      times, then stopped working. Once refresh stops working the account is
      spent and a NEW ACCOUNT is needed. Whether a spent account ever recovers
      is unknown.

    So the account is a consumable, and repeated hits are what burn it — the
    cost of tripping this is not a wait, it is an account. Budget accordingly:
    routine daily tracking is a handful of requests, while deep backfills are
    where accounts die. --urls mode (src/wbfetch.py) is anonymous, uses no
    account, and is unaffected.
    """


def parse_created_at(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(CN_TZ)
    except (TypeError, ValueError):
        return None


def parse_weibo_cards(cards: list[dict], uid: str) -> list[dict]:
    posts = []
    for card in cards:
        mblog = card.get("mblog")
        if not mblog:
            continue
        text = WebClient.extract_text(mblog.get("text", ""))
        retweet = mblog.get("retweeted_status") or {}
        retweet_text = WebClient.extract_text(retweet.get("text", "")) if retweet else ""
        created_dt = parse_created_at(mblog.get("created_at", ""))
        is_top = bool(mblog.get("isTop") or mblog.get("title", {}).get("text") == "置顶")
        posts.append({
            "id": mblog.get("id", ""),
            "url": f"https://weibo.com/{uid}/{mblog.get('bid', '')}",
            "text": text,
            "retweet_text": retweet_text,
            "created_dt": created_dt,
            "is_top": is_top,
        })
    return posts


def fetch_weibo_posts(web: WebClient, uid: str, page: int = 1) -> list[dict]:
    url = f"{WEIBO_API}?type=uid&value={uid}&containerid=107603{uid}&page={page}"
    data = web.fetch_json(url)
    if data.get("ok") == -100 and "captcha" in (data.get("url") or ""):
        raise RateLimited()
    cards = data.get("data", {}).get("cards", [])
    return parse_weibo_cards(cards, uid)


def parse_searchprofile_items(items: list[dict], uid: str) -> list[dict]:
    """Map weibo.com ajax searchProfile items to the tracker post shape."""
    posts = []
    for m in items:
        retweet = m.get("retweeted_status") or {}
        posts.append({
            "id": str(m.get("idstr") or m.get("id") or ""),
            "url": f"https://weibo.com/{uid}/{m.get('mblogid', '')}",
            "text": m.get("text_raw") or WebClient.extract_text(m.get("text", "")),
            "retweet_text": retweet.get("text_raw")
                or (WebClient.extract_text(retweet.get("text", "")) if retweet else ""),
            "created_dt": parse_created_at(m.get("created_at", "")),
            "is_top": bool(m.get("isTop")),
        })
    return posts


def fetch_weibo_posts_by_day(
    web: WebClient,
    uid: str,
    day: date,
    max_pages: int = PAGINATION_MAX_PAGES,
) -> list[dict]:
    """Date-filtered profile fetch (searchProfile) — O(当日帖量) requests,
    no backfill walk from today. Works with the existing weibo.cn cookie.

    An expired/rejected cookie yields HTTP 200 with `{}` (no `ok` field), so
    anything but ok=1 raises instead of returning [] — a silent [] would let
    callers wrongly attest 无事件 for a day that was never actually checked.
    """
    t0 = int(datetime.combine(day, datetime.min.time(), tzinfo=CN_TZ).timestamp())
    headers = {
        "Referer": f"https://weibo.com/u/{uid}",
        "Accept": "application/json, text/plain, */*",
    }
    posts: list[dict] = []
    for page in range(1, max_pages + 1):
        url = (f"{SEARCHPROFILE_API}?uid={uid}&page={page}"
               f"&starttime={t0}&endtime={t0 + 86400 - 1}")
        data = web.fetch_json(url, headers=headers)
        if data.get("ok") == -100 and "captcha" in (data.get("url") or ""):
            raise RateLimited()
        if data.get("ok") != 1:
            raise WebClient.FetchError(
                f"searchProfile refused (cookie expired/未登录?): {str(data)[:200]}")
        lst = (data.get("data") or {}).get("list") or []
        if not lst:
            break
        posts.extend(parse_searchprofile_items(lst, uid))
        time.sleep(random.uniform(PAGINATION_DELAY_SEC, PAGINATION_DELAY_SEC * 3))
    return posts


def fetch_weibo_posts_paginated(
    web: WebClient,
    uid: str,
    cutoff: datetime,
    max_pages: int = PAGINATION_MAX_PAGES,
) -> tuple[list[dict], bool]:
    """Walk pages until the oldest non-pinned post is older than cutoff.

    Returns (posts, complete). complete=False means the walk stopped short of
    the cutoff (page cap exhausted, or a fetch error) — posts older than the
    oldest one returned may exist unfetched, so callers must not treat the
    uncovered dates as "checked, no events". An empty/overlapping page counts
    as complete: the feed simply has nothing older.
    """
    all_posts: list[dict] = []
    seen_ids: set[str] = set()
    complete = False
    for page in range(1, max_pages + 1):
        try:
            posts = fetch_weibo_posts(web, uid, page=page)
        except WebClient.FetchError as e:
            print(f"  uid {uid} page {page}: fetch error {e}")
            break
        if not posts:
            complete = True
            break
        new_posts = [p for p in posts if p["id"] and p["id"] not in seen_ids]
        if not new_posts:
            complete = True
            break
        for p in new_posts:
            seen_ids.add(p["id"])
        all_posts.extend(new_posts)
        # Find oldest non-pinned post on this page
        dated = [p["created_dt"] for p in new_posts if p["created_dt"] and not p["is_top"]]
        if dated and min(dated) < cutoff:
            complete = True
            break
        if page < max_pages:
            time.sleep(random.uniform(PAGINATION_DELAY_SEC, PAGINATION_DELAY_SEC * 3))
    return all_posts, complete


def bucket_posts_by_date(posts: list[dict], target_dates: list[str]) -> dict[str, list[dict]]:
    """Group posts by YYMMDD created date. Skip pinned posts (out of order).
    Only returns buckets for dates in `target_dates`."""
    targets = set(target_dates)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        if p["is_top"] or not p["created_dt"]:
            continue
        yymmdd = p["created_dt"].strftime("%y%m%d")
        if yymmdd in targets:
            buckets[yymmdd].append(p)
    return dict(buckets)


def _extract_events_json(content: str) -> list[dict] | None:
    """Pull the events array out of an LLM reply.

    The reply may wrap the array in a ``` fence or surround it with prose that
    itself contains bracketed fragments (e.g. echoed "[1]" post indices), so
    never slice blindly from the first '[' to the last ']'. Returns None when
    no valid events array is found (caller retries).
    """
    def _valid(arr) -> bool:
        return isinstance(arr, list) and all(
            isinstance(e, dict) and {"title", "brief", "sources"} <= e.keys()
            for e in arr
        )

    # Fenced blocks first — the least ambiguous form.
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", content, re.DOTALL):
        try:
            arr = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if _valid(arr):
            return arr
    # Otherwise walk balanced [...] candidates from the end of the reply
    # backwards — the final answer comes last, earlier brackets are usually
    # echoed prose references.
    end = len(content)
    for _ in range(10):
        end = content.rfind("]", 0, end)
        if end == -1:
            return None
        depth = 0
        start = -1
        for i in range(end, -1, -1):
            if content[i] == "]":
                depth += 1
            elif content[i] == "[":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start != -1:
            try:
                arr = json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                arr = None
            if arr is not None and _valid(arr):
                return arr
    return None


def filter_feminist_events(posts: list[dict]) -> list[dict]:
    """Use claude CLI to filter and deduplicate feminist-relevant events."""
    if not posts:
        return []
    import subprocess
    posts_text = "\n\n".join(
        f"#{i+1} URL: {p['url']}\nText: {p['text']}\nRetweet: {p['retweet_text']}"
        for i, p in enumerate(posts)
    )
    keywords = "、".join(FEMINIST_KEYWORDS)
    prompt = f"""以下是微博帖子。请筛选出与女性权益、性别议题相关的**近期具体事件**，关键词包括：{keywords}。

**收录标准（同时满足）：**
1. 是具体事件（有明确当事人、发生地点或机构），不是泛泛的性别议题讨论或科普
2. 是近期发生或有新进展的事件（新闻报道、判决、声明、案发等）；若帖子讨论的是旧事件且无新进展，则不收录

**排除以下内容：**
- 对历史事件或旧案的回顾/感慨（无新进展）
- 泛化的性别讨论、观点分享、情绪宣泄
- 对某议题的一般性科普或评论

对于相同事件的多个帖子，请合并为一条。每条事件用以下格式输出（JSON数组）：
[
  {{
    "title": "标题简述（10字以内）",
    "brief": "一两句话概述，注明最新进展",
    "sources": ["url1", "url2"]
  }}
]

如无符合条件的内容，返回空数组 []。

帖子列表：
{posts_text}"""

    for attempt in range(3):
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--model", "claude-haiku-4-5-20251001", "--output-format", "text"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            content = result.stdout.strip()
            events = _extract_events_json(content)
            if events is None:
                raise ValueError(
                    f"no valid JSON events array in LLM reply: {content[:200]!r}"
                )
            return events
        except Exception as e:
            if attempt == 2:
                raise
            wait = random.uniform(10, 20) * (attempt + 1)
            print(f"  LLM attempt {attempt + 1} failed ({e}), retrying in {wait:.0f}s...")
            time.sleep(wait)


def format_events(date_str: str, events: list[dict]) -> str:
    year = "20" + date_str[:2]
    month = date_str[2:4]
    day = date_str[4:6]
    lines = [f"# Events — {year}-{month}-{day}\n"]
    for i, ev in enumerate(events, 1):
        sources = " ".join(f"[{url}]" for url in ev.get("sources", []))
        lines.append(
            f"## {ev.get('index', i)}. {ev['title']}\n"
            f"**Sources**: {sources}\n"
            f"**Brief**: {ev['brief']}\n"
        )
    return "\n".join(lines)


_SOURCES_LINE_RE = re.compile(r"^\*\*Sources\*\*:(.*)$", re.MULTILINE)


def known_source_urls(date_str: str) -> set[str]:
    """All source URLs already recorded for a date — live events md AND the
    archived one (a fully-terminal date keeps its md only in the archive)."""
    from src.utils import pipeline as _pl
    urls: set[str] = set()
    for path in (events_path(date_str), _pl.ARCHIVE / "events" / f"{date_str}.md"):
        if path.exists():
            for m in _SOURCES_LINE_RE.finditer(path.read_text(encoding="utf-8")):
                urls.update(re.findall(r"\[([^\]]+)\]", m.group(1)))
    return urls


def dedupe_events(date_str: str, events: list[dict]) -> list[dict]:
    """Cross-run dedup: drop events whose source posts are already recorded for
    this date in a previous run (overlapping runs re-filter the same posts and
    would otherwise re-open adjudicated events as fresh candidates). Events
    without sources are kept — nothing to match on (e.g. manual briefs)."""
    known = known_source_urls(date_str)
    if not known:
        return events
    kept = []
    for ev in events:
        if set(ev.get("sources") or []) & known:
            print(f"  {date_str}: 跳过重复事件（来源已记录）：{ev['title']}")
        else:
            kept.append(ev)
    return kept


def write_events_file(date_str: str, events: list[dict]) -> Path | None:
    """写 events md（人读内容）并同步账本行。空事件：只记"无事件"行，不写 md。

    编号从账本已有的最大事件编号之后续接（而非总是从 1 开始）：若该日期的
    events md 已被归档（事件到终态后）但账本行仍在，从 1 编号会撞上旧行，
    ledger.add_event 静默 no-op，新事件就此从账本中消失。全新日期 offset 为
    0，行为不变。
    """
    if not events:
        ledger.record_no_events(date_str)
        return None
    events = dedupe_events(date_str, events)
    if not events:
        # 有事件但全是重复：不是"无事件"，不写、不记 无事件 行
        out = events_path(date_str)
        return out if out.exists() else None
    offset = ledger.max_index(date_str)
    numbered = [dict(e, index=i + 1 + offset) for i, e in enumerate(events)]
    out = events_path(date_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_events(date_str, numbered), encoding="utf-8")
    for ev in numbered:
        if not ledger.add_event(date_str, ev["index"], ev["title"]):
            print(f"  WARNING: 账本已存在 {date_str}-{ev['index']}，新事件未记录：{ev['title']}")
    return out


def count_existing_events(path: Path) -> int:
    """Return the highest event index already present in an events file (0 if none)."""
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    indexes = [int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", text, re.MULTILINE)]
    return max(indexes) if indexes else 0


def append_events_to_file(date_str: str, new_events: list[dict]) -> Path | None:
    """Append events to an existing file, continuing the index from where it left off.
    Creates the file if it doesn't exist.

    Never records 无事件: append callers (--daily buckets, --urls, --merge)
    hold partial samples of a day, which cannot attest "checked, no events".
    An empty append onto a missing file is a no-op and the date stays
    untracked. (Range mode marks 无事件 itself, gated on attested coverage.)
    """
    out = events_path(date_str)
    if not new_events:
        return out if out.exists() else None
    new_events = dedupe_events(date_str, new_events)
    if not new_events:
        return out if out.exists() else None
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        return write_events_file(date_str, new_events)
    offset = max(count_existing_events(out), ledger.max_index(date_str))
    numbered = [dict(e, index=offset + i + 1) for i, e in enumerate(new_events)]
    # format_events re-numbers from 1, so we build the appended block manually
    lines = []
    for i, ev in enumerate(numbered):
        sources = " ".join(f"[{url}]" for url in ev.get("sources", []))
        lines.append(
            f"## {ev['index']}. {ev['title']}\n"
            f"**Sources**: {sources}\n"
            f"**Brief**: {ev['brief']}\n"
        )
    existing = out.read_text(encoding="utf-8").rstrip() + "\n\n"
    out.write_text(existing + "\n".join(lines), encoding="utf-8")
    for ev in numbered:
        ledger.add_event(date_str, ev["index"], ev["title"])
    return out


def run_tracker_day(
    date_str: str,
    cookie: str,
    uids: list[str] | None = None,
    merge: bool = False,
) -> None:
    """Single-day mode: date-filtered fetch per UID via searchProfile.

    Coverage attestation: all UIDs fetched cleanly + 0 events → 无事件 row;
    any fetch error → no attestation (the date stays visibly untracked).
    """
    if uids is None:
        uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    day = _parse_yymmdd(date_str)
    web = WebClient(cookie=cookie)
    all_posts: list[dict] = []
    covered = True
    for i, uid in enumerate(uids):
        if i > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        try:
            posts = fetch_weibo_posts_by_day(web, uid, day)
        except WebClient.FetchError as e:
            covered = False
            print(f"  uid {uid}: fetch error {e}", file=sys.stderr)
            continue
        print(f"  uid {uid}: {len(posts)} posts on {day}")
        all_posts.extend(posts)
    events = filter_feminist_events(all_posts)
    if events:
        writer = append_events_to_file if merge else write_events_file
        out = writer(date_str, events)
        print(f"{date_str}: {len(all_posts)} posts → {len(events)} events → {out}")
    elif covered:
        ledger.record_no_events(date_str)
        print(f"{date_str}: {len(all_posts)} posts → 0 events →（无事件行）")
    else:
        print(f"{date_str}: 覆盖不完整，未标记无事件（仍显示为未追踪）", file=sys.stderr)


def run_tracker_range(
    end_date: date,
    days: int,
    cookie: str,
    uids: list[str] | None = None,
    merge: bool = False,
) -> None:
    """Range mode: paginate to cover `days` back from `end_date`, bucket per date,
    LLM-filter each bucket, write one events file per date.

    uids: override TRACKED_UIDS for partial re-runs.
    merge: append to existing events files instead of overwriting.
    """
    if uids is None:
        uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    target_dates = [(end_date - timedelta(days=i)).strftime("%y%m%d") for i in range(days)]
    cutoff_date = end_date - timedelta(days=days - 1)
    cutoff = datetime.combine(cutoff_date, datetime.min.time(), tzinfo=CN_TZ)
    web = WebClient(cookie=cookie)
    all_posts = []
    skipped_uids: list[str] = []
    # Earliest date every fetched UID fully covered. A 无事件 row asserts
    # "checked this day, found nothing", so it may only be written for dates
    # >= covered_from. None = nothing attested (rate-limited / truncated with
    # no datable posts).
    covered_from: date | None = cutoff_date
    for i, uid in enumerate(uids):
        if i > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        print(f"Paginating uid {uid} until {cutoff.date()} ...")
        try:
            posts, complete = fetch_weibo_posts_paginated(web, uid, cutoff)
        except RateLimited:
            skipped_uids = uids[i:]
            covered_from = None
            print(f"  uid {uid}: RATE LIMITED — writing partial results and stopping", file=sys.stderr)
            break
        all_posts.extend(posts)
        if complete:
            print(f"  uid {uid}: {len(posts)} posts collected")
            continue
        # Truncated walk: only dates strictly newer than the oldest fetched
        # post are fully covered (the oldest post's own day may have older
        # unfetched posts).
        dated = [p["created_dt"].date() for p in posts if p["created_dt"] and not p["is_top"]]
        if dated:
            uid_covered_from = min(dated) + timedelta(days=1)
            if covered_from is not None:
                covered_from = max(covered_from, uid_covered_from)
            print(f"  uid {uid}: {len(posts)} posts collected（截断：未走到 {cutoff.date()}，"
                  f"完整覆盖仅到 {uid_covered_from}）")
        else:
            covered_from = None
            print(f"  uid {uid}: 截断且无带日期帖子，本轮不标记任何无事件", file=sys.stderr)
    buckets = bucket_posts_by_date(all_posts, target_dates)
    print(f"Total posts: {len(all_posts)}; bucketed dates: {sorted(buckets.keys())}")
    writer = append_events_to_file if merge else write_events_file
    for date_str in sorted(target_dates):
        bucket = buckets.get(date_str, [])
        events = filter_feminist_events(bucket) if bucket else []
        if events:
            out = writer(date_str, events)
            action = "appended" if merge else "wrote"
            print(f"  {date_str}: {len(bucket)} posts → {len(events)} events {action} → {out}")
        elif covered_from is not None and _parse_yymmdd(date_str) >= covered_from:
            ledger.record_no_events(date_str)
            print(f"  {date_str}: {len(bucket)} posts → 0 events →（无事件行）")
        else:
            print(f"  {date_str}: 覆盖不完整，跳过（未标记无事件，仍显示为未追踪）")
    if skipped_uids:
        skipped = ",".join(skipped_uids)
        print(
            f"\nRATE LIMITED. Partial results written above (skipped uids: {skipped}).\n"
            "Waiting does NOT clear this — there is no cooldown window.\n"
            "Try refreshing this account's cookie, then complete with:\n"
            f"  python src/tracker.py [args] --uids {skipped} --merge\n"
            "Cookie refresh has cleared it before, but stops working after repeated\n"
            "hits — at that point the account is spent and needs replacing.\n"
            "Do not retry blind: repeated hits are what burn the account.\n"
            "To add events with no account at all, use --urls (anonymous, unaffected).",
            file=sys.stderr,
        )
        sys.exit(2)


def _fetch_url_post(url: str) -> dict:
    from src.wbfetch import fetch_post
    d = fetch_post(url)
    return {"url": url, "text": d["text"], "retweet_text": d.get("retweet_text", "")}


def run_tracker_urls(urls: list[str], date_str: str) -> None:
    """Anonymous URL-list mode: no cookie, no account, merge-append.

    The user supplies public weibo.com post URLs; each is fetched via
    src/wbfetch.py (headless Chrome, visitor cookies) and run through the
    same Haiku filter as tracked posts.
    """
    from src.wbfetch import WbFetchError
    posts = []
    for i, u in enumerate(urls):
        if i > 0:
            time.sleep(random.uniform(URL_FETCH_DELAY_SEC, URL_FETCH_DELAY_SEC * 3))
        try:
            posts.append(_fetch_url_post(u))
        except WbFetchError as e:
            print(f"  skip {u}: {e}", file=sys.stderr)
    events = filter_feminist_events(posts) if posts else []
    out = append_events_to_file(date_str, events)
    print(f"{date_str}: {len(posts)} posts → {len(events)} events appended → {out or '（0 收录，未标记无事件）'}")


DAILY_BUDGET = 40
DAILY_FIRST_RUN_DAYS = 3
DAILY_BUCKET_WINDOW_DAYS = 15


def run_tracker_daily(
    cookie: str,
    budget: int = DAILY_BUDGET,
    state_path: Path | None = None,
    today: date | None = None,
) -> None:
    """Incremental fetch since last_seen_id per UID, budget-capped, merge-append.

    Budget exhaustion persists a resume cursor and returns normally (the next
    run continues automatically). RateLimited persists the cursor and exits 2 —
    but the cursor only helps if the account survives: waiting does not clear
    the throttle, and repeated hits burn the account outright. See RateLimited.
    """
    from src.utils.tracker_state import load_state, save_state, state_path as _sp
    sp = state_path or _sp()
    state = load_state(sp)
    today = today or date.today()
    uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    # UIDs left with a resume cursor by a previous run go first, so a heavy
    # account at the front of TRACKED_UIDS cannot starve the others.
    uids.sort(key=lambda u: not (state["uids"].get(u) or {}).get("pending"))
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
        while True:
            if remaining <= 0:
                ustate["pending"] = {"next_page": page}
                break
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
                or (
                    last_seen is None
                    and organic
                    and min(p["created_dt"] for p in organic) < first_run_cutoff
                )
            )
            if reached_old:
                ustate["pending"] = None
                break
            page += 1
            if remaining > 0:
                time.sleep(random.uniform(PAGINATION_DELAY_SEC, PAGINATION_DELAY_SEC * 3))
        if max_id_seen:
            ustate["last_seen_id"] = str(max_id_seen)
        if rate_limited:
            break

    target_dates = [
        (today - timedelta(days=k)).strftime("%y%m%d")
        for k in range(DAILY_BUCKET_WINDOW_DAYS)
    ]
    buckets = bucket_posts_by_date(all_new, target_dates)
    for date_str in sorted(buckets):
        events = filter_feminist_events(buckets[date_str])
        out = append_events_to_file(date_str, events)
        print(f"  {date_str}: {len(buckets[date_str])} posts → {len(events)} events appended → {out or '（0 收录，未标记无事件）'}")
    save_state(state, sp)

    pending_uids = [u for u, s in state["uids"].items() if s.get("pending")]
    if rate_limited:
        print(
            "\nRATE LIMITED. The resume cursor is saved, but do NOT simply re-run: "
            "waiting does not clear the throttle, and a blind retry spends another "
            "strike on the account. Try refreshing this account's cookie first — "
            "that has worked before, but stops working after repeated hits, at "
            "which point the account is spent and needs replacing. Weibo throttles "
            "on request volume AND frequency, so consider a smaller --budget. "
            "--urls (anonymous, no account) is unaffected.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if pending_uids:
        print(
            f"Budget exhausted; resume cursor saved for uids: {','.join(pending_uids)}. "
            "Next --daily run continues automatically."
        )


def _parse_yymmdd(s: str) -> date:
    return datetime.strptime(s, "%y%m%d").date()


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")
    parser = argparse.ArgumentParser(description="Track feminist events from Weibo UIDs.")
    parser.add_argument("date", nargs="*",
                        help="one or more dates YYMMDD (default: yesterday); date-filtered "
                             "fetch per day, O(当日帖量) requests even for old dates")
    parser.add_argument("--days", type=int, help="walk back N days from --end (range mode)")
    parser.add_argument("--end", help="end date YYMMDD for range mode (default: yesterday)")
    parser.add_argument("--uids", help="comma-separated UID override; for partial re-runs")
    parser.add_argument("--merge", action="store_true", help="append to existing events files")
    parser.add_argument("--daily", action="store_true",
                        help="incremental fetch since last seen post per UID (cron-safe; resumes cursors)")
    parser.add_argument("--budget", type=int, default=None,
                        help="max page fetches this run (daily mode; default 40)")
    parser.add_argument("--urls",
                        help="comma-separated weibo.com post URLs or @file (one per line); "
                             "anonymous fetch, no cookie needed")
    args = parser.parse_args()

    cookie = os.environ.get("WEIBO_COOKIE", "")

    try:
        if args.urls:
            raw = args.urls
            if raw.startswith("@"):
                urls = [l.strip() for l in Path(raw[1:]).read_text(encoding="utf-8").splitlines() if l.strip()]
            else:
                urls = [u.strip() for u in raw.split(",") if u.strip()]
            date_arg = args.date[0] if args.date else (date.today() - timedelta(days=1)).strftime("%y%m%d")
            run_tracker_urls(urls, date_arg)
        elif args.daily:
            run_tracker_daily(cookie, budget=args.budget or DAILY_BUDGET)
        elif args.days:
            end_date = _parse_yymmdd(args.end) if args.end else (date.today() - timedelta(days=1))
            uids = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else None
            run_tracker_range(end_date, args.days, cookie, uids=uids, merge=args.merge)
        else:
            dates = args.date or [(date.today() - timedelta(days=1)).strftime("%y%m%d")]
            uids = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else None
            for i, date_arg in enumerate(dates):
                if i > 0:
                    time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
                run_tracker_day(date_arg, cookie, uids=uids, merge=args.merge)
    except RateLimited:
        print(
            "\nRATE LIMITED. Waiting does NOT clear this — there is no cooldown window.\n"
            "Try refreshing this account's cookie, then re-run with:\n"
            "  python src/tracker.py [args] --merge\n"
            "Cookie refresh has cleared it before, but stops working after repeated\n"
            "hits — at that point the account is spent and needs replacing.\n"
            "Do not retry blind: repeated hits are what burn the account.\n"
            "To add events with no account at all, use --urls (anonymous, unaffected).",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
