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
from src.utils.pipeline import events_path, set_state

WEIBO_API = "https://m.weibo.cn/api/container/getIndex"
FEMINIST_KEYWORDS = ["女性", "女权", "性别", "婚姻", "家暴", "性侵", "拐卖", "生育", "就业歧视"]
CN_TZ = timezone(timedelta(hours=8))
PAGINATION_MAX_PAGES = 20
PAGINATION_DELAY_SEC = 3.0   # base; actual = uniform(base, base*3) → 3–9s per page
INTER_UID_DELAY_SEC = 5.0    # base; actual = uniform(base, base*3) → 5–15s between UIDs


class RateLimited(Exception):
    """Weibo per-cookie throttle hit (ok:-100 captcha challenge)."""


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


def fetch_weibo_posts_paginated(
    web: WebClient,
    uid: str,
    cutoff: datetime,
    max_pages: int = PAGINATION_MAX_PAGES,
) -> list[dict]:
    """Walk pages until the oldest non-pinned post is older than cutoff."""
    all_posts: list[dict] = []
    seen_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        try:
            posts = fetch_weibo_posts(web, uid, page=page)
        except WebClient.FetchError as e:
            print(f"  uid {uid} page {page}: fetch error {e}")
            break
        if not posts:
            break
        new_posts = [p for p in posts if p["id"] and p["id"] not in seen_ids]
        if not new_posts:
            break
        for p in new_posts:
            seen_ids.add(p["id"])
        all_posts.extend(new_posts)
        # Find oldest non-pinned post on this page
        dated = [p["created_dt"] for p in new_posts if p["created_dt"] and not p["is_top"]]
        if dated and min(dated) < cutoff:
            break
        if page < max_pages:
            time.sleep(random.uniform(PAGINATION_DELAY_SEC, PAGINATION_DELAY_SEC * 3))
    return all_posts


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


def filter_feminist_events(posts: list[dict]) -> list[dict]:
    """Use claude CLI to filter and deduplicate feminist-relevant events."""
    if not posts:
        return []
    import subprocess
    posts_text = "\n\n".join(
        f"[{i+1}] URL: {p['url']}\nText: {p['text']}\nRetweet: {p['retweet_text']}"
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
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            return json.loads(content[start:end])
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
            f"## {i}. {ev['title']}\n"
            f"**Sources**: {sources}\n"
            f"**Brief**: {ev['brief']}\n"
        )
    return "\n".join(lines)


def write_events_file(date_str: str, events: list[dict]) -> Path:
    numbered = [dict(e, index=i + 1) for i, e in enumerate(events)]
    out = events_path(date_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_events(date_str, numbered), encoding="utf-8")
    return out


def count_existing_events(path: Path) -> int:
    """Return the highest event index already present in an events file (0 if none)."""
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    indexes = [int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", text, re.MULTILINE)]
    return max(indexes) if indexes else 0


def append_events_to_file(date_str: str, new_events: list[dict]) -> Path:
    """Append events to an existing file, continuing the index from where it left off.
    Creates the file if it doesn't exist."""
    out = events_path(date_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        return write_events_file(date_str, new_events)
    if not new_events:
        return out
    offset = count_existing_events(out)
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
    return out


def run_tracker(date_str: str, cookie: str) -> None:
    """Single-date mode: fetch current page only, write to date_str events file."""
    tracked_uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    web = WebClient(cookie=cookie)
    all_posts = []
    for i, uid in enumerate(tracked_uids):
        if i > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        try:
            all_posts.extend(fetch_weibo_posts(web, uid))
        except WebClient.FetchError as e:
            print(f"Warning: failed to fetch uid {uid}: {e}")
    events = filter_feminist_events(all_posts)
    out = write_events_file(date_str, events)
    set_state("20" + date_str)
    print(f"Wrote {len(events)} events to {out}")


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
    for i, uid in enumerate(uids):
        if i > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        print(f"Paginating uid {uid} until {cutoff.date()} ...")
        try:
            posts = fetch_weibo_posts_paginated(web, uid, cutoff)
        except RateLimited:
            skipped_uids = uids[i:]
            print(f"  uid {uid}: RATE LIMITED — writing partial results and stopping", file=sys.stderr)
            break
        print(f"  uid {uid}: {len(posts)} posts collected")
        all_posts.extend(posts)
    buckets = bucket_posts_by_date(all_posts, target_dates)
    print(f"Total posts: {len(all_posts)}; bucketed dates: {sorted(buckets.keys())}")
    writer = append_events_to_file if merge else write_events_file
    for date_str in sorted(target_dates):
        bucket = buckets.get(date_str, [])
        events = filter_feminist_events(bucket) if bucket else []
        out = writer(date_str, events)
        action = "appended" if merge else "wrote"
        print(f"  {date_str}: {len(bucket)} posts → {len(events)} events {action} → {out}")
    if skipped_uids:
        skipped = ",".join(skipped_uids)
        print(
            f"\nRATE LIMITED. Partial results written above (skipped uids: {skipped}).\n"
            f"Wait 6–24h, then complete with: python src/tracker.py [args] --uids {skipped} --merge\n"
            "Do not retry now — additional requests extend the window.\n"
            "The throttle is account-level: a new cookie for the same account does NOT reset it.\n"
            "To add events immediately, use --urls (anonymous fetch, unaffected).",
            file=sys.stderr,
        )
        sys.exit(2)
    set_state("20" + end_date.strftime("%y%m%d"))


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
    for u in urls:
        try:
            posts.append(_fetch_url_post(u))
        except WbFetchError as e:
            print(f"  skip {u}: {e}", file=sys.stderr)
    events = filter_feminist_events(posts) if posts else []
    out = append_events_to_file(date_str, events)
    print(f"{date_str}: {len(posts)} posts → {len(events)} events appended → {out}")


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
    run continues automatically). RateLimited persists the cursor and exits 2.
    The throttle is account-level — a new cookie for the same account does not
    reset it, so no cookie-swap advice is given.
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
        print(f"  {date_str}: {len(buckets[date_str])} posts → {len(events)} events appended → {out}")
    save_state(state, sp)

    pending_uids = [u for u, s in state["uids"].items() if s.get("pending")]
    if rate_limited:
        print(
            "\nRATE LIMITED (account-level throttle; a new cookie for the same "
            "account does NOT reset it). Progress saved — the next --daily run "
            "resumes automatically. Meanwhile you can add events manually with "
            "--urls (anonymous, unaffected by the throttle).",
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
    parser.add_argument("date", nargs="?", help="single date YYMMDD (default: yesterday)")
    parser.add_argument("--days", type=int, help="walk back N days from --end (range mode)")
    parser.add_argument("--end", help="end date YYMMDD for range mode (default: yesterday)")
    parser.add_argument("--uids", help="comma-separated UID override (range mode); for partial re-runs")
    parser.add_argument("--merge", action="store_true", help="append to existing events files (range mode)")
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
            date_arg = args.date or (date.today() - timedelta(days=1)).strftime("%y%m%d")
            run_tracker_urls(urls, date_arg)
        elif args.daily:
            run_tracker_daily(cookie, budget=args.budget or DAILY_BUDGET)
        elif args.days:
            end_date = _parse_yymmdd(args.end) if args.end else (date.today() - timedelta(days=1))
            uids = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else None
            run_tracker_range(end_date, args.days, cookie, uids=uids, merge=args.merge)
        else:
            date_arg = args.date or (date.today() - timedelta(days=1)).strftime("%y%m%d")
            run_tracker(date_arg, cookie)
    except RateLimited:
        print(
            "\nRATE LIMITED. Weibo throttle is account-level and persists 6–24h\n"
            "(a new cookie for the same account does NOT reset it).\n"
            "Wait, then re-run with: python src/tracker.py [args] --merge\n"
            "Do not retry now — additional requests extend the window.\n"
            "To add events immediately, use --urls (anonymous fetch, unaffected).",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
