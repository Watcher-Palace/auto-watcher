"""原文快照抓取 —— 把信源页面的正文按原样落到本地，供 research_linter 逐字核对摘录。

**为什么不能拿 WebFetch 当快照**：那个工具自己的说明写着 "converts the page to markdown,
and **answers `prompt` against it using a small fast model**" —— 它从不把页面还给调用者，
返回的是一个小模型读完页面后写的答复。研究阶段据此登记「正文原话」、评审阶段再据此
"逐字比对"，比的是同一段文本的两次改写，中间没有一处字节比对。260731-1 的伪引用
（把某报道的标题措辞标成当事人原话）正是从这个口子进的，评审也只是碰巧抓住。
本模块走裸 HTTP／无头浏览器取原始 HTML，模型不介入，快照才配当比对基准。

CLI: python src/srcfetch.py --event <YYMMDD-N> <url>...        # 抓并落快照
     python src/srcfetch.py --event <YYMMDD-N> --check <url>   # 只看快照在不在
"""
from __future__ import annotations
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import PIPELINE

SNAPSHOTS = PIPELINE / "snapshots"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 25
# 裸 HTTP 拿回的正文短于这个数，多半是 JS 渲染壳或反爬拦截页 —— 换无头浏览器再试一次
MIN_TEXT = 200
WEIBO_HOSTS = {"weibo.com", "www.weibo.com", "m.weibo.cn"}
DROP_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "iframe", "svg")
# 中文新闻站基本不用 <nav>/<footer> 语义标签，用的是 <div class="nav">，
# 上面那行 DROP_TAGS 在这些站上近乎空转：实测同一篇报道 ctdsb 原发 3.0KB、
# 163 转载 13.9KB，差额全是头部导航与尾部推荐信息流。按 class/id 再剥一层。
# 风险不对称：剥过头吃掉真正文 → linter 报「不在快照里」＝诬告研究 agent；
# 剥不够只是多烧 token。故只用判据硬的整词/分词匹配，不做正文主体抽取。
CHROME_TOKENS = {
    "nav", "navbar", "navigation", "footer", "sidebar", "aside",
    "recommend", "recommended", "recommendation", "related",
    "comment", "comments", "share", "copyright", "breadcrumb",
    "tuijian", "xiangguan", "hotnews", "hotlist",
}
# 这几个词在正文容器的类名里也常见（article-header 含标题、hot-word 可能是正文标签），
# 只在整个 class/id 值恰好等于它时才剥，不参与分词匹配
CHROME_EXACT = {"header", "hot", "top", "bottom", "menu", "logo"}
_SPLIT_ATTR_RE = re.compile(r"[-_\s]+")
# 逐字比对前两边同样归一：空白（含全角空格）与各式引号在转载/渲染中极不稳定，
# 把它们算进"逐字"只会制造假阳性；标点与用字一律不动，那才是要比的东西。
_STRIP_RE = re.compile(r"[\s　「」『』“”‘’\"']+")


class SrcFetchError(Exception):
    pass


def normalize(text: str) -> str:
    """比对用归一化 —— 快照与摘录必须走同一个函数，否则比的不是同一件事。"""
    return _STRIP_RE.sub("", text)


def event_dir(event: str) -> Path:
    return SNAPSHOTS / event


def snapshot_path(url: str, event: str) -> Path:
    host = urlparse(url).netloc.replace(":", "_") or "unknown"
    return event_dir(event) / f"{host}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}.txt"


def load(url: str, event: str) -> str | None:
    """返回该 URL 在该事件下的快照正文；没抓过返回 None（＝无法机械核对，不等于核不过）。"""
    p = snapshot_path(url, event)
    if not p.is_file():
        return None
    body = p.read_text(encoding="utf-8").split("\n\n", 1)
    return body[1] if len(body) == 2 else ""


def _is_chrome(tag) -> bool:
    vals = list(tag.get("class") or [])
    if tag.get("id"):
        vals.append(tag["id"])
    for v in vals:
        v = v.strip().lower()
        if v in CHROME_EXACT or v in CHROME_TOKENS:
            return True
        if any(part in CHROME_TOKENS for part in _SPLIT_ATTR_RE.split(v)):
            return True
    return False


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for t in soup(DROP_TAGS):
        t.decompose()
    for t in soup.find_all(_is_chrome):
        t.decompose()
    return " ".join(soup.get_text(" ").split())


def _fetch_http(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return _html_to_text(r.text)


def _fetch_rendered(url: str) -> str:
    """JS 渲染页兜底：同 wbfetch 的无头 Chrome，同样不经任何模型。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome", headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        try:
            ctx = browser.new_context(user_agent=UA, locale="zh-CN")
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
            return " ".join(page.locator("body").inner_text().split())
        finally:
            browser.close()


def fetch_text(url: str) -> str:
    """取该 URL 的正文纯文本。微博走 wbfetch（已是原始接口文本），其余先裸 HTTP 后无头浏览器。"""
    if urlparse(url).netloc in WEIBO_HOSTS:
        from src.wbfetch import fetch_post

        return fetch_post(url)["text"]
    errs: list[str] = []
    try:
        text = _fetch_http(url)
        if len(text) >= MIN_TEXT:
            return text
        errs.append(f"HTTP 正文仅 {len(text)} 字，疑似 JS 壳/拦截页")
    except Exception as e:
        errs.append(f"HTTP: {e}")
    try:
        return _fetch_rendered(url)
    except Exception as e:
        errs.append(f"渲染: {e}")
    raise SrcFetchError("；".join(errs))


def save(url: str, event: str) -> Path:
    text = fetch_text(url)
    if not text.strip():
        raise SrcFetchError("抓到空正文")
    p = snapshot_path(url, event)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"# SOURCE: {url}\n# FETCHED: {datetime.now().isoformat(timespec='seconds')}\n\n{text}",
        encoding="utf-8",
    )
    return p


def main(argv: list[str]) -> int:
    if "--event" not in argv:
        print("usage: python src/srcfetch.py --event <YYMMDD-N> [--check] <url>...")
        return 2
    event = argv[argv.index("--event") + 1]
    check_only = "--check" in argv
    urls = [a for a in argv if a.startswith("http")]
    if not urls:
        print("usage: python src/srcfetch.py --event <YYMMDD-N> [--check] <url>...")
        return 2
    rc = 0
    for u in urls:
        if check_only:
            snap = load(u, event)
            print(f"{'HAVE' if snap is not None else 'MISS'} {len(snap or '')} 字 {u}")
            rc = rc or (0 if snap is not None else 1)
            continue
        try:
            p = save(u, event)
            print(f"SNAPSHOT OK {u} → {p.name}（{len(load(u, event) or '')} 字）")
        except Exception as e:
            rc = 1
            print(f"SNAPSHOT FAIL {u}: {e}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
