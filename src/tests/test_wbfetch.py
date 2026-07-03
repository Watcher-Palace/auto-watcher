import pytest
from unittest.mock import MagicMock, patch

from src.wbfetch import PWTimeout, WbFetchError, fetch_post


def make_pw(text="正文内容", author="作者", when="2026-05-28 10:00", fail_first=False):
    pw = MagicMock()
    page = (
        pw.chromium.launch.return_value
        .new_context.return_value
        .new_page.return_value
    )
    if fail_first:
        page.wait_for_selector.side_effect = [PWTimeout("t"), None]

    def locator(sel):
        loc = MagicMock()
        vals = {"detail_wbtext": text, "head_name": author, "head-info_time": when}
        for k, v in vals.items():
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
    assert d["retweet_text"] == ""


def test_fetch_post_retries_then_succeeds():
    with patch("src.wbfetch.sync_playwright", return_value=make_pw(fail_first=True)):
        d = fetch_post("https://weibo.com/1/x", retries=2)
    assert d["text"] == "正文内容"


def test_fetch_post_raises_after_retries():
    cm = make_pw()
    page = (
        cm.__enter__.return_value
        .chromium.launch.return_value
        .new_context.return_value
        .new_page.return_value
    )
    page.wait_for_selector.side_effect = PWTimeout("t")
    with patch("src.wbfetch.sync_playwright", return_value=cm):
        with pytest.raises(WbFetchError):
            fetch_post("https://weibo.com/1/x", retries=2)
