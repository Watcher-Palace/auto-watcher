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
from src.utils.web import WebClient
from src.utils.pipeline import events_path, set_state

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
