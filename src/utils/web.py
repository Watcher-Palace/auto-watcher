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
        text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
        return " ".join(text.split())
