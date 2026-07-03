import pytest

from src.tracker import run_tracker_urls


@pytest.fixture
def env(tmp_path, monkeypatch):
    pipe = tmp_path / "_pipeline"
    (pipe / "events").mkdir(parents=True)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", pipe)
    monkeypatch.setattr(
        "src.tracker.filter_feminist_events",
        lambda posts: [
            {"title": "事件", "brief": p["text"], "sources": [p["url"]]}
            for p in posts
        ],
    )
    return pipe


def test_urls_mode_appends_events(env, monkeypatch):
    monkeypatch.setattr(
        "src.tracker._fetch_url_post",
        lambda u: {"url": u, "text": "家暴事件通报", "retweet_text": ""},
    )
    run_tracker_urls(["https://weibo.com/1/a", "https://weibo.com/1/b"], "260702")
    content = (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "## 1." in content and "## 2." in content


def test_urls_mode_merges_into_existing_events(env, monkeypatch):
    (env / "events" / "260702.md").write_text(
        "# Events — 2026-07-02\n\n## 1. 已有事件\n**Sources**: [u]\n**Brief**: b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.tracker._fetch_url_post",
        lambda u: {"url": u, "text": "性侵案进展", "retweet_text": ""},
    )
    run_tracker_urls(["https://weibo.com/1/c"], "260702")
    content = (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "## 1. 已有事件" in content and "## 2." in content


def test_urls_mode_skips_failed_fetch(env, monkeypatch, capsys):
    from src.wbfetch import WbFetchError

    def fetch(u):
        if u.endswith("bad"):
            raise WbFetchError("nope")
        return {"url": u, "text": "性侵案进展", "retweet_text": ""}

    monkeypatch.setattr("src.tracker._fetch_url_post", fetch)
    run_tracker_urls(["https://weibo.com/1/ok", "https://weibo.com/1/bad"], "260702")
    assert "## 1." in (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "bad" in capsys.readouterr().err
