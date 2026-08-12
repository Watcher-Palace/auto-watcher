import pytest
import requests

from src import srcfetch
from src.srcfetch import (
    USAGE, SrcFetchError, fetch_text, load, main, normalize, save, snapshot_path,
)

URL = "https://news.example.com/a/2026/0731/12345.shtml"
EVENT = "260731-1"
LONG = "正文" * 200


@pytest.fixture(autouse=True)
def snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(srcfetch, "SNAPSHOTS", tmp_path / "snapshots")
    return tmp_path / "snapshots"


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
    p = save(URL, EVENT)
    assert p == snapshot_path(URL, EVENT) and URL in p.read_text(encoding="utf-8")
    assert load(URL, EVENT) == "她说：我不认识他"


def test_load_returns_none_when_never_fetched():
    # 没抓过 ≠ 核不过：linter 据此降级为 WARN，不能当成 FAIL
    assert load(URL, EVENT) is None


def test_load_returns_none_for_header_only_snapshot(snapshots):
    # fix 轮 2（评审 M-2）：只有头部没有正文的快照（写了一半/手工占位）——语义上
    # 等于"没有可用快照"，不能被下游误判成"抓到了空文本"去跟摘录逐字比对，那会把
    # "抓失败"错报成"研究造假"（[E1] 摘录不在原文快照里）。save() 已拒写空正文，
    # 这条防的是那之外手工/半成品文件的情况。
    p = snapshot_path(URL, EVENT)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# SOURCE: {URL}\n# FETCHED: x\n\n   \n", encoding="utf-8")
    assert load(URL, EVENT) is None


def test_empty_body_is_not_saved(monkeypatch):
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "   ")
    with pytest.raises(SrcFetchError):
        save(URL, EVENT)
    assert not snapshot_path(URL, EVENT).exists()


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


def test_snapshots_are_partitioned_by_event(monkeypatch, snapshots):
    # 快照是事件的证据底本，随事件归档——两个事件引同一 URL 各存一份
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "同一篇报道")
    save(URL, "260731-1")
    save(URL, "260801-2")
    assert load(URL, "260731-1") == "同一篇报道"
    assert load(URL, "260801-2") == "同一篇报道"
    assert (snapshots / "260731-1").is_dir() and (snapshots / "260801-2").is_dir()


def test_load_is_none_for_other_event():
    # 别的事件抓过不算本事件抓过，否则归档后证据链对不上
    assert load(URL, "260731-1") is None


def test_snapshot_filename_carries_host():
    p = snapshot_path(URL, EVENT)
    assert p.name.startswith("news.example.com-") and p.suffix == ".txt"


def test_chrome_blocks_are_stripped_by_class_and_id(monkeypatch):
    html = (
        '<div class="nav">网易首页 应用 网易新闻 网易公开课</div>'
        '<div class="article-header"><h1>保时捷女销冠起诉造黄谣者</h1></div>'
        "<p>牟倩文说，他一直都没道歉。" + "正文" * 100 + "</p>"
        '<div id="footer">© 1997-2026 网易公司版权所有 联系方法 招聘信息</div>'
        '<div class="recommend-list">罗永浩罕见夸赞 军事要闻 乌防空导弹严重短缺</div>'
    )
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(html))
    text = fetch_text(URL)
    assert "他一直都没道歉" in text
    assert "网易首页" not in text and "版权所有" not in text and "罗永浩" not in text


def test_article_header_survives_stripping(monkeypatch):
    # header/hot 只做整词匹配：article-header 常含标题，标题本身可被摘为 `标题` 形态
    html = '<div class="article-header"><h1>' + "标题" * 100 + "</h1></div>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(html))
    assert "标题标题" in fetch_text(URL)


# 以下四条都在发起任何抓取之前就返回（拒绝路径），天然 hermetic，不需要 mock 网络——
# 提前返回正是要测的性质，mock 掉网络反而会掩盖这一点
def test_main_with_no_args_prints_usage(capsys):
    assert main([]) == 2
    assert capsys.readouterr().out.strip() == USAGE


def test_main_with_event_missing_value_prints_usage(capsys):
    assert main(["--event"]) == 2
    assert capsys.readouterr().out.strip() == USAGE


def test_main_with_event_value_swallowing_flag_prints_usage(capsys):
    # `--event --check <url>` 不能把 `--check` 当成事件号收下
    assert main(["--event", "--check", "https://a/b"]) == 2
    assert capsys.readouterr().out.strip() == USAGE


def test_main_with_event_but_no_url_prints_usage(capsys):
    assert main(["--event", "260731-1"]) == 2
    assert capsys.readouterr().out.strip() == USAGE


def test_from_research_collects_every_source_url(tmp_path, monkeypatch):
    # 没有这个批量入口，agent 要手敲十几个 URL，必然漏
    doc = tmp_path / "260731-1-标题.md"
    doc.write_text(
        "## 信息来源\n"
        "- 2026.07.31，极目新闻。*甲*。https://a.example/1 — 快照失败：超时\n"
        "- 2026.07.31，紫牛新闻。*乙*。https://b.example/2 — 快照 2026-08-07（900字）\n"
        "\n## 摘录\n[E1] 信源2 · 标题 · 2026-08-07\n乙\n",
        encoding="utf-8",
    )
    fetched = []
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: fetched.append(u) or "正文")
    assert srcfetch.main(["--event", "260731-1", "--from-research", str(doc)]) == 0
    assert fetched == ["https://a.example/1", "https://b.example/2"]


def test_refresh_overwrites_an_existing_snapshot(monkeypatch):
    # 评审查「有没有更新进展」时读到研究阶段几天前的字节就是错的
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "旧正文")
    save(URL, EVENT)
    monkeypatch.setattr(srcfetch, "fetch_text", lambda u: "新正文")
    srcfetch.main(["--event", EVENT, URL])
    assert load(URL, EVENT) == "旧正文"          # 无 --refresh：已有快照跳过
    srcfetch.main(["--event", EVENT, "--refresh", URL])
    assert load(URL, EVENT) == "新正文"


# ==================== final-review fix 轮 1 ====================


def test_normalize_strips_markdown_emphasis():
    # F-7a：研究文件的摘录/事实句常把词加粗（**合成聊天记录**），快照正文没有
    # 这层 markdown，逐字比对若不剥 `*` 必然落空——两侧同改（linter._norm_quote
    # 必须保持同形，见 Minor 8）
    assert normalize("**合成聊天记录**并散布至互联网") == normalize("合成聊天记录并散布至互联网")


def test_from_research_nonexistent_file_gives_a_clear_message_not_a_traceback(capsys):
    # F-9：--from-research 指向不存在的文件此前会抛裸 FileNotFoundError
    rc = main(["--event", EVENT, "--from-research", "/no/such/file.md"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "不存在" in out


def test_from_research_with_zero_parseable_sources_gives_a_clear_message(tmp_path, capsys):
    # F-9：研究文件里一条来源都解析不出来时，此前打的是 usage:，agent 会以为是
    # 自己命令写错了——应改成说清楚是研究文件 ## 信息来源 没有可解析的来源行，
    # 并给出原始行数
    doc = tmp_path / "260731-1-标题.md"
    doc.write_text("## 信息来源\n- 澎湃新闻报道了\n- 另一条脏行\n", encoding="utf-8")
    rc = main(["--event", EVENT, "--from-research", str(doc)])
    assert rc == 2
    out = capsys.readouterr().out
    assert "没有解析得出的来源行" in out and "2 行" in out
    assert out.strip() != USAGE


def test_main_with_event_but_no_url_still_prints_bare_usage(capsys):
    # 回归：--from-research 没给的普通用法错误仍应打原样 USAGE，不受上面那条改动影响
    assert main(["--event", "260731-1"]) == 2
    assert capsys.readouterr().out.strip() == USAGE


def test_fetch_rendered_launch_has_a_timeout(monkeypatch):
    # F-8：launch() 此前没有 timeout——只有 page.goto 有；浏览器进程本身起不来时
    # 会无限挂起。与 wbfetch 共用同一条路径，一并加。
    from unittest.mock import MagicMock
    import playwright.sync_api as pw_api

    pw = MagicMock()
    page = pw.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.locator.return_value.inner_text.return_value = "正文"
    cm = MagicMock()
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    monkeypatch.setattr(pw_api, "sync_playwright", lambda: cm)

    srcfetch._fetch_rendered(URL)

    _, kwargs = pw.chromium.launch.call_args
    assert kwargs.get("timeout")
