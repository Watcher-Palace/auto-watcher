import re
import urllib.parse
from bs4 import BeautifulSoup
from src.utils import pipeline
from src.utils.web import WebClient

RESEARCH_SYSTEM = """You are a research assistant for a feminist news blog.
Given an event description and web content gathered from multiple sources, compile
a comprehensive research document in Chinese.

Output ONLY in this format:
# Research: {title} ({date}, #{index})

## Facts
[Key facts, chronological if applicable, with <font color="blue"> for most recent updates]

## Parties
[Identify all key parties — victims, perpetrators, institutions, officials — and describe
their actions, statements, and any relevant social media posts (e.g. the victim's own Weibo posts,
official accounts' responses). Include usernames or handles where known.]

## Sources
- [来源名称] url — 关键摘录

Be factual. Only report what you actually found. Note conflicting information between sources."""


def run_researcher(
    date_str: str,
    indexes: list[int],
    claude,
    web,
    confirm_overwrite: bool = False,
) -> None:
    """Research approved events and write one file per event to _pipeline/research/.
    Raises FileExistsError if a research file already exists for any index,
    unless confirm_overwrite=True."""
    events_path = pipeline.events_path(date_str)
    if not events_path.exists():
        raise FileNotFoundError(f"Events file not found: {events_path}")

    titles = pipeline.get_event_titles(date_str)
    events_content = events_path.read_text()

    for index in indexes:
        existing = pipeline.find_research_file(date_str, index)
        if existing and not confirm_overwrite:
            raise FileExistsError(
                f"Research file already exists for {date_str}-{index}: {existing.name}. "
                "Pass confirm_overwrite=True to overwrite."
            )
        title = titles.get(index, f"事件{index}")
        _research_event(date_str, index, title, events_content, claude, web)


def _research_event(
    date_str: str,
    index: int,
    title: str,
    events_content: str,
    claude,
    web,
) -> None:
    """Search the web in Python, then ask LLM to compile research."""
    source_urls = _extract_sources_for_event(events_content, index)

    # Fetch seed URLs from the events file
    fetched = _fetch_urls(source_urls, web)

    # Search DuckDuckGo with the event title and fetch top results
    search_urls = _search_ddg(title, web, max_results=5)
    fetched += _fetch_urls(search_urls, web)

    web_content = "\n\n---\n\n".join(fetched) if fetched else "无法获取任何来源内容"

    display_date = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
    system = RESEARCH_SYSTEM.format(title=title, date=display_date, index=index)
    user_prompt = (
        f"事件标题：{title}\n\n"
        f"事件摘要：\n{events_content}\n\n"
        f"已收集的来源内容：\n\n{web_content}"
    )

    research = claude.simple(system, user_prompt)
    out_path = pipeline.research_path(date_str, index, title)
    out_path.write_text(research)


def _fetch_urls(urls: list[str], web, max_chars: int = 3000) -> list[str]:
    """Fetch a list of URLs and return text content snippets."""
    results = []
    for url in urls:
        try:
            html = web.fetch(url)
            text = web.extract_text(html)[:max_chars]
            results.append(f"[来源: {url}]\n{text}")
        except WebClient.FetchError:
            results.append(f"[来源: {url}] (无法访问)")
    return results


def _search_ddg(query: str, web, max_results: int = 5) -> list[str]:
    """Search DuckDuckGo and return a list of result URLs."""
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        html = web.fetch(search_url)
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select("a.result__a")[:max_results]:
            href = a.get("href", "")
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            url = params.get("uddg", [href])[0]
            if url:
                urls.append(url)
        return urls
    except WebClient.FetchError:
        return []


def _extract_sources_for_event(events_content: str, index: int) -> list[str]:
    """Parse source URLs from the events file for a specific event index."""
    pattern = rf'## {index}\..+?(?=## \d+\.|$)'
    m = re.search(pattern, events_content, re.DOTALL)
    if not m:
        return []
    section = m.group(0)
    return re.findall(r'https?://\S+', section)
