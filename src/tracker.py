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
from openai import OpenAI
from src.utils.web import WebClient
from src.utils.pipeline import events_path, set_state

WEIBO_API = "https://m.weibo.cn/api/container/getIndex"
FEMINIST_KEYWORDS = ["女性", "女权", "性别", "婚姻", "家暴", "性侵", "拐卖", "生育", "就业歧视"]
CN_TZ = timezone(timedelta(hours=8))
PAGINATION_MAX_PAGES = 20
PAGINATION_DELAY_SEC = 0.5   # base; actual = uniform(base, base*3)
INTER_UID_DELAY_SEC = 2.0    # base; actual = uniform(base, base*3)


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


def filter_feminist_events(posts: list[dict], api_key: str, model: str) -> list[dict]:
    """Call OpenRouter to filter and deduplicate feminist-relevant events."""
    if not posts:
        return []
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

    for attempt in range(3):
        try:
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


def run_tracker(date_str: str, api_key: str, model: str, cookie: str) -> None:
    """Single-date mode: fetch current page only, write to date_str events file."""
    tracked_uids = [u.strip() for u in os.environ.get("TRACKED_UIDS", "").split(",") if u.strip()]
    web = WebClient(cookie=cookie)
    all_posts = []
    for uid in tracked_uids:
        try:
            all_posts.extend(fetch_weibo_posts(web, uid))
        except WebClient.FetchError as e:
            print(f"Warning: failed to fetch uid {uid}: {e}")
    events = filter_feminist_events(all_posts, api_key, model)
    out = write_events_file(date_str, events)
    set_state("20" + date_str)
    print(f"Wrote {len(events)} events to {out}")


def run_tracker_range(
    end_date: date,
    days: int,
    api_key: str,
    model: str,
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
    for i, uid in enumerate(uids):
        if i > 0:
            time.sleep(random.uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC * 3))
        print(f"Paginating uid {uid} until {cutoff.date()} ...")
        posts = fetch_weibo_posts_paginated(web, uid, cutoff)
        print(f"  uid {uid}: {len(posts)} posts collected")
        all_posts.extend(posts)
    buckets = bucket_posts_by_date(all_posts, target_dates)
    print(f"Total posts: {len(all_posts)}; bucketed dates: {sorted(buckets.keys())}")
    writer = append_events_to_file if merge else write_events_file
    for date_str in sorted(target_dates):
        bucket = buckets.get(date_str, [])
        events = filter_feminist_events(bucket, api_key, model) if bucket else []
        out = writer(date_str, events)
        action = "appended" if merge else "wrote"
        print(f"  {date_str}: {len(bucket)} posts → {len(events)} events {action} → {out}")
    set_state("20" + end_date.strftime("%y%m%d"))


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
    args = parser.parse_args()

    cfg = yaml.safe_load(open(Path(__file__).parent / "config.yaml"))
    model = cfg["llm"]["tracker_model"]
    api_key = os.environ["OPENROUTER_API_KEY"]
    cookie = os.environ.get("WEIBO_COOKIE", "")

    if args.days:
        end_date = _parse_yymmdd(args.end) if args.end else (date.today() - timedelta(days=1))
        uids = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else None
        run_tracker_range(end_date, args.days, api_key, model, cookie, uids=uids, merge=args.merge)
    else:
        date_arg = args.date or (date.today() - timedelta(days=1)).strftime("%y%m%d")
        run_tracker(date_arg, api_key, model, cookie)


if __name__ == "__main__":
    main()
