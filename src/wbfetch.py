"""Anonymous Weibo post fetcher.

Headless system Chrome passes the Sina Visitor System (tourist cookies) —
no account involved, so the account-level rate limit does not apply.
Only single post URLs work: timelines/profiles stay login-walled.

CLI: python src/wbfetch.py <weibo-post-url>...
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# Logged-out ("visitor wall") pages render one <article> with CSS-module hashed
# class names; the logged-in SPA uses detail_wbtext. Wait on <article>, prefer
# the rich selector when present.
POST_SEL = "article"
RICH_TEXT_SEL = '[class*="detail_wbtext"]'


class WbFetchError(Exception):
    pass


def fetch_post(
    url: str,
    timeout_ms: int = 30000,
    retries: int = 3,
    headless: bool = True,
) -> dict:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    channel="chrome",
                    headless=headless,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                try:
                    ctx = browser.new_context(user_agent=UA, locale="zh-CN")
                    ctx.add_init_script(
                        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                    )
                    page = ctx.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_selector(POST_SEL, timeout=timeout_ms)
                    rich = page.locator(RICH_TEXT_SEL)
                    if rich.count() > 0:
                        text = rich.first.inner_text()
                    else:
                        text = page.locator(POST_SEL).first.inner_text()
                    author = page.locator('article [class*="_name_"]').first.inner_text()
                    created = page.locator('article [class*="_time_"]').first.inner_text()
                    images = [
                        img.get_attribute("src") or ""
                        for img in page.locator("article img").all()
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
        except Exception as e:  # visitor flow / chrome launch failures
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
