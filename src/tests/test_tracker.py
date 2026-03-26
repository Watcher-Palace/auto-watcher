import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.tracker import parse_weibo_cards, format_events


SAMPLE_CARDS = [
    {
        "mblog": {
            "id": "abc",
            "bid": "Abc123",
            "text": "<a>link</a> 女性遭受家暴事件",
            "retweeted_status": {
                "text": "<b>转发内容</b> 详细描述"
            }
        }
    },
    {
        "mblog": {
            "id": "def",
            "bid": "Def456",
            "text": "无关内容",
        }
    },
    {
        "card_type": 9,  # non-mblog card, should be skipped
    }
]


def test_parse_weibo_cards_extracts_text():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert len(posts) == 2
    assert posts[0]["text"] == "link 女性遭受家暴事件"


def test_parse_weibo_cards_includes_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[0]["retweet_text"] == "转发内容 详细描述"


def test_parse_weibo_cards_empty_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[1]["retweet_text"] == ""


def test_parse_weibo_cards_skips_non_mblog():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert len(posts) == 2


def test_parse_weibo_cards_builds_url():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[0]["url"] == "https://weibo.com/1114030772/Abc123"


def test_format_events_markdown():
    events = [
        {"index": 1, "title": "测试事件", "brief": "简短描述", "sources": ["https://example.com"]},
    ]
    md = format_events("260325", events)
    assert "## 1. 测试事件" in md
    assert "简短描述" in md
    assert "https://example.com" in md


def test_format_events_header():
    md = format_events("260325", [])
    assert "2026-03-25" in md


def test_run_tracker_writes_events_file(tmp_path, monkeypatch):
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)

    with patch("src.tracker.fetch_weibo_posts", return_value=[]):
        with patch("src.tracker.filter_feminist_events", return_value=[
            {"title": "测试事件", "brief": "简短描述", "sources": ["https://example.com"]}
        ]):
            from src.tracker import run_tracker
            run_tracker("260325", api_key="test", model="test-model", cookie="")

    events_file = tmp_path / "_pipeline" / "events" / "260325.md"
    assert events_file.exists()
    assert "测试事件" in events_file.read_text(encoding="utf-8")
    assert (tmp_path / ".state").read_text().strip() == "20260325"
