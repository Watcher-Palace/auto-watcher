import pytest
import requests

from src import srcfetch
from src.srcfetch import SrcFetchError, fetch_text, load, normalize, save, snapshot_path

URL = "https://news.example.com/a/2026/0731/12345.shtml"
LONG = "正文" * 200


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "CACHE", tmp_path / ".srccache")
    return tmp_path / ".srccache"


class FakeResp:
    def __init__(self, text, encoding="utf-8"):
        self.text, self.encoding, self.apparent_encoding = text, encoding, "utf-8"

    def raise_for_status(self):
        pass


def test_normalize_ignores_whitespace_and_quote_variants():
    # 空白与引号在转载/渲染里极不稳定，算进"逐字"只会制造假阳性
    assert normalize("我 不认识他，　他欠我一个道歉") == normalize("我不认识他，他欠我一个道歉")
    assert normalize("「原话」") == normalize('“原话”') == normalize('"原话"')
    # 用字与标点必须照旧比——那才是要核的东西
    assert normalize("他欠我一个道歉") != normalize("他欠我一句道歉")


def test_save_then_load_roundtrip(monkeypatch):
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "她说：我不认识他")
    p = save(URL)
    assert p == snapshot_path(URL) and URL in p.read_text(encoding="utf-8")
    assert load(URL) == "她说：我不认识他"


def test_load_returns_none_when_never_fetched():
    # 没抓过 ≠ 核不过：linter 据此降级为 WARN，不能当成 FAIL
    assert load(URL) is None


def test_empty_body_is_not_saved(monkeypatch):
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "   ")
    with pytest.raises(SrcFetchError):
        save(URL)
    assert not snapshot_path(URL).exists()


def test_http_path_strips_scripts_and_tags(monkeypatch):
    html = f"<html><body><script>var x=1</script><p>{LONG}</p></body></html>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(html))
    text = fetch_text(URL)
    assert LONG in text and "var x=1" not in text


def test_short_http_body_falls_back_to_headless_render(monkeypatch):
    # JS 壳只回一句"加载中"，裸 HTTP 拿不到正文——必须换无头浏览器，而不是收下空壳
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp("<body>加载中</body>"))
    monkeypatch.setattr(srcfetch, "_fetch_rendered", lambda u: LONG)
    assert fetch_text(URL) == LONG


def test_http_error_falls_back_to_headless_render(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("403")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(srcfetch, "_fetch_rendered", lambda u: LONG)
    assert fetch_text(URL) == LONG


def test_both_paths_failing_raises_with_both_reasons(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp("<body>短</body>"))

    def boom(u):
        raise RuntimeError("chrome 挂了")

    monkeypatch.setattr(srcfetch, "_fetch_rendered", boom)
    with pytest.raises(SrcFetchError) as e:
        fetch_text(URL)
    assert "JS 壳" in str(e.value) and "chrome 挂了" in str(e.value)


def test_weibo_url_goes_through_wbfetch(monkeypatch):
    # 微博的原始接口文本本来就没经过模型，不必也不能走通用 HTML 抽取
    import src.wbfetch as wbfetch

    monkeypatch.setattr(wbfetch, "fetch_post", lambda u: {"text": "微博正文"})
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("微博不该走 HTTP 抽取"))
    assert fetch_text("https://weibo.com/1234567890/AbCdE") == "微博正文"
