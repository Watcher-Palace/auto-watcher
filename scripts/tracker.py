import json
from datetime import datetime
from bs4 import BeautifulSoup
from scripts.utils import pipeline
from scripts.utils.web import WebClient

NOTHING_NOTICEABLE = "Nothing noticeable."

FILTER_SYSTEM = """You are an assistant that filters social media posts for feminist-relevant events.
Given a list of Weibo post texts and a list of topic keywords, identify posts that describe
significant events related to: {keywords}

For each relevant event, output ONLY a markdown block in this exact format:
## N. 标题简述
**Sources**: [url1, url2]
**Brief**: 一两句话概述。

If multiple posts describe the same incident, merge them into a single event entry and list all source URLs.

If nothing is relevant, output exactly: {nothing}
Do not include any other text."""


def run_tracker(
    date_str: str,
    config: dict,
    claude,
    web,
    paste_text: str | None = None,
) -> None:
    """
    Track events for a single date. Writes to _pipeline/events/YYMMDD.md
    and updates .state. If web.fetch fails and paste_text is provided,
    uses paste_text instead. If fetch fails and no paste_text, re-raises.
    """
    raw_content = _fetch_weibo_content(config["weibo_accounts"], web, paste_text)

    keywords = "、".join(config.get("topic_keywords", []))
    system = FILTER_SYSTEM.format(keywords=keywords, nothing=NOTHING_NOTICEABLE)
    user_prompt = f"以下是微博内容，请筛选相关事件：\n\n{raw_content}"

    events_markdown = claude.simple(system, user_prompt)

    event_date = datetime.strptime(
        "20" + date_str if len(date_str) == 6 else date_str, "%Y%m%d"
    ).date()

    if events_markdown.strip() == NOTHING_NOTICEABLE:
        output = NOTHING_NOTICEABLE
    else:
        output = f"# Events — {event_date.strftime('%Y-%m-%d')}\n\n{events_markdown.strip()}\n"

    pipeline.events_path(date_str).write_text(output)
    pipeline.set_last_tracked_date(event_date)


def _fetch_weibo_content(accounts: list[str], web, paste_text: str | None) -> str:
    """Fetch Weibo account pages and return concatenated post texts."""
    if paste_text:
        return paste_text

    parts = []
    last_error = None
    for uid in accounts:
        url = (
            f"https://m.weibo.cn/api/container/getIndex"
            f"?type=uid&value={uid}&containerid=107603{uid}"
        )
        try:
            raw = web.fetch(url)
            text = _extract_posts(raw, uid)
            parts.append(f"[weibo uid={uid}]\n{text}")
        except WebClient.FetchError as e:
            last_error = e

    if not parts:
        if last_error:
            raise last_error
        return ""

    return "\n\n---\n\n".join(parts)


def _extract_posts(raw: str, uid: str) -> str:
    """Parse Weibo JSON response and return readable post texts."""
    try:
        data = json.loads(raw)
        cards = data.get("data", {}).get("cards", [])
        posts = []
        for card in cards:
            mblog = card.get("mblog")
            if not mblog:
                continue
            mid = mblog.get("id", "")
            post_url = f"https://weibo.com/{uid}/{mid}"
            # Strip HTML tags from post text
            raw_text = mblog.get("text", "")
            text = BeautifulSoup(raw_text, "html.parser").get_text(separator=" ", strip=True)
            # Include retweet body if present
            retweeted = mblog.get("retweeted_status")
            if retweeted:
                rt_raw = retweeted.get("text", "")
                rt_text = BeautifulSoup(rt_raw, "html.parser").get_text(separator=" ", strip=True)
                if rt_text:
                    text = text + "\nRT: " + rt_text
            created = mblog.get("created_at", "")
            posts.append(f"[{post_url}] ({created})\n{text}")
        return "\n\n".join(posts)
    except (json.JSONDecodeError, KeyError):
        # Fallback: treat as HTML
        return BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True)
