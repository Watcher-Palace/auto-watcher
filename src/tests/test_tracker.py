import pytest
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.tracker import (
    parse_weibo_cards, format_events, parse_created_at,
    bucket_posts_by_date, fetch_weibo_posts_paginated, CN_TZ,
    count_existing_events, append_events_to_file,
)


SAMPLE_CARDS = [
    {
        "mblog": {
            "id": "abc",
            "bid": "Abc123",
            "text": "<a>link</a> 女性遭受家暴事件",
            "created_at": "Thu May 07 14:30:00 +0800 2026",
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
            "created_at": "Wed May 06 10:00:00 +0800 2026",
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


def test_parse_weibo_cards_extracts_created_dt():
    posts = parse_weibo_cards(SAMPLE_CARDS, "1114030772")
    assert posts[0]["created_dt"].date() == date(2026, 5, 7)
    assert posts[1]["created_dt"].date() == date(2026, 5, 6)


def test_parse_weibo_cards_marks_pinned():
    cards = [{"mblog": {"id": "x", "bid": "X", "text": "t", "isTop": 1, "created_at": "Mon Jan 01 00:00:00 +0800 2024"}}]
    posts = parse_weibo_cards(cards, "u")
    assert posts[0]["is_top"] is True


def test_parse_created_at_handles_missing():
    assert parse_created_at("") is None
    assert parse_created_at("garbage") is None


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


def test_bucket_posts_by_date_groups_by_day():
    posts = [
        {"id": "a", "is_top": False, "created_dt": datetime(2026, 5, 7, 10, 0, tzinfo=CN_TZ)},
        {"id": "b", "is_top": False, "created_dt": datetime(2026, 5, 7, 22, 0, tzinfo=CN_TZ)},
        {"id": "c", "is_top": False, "created_dt": datetime(2026, 5, 6, 12, 0, tzinfo=CN_TZ)},
    ]
    buckets = bucket_posts_by_date(posts, ["260507", "260506"])
    assert len(buckets["260507"]) == 2
    assert len(buckets["260506"]) == 1


def test_bucket_posts_by_date_skips_pinned():
    posts = [
        {"id": "p", "is_top": True, "created_dt": datetime(2024, 1, 1, tzinfo=CN_TZ)},
        {"id": "n", "is_top": False, "created_dt": datetime(2026, 5, 7, tzinfo=CN_TZ)},
    ]
    buckets = bucket_posts_by_date(posts, ["260507"])
    assert "240101" not in buckets
    assert len(buckets["260507"]) == 1


def test_bucket_posts_by_date_filters_to_targets():
    posts = [
        {"id": "a", "is_top": False, "created_dt": datetime(2026, 5, 5, tzinfo=CN_TZ)},
        {"id": "b", "is_top": False, "created_dt": datetime(2026, 5, 7, tzinfo=CN_TZ)},
    ]
    buckets = bucket_posts_by_date(posts, ["260507"])
    assert "260505" not in buckets
    assert "260507" in buckets


def test_fetch_paginated_stops_at_cutoff():
    """Paginator should stop once a page contains posts older than cutoff."""
    page1 = [{"id": "1", "url": "u1", "text": "", "retweet_text": "",
              "created_dt": datetime(2026, 5, 8, tzinfo=CN_TZ), "is_top": False}]
    page2 = [{"id": "2", "url": "u2", "text": "", "retweet_text": "",
              "created_dt": datetime(2026, 5, 4, tzinfo=CN_TZ), "is_top": False}]
    cutoff = datetime(2026, 5, 6, tzinfo=CN_TZ)
    pages = [page1, page2, []]
    call_count = {"n": 0}
    def fake_fetch(web, uid, page=1):
        idx = call_count["n"]
        call_count["n"] += 1
        return pages[idx] if idx < len(pages) else []
    with patch("src.tracker.fetch_weibo_posts", side_effect=fake_fetch), \
         patch("src.tracker.time.sleep"):
        result = fetch_weibo_posts_paginated(MagicMock(), "u", cutoff, max_pages=5)
    assert call_count["n"] == 2
    assert len(result) == 2


def test_fetch_paginated_dedupes_by_id():
    """If the API returns overlapping pages, dedupe by id and stop."""
    same_post = {"id": "1", "url": "u", "text": "", "retweet_text": "",
                 "created_dt": datetime(2026, 5, 8, tzinfo=CN_TZ), "is_top": False}
    with patch("src.tracker.fetch_weibo_posts", return_value=[same_post]), \
         patch("src.tracker.time.sleep"):
        result = fetch_weibo_posts_paginated(MagicMock(), "u", datetime(2020, 1, 1, tzinfo=CN_TZ), max_pages=5)
    assert len(result) == 1


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
            run_tracker("260325", cookie="")

    events_file = tmp_path / "_pipeline" / "events" / "260325.md"
    assert events_file.exists()
    assert "测试事件" in events_file.read_text(encoding="utf-8")
    assert (tmp_path / ".state").read_text().strip() == "20260325"


def test_count_existing_events_returns_max_index(tmp_path):
    f = tmp_path / "events.md"
    f.write_text("# Events\n\n## 1. A\n\n## 2. B\n\n## 3. C\n", encoding="utf-8")
    assert count_existing_events(f) == 3


def test_count_existing_events_zero_when_missing(tmp_path):
    assert count_existing_events(tmp_path / "missing.md") == 0


def test_count_existing_events_zero_when_no_events(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("# Events — 2026-05-01\n", encoding="utf-8")
    assert count_existing_events(f) == 0


def test_append_events_continues_numbering(tmp_path, monkeypatch):
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    f = pipeline_mod.events_path("260501")
    f.write_text(
        "# Events — 2026-05-01\n\n## 1. 旧事件\n**Sources**: \n**Brief**: 旧描述\n",
        encoding="utf-8",
    )
    append_events_to_file("260501", [
        {"title": "新事件A", "brief": "新描述A", "sources": ["https://x"]},
        {"title": "新事件B", "brief": "新描述B", "sources": []},
    ])
    text = f.read_text(encoding="utf-8")
    assert "## 1. 旧事件" in text
    assert "## 2. 新事件A" in text
    assert "## 3. 新事件B" in text


def test_append_events_creates_file_if_missing(tmp_path, monkeypatch):
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    append_events_to_file("260501", [{"title": "T", "brief": "B", "sources": []}])
    f = pipeline_mod.events_path("260501")
    assert f.exists()
    assert "## 1. T" in f.read_text(encoding="utf-8")


def test_append_events_noop_for_empty_list(tmp_path, monkeypatch):
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    f = pipeline_mod.events_path("260501")
    f.write_text("## 1. existing\n", encoding="utf-8")
    append_events_to_file("260501", [])
    assert f.read_text(encoding="utf-8") == "## 1. existing\n"


def test_run_tracker_range_uids_override(tmp_path, monkeypatch):
    """Passing uids= should override TRACKED_UIDS env var."""
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    monkeypatch.setenv("TRACKED_UIDS", "should,not,be,used")
    called_uids = []
    def fake_paginate(web, uid, cutoff, max_pages=20):
        called_uids.append(uid)
        return []
    with patch("src.tracker.fetch_weibo_posts_paginated", side_effect=fake_paginate), \
         patch("src.tracker.filter_feminist_events", return_value=[]), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        run_tracker_range(date(2026, 5, 7), days=1, cookie="c", uids=["only_me"])
    assert called_uids == ["only_me"]


def test_run_tracker_range_merge_appends(tmp_path, monkeypatch):
    """merge=True should append events to existing file, continuing numbering."""
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    pre = pipeline_mod.events_path("260507")
    pre.write_text("# Events — 2026-05-07\n\n## 1. 已有事件\n**Sources**: \n**Brief**: x\n",
                   encoding="utf-8")
    post = {"id": "x", "url": "u", "text": "", "retweet_text": "",
            "created_dt": datetime(2026, 5, 7, 12, tzinfo=CN_TZ), "is_top": False}
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=[post]), \
         patch("src.tracker.filter_feminist_events",
               return_value=[{"title": "新增事件", "brief": "y", "sources": []}]), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        run_tracker_range(date(2026, 5, 7), days=1, cookie="c", uids=["u1"], merge=True)
    text = pre.read_text(encoding="utf-8")
    assert "## 1. 已有事件" in text
    assert "## 2. 新增事件" in text


def test_run_tracker_range_inter_uid_delay(tmp_path, monkeypatch):
    """Should sleep a jittered delay between UIDs (not before the first)."""
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    sleeps = []
    def fake_sleep(s): sleeps.append(s)
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=[]), \
         patch("src.tracker.filter_feminist_events", return_value=[]), \
         patch("src.tracker.time.sleep", side_effect=fake_sleep):
        from src.tracker import run_tracker_range, INTER_UID_DELAY_SEC
        run_tracker_range(date(2026, 5, 7), days=1, cookie="c", uids=["a", "b", "c"])
    # The only sleeps in run_tracker_range are the inter-UID delays, each
    # jittered as uniform(INTER_UID_DELAY_SEC, INTER_UID_DELAY_SEC*3).
    # 3 UIDs → 2 delays (none before the first), each within the jitter range.
    assert len(sleeps) == 2
    assert all(INTER_UID_DELAY_SEC <= s <= INTER_UID_DELAY_SEC * 3 for s in sleeps)


def test_run_tracker_range_writes_per_date_files(tmp_path, monkeypatch):
    import src.utils.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "STATE_FILE", tmp_path / ".state")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    monkeypatch.setenv("TRACKED_UIDS", "1,2")

    posts_for_uid = {
        "1": [
            {"id": "a", "url": "u1", "text": "", "retweet_text": "",
             "created_dt": datetime(2026, 5, 7, 10, tzinfo=CN_TZ), "is_top": False},
            {"id": "b", "url": "u2", "text": "", "retweet_text": "",
             "created_dt": datetime(2026, 5, 6, 10, tzinfo=CN_TZ), "is_top": False},
        ],
        "2": [
            {"id": "c", "url": "u3", "text": "", "retweet_text": "",
             "created_dt": datetime(2026, 5, 7, 14, tzinfo=CN_TZ), "is_top": False},
        ],
    }
    def fake_paginate(web, uid, cutoff, max_pages=20):
        return posts_for_uid[uid]
    def fake_filter(posts):
        return [{"title": f"event-{len(posts)}", "brief": "x", "sources": []}]

    with patch("src.tracker.fetch_weibo_posts_paginated", side_effect=fake_paginate), \
         patch("src.tracker.filter_feminist_events", side_effect=fake_filter), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        run_tracker_range(date(2026, 5, 7), days=2, cookie="c")

    f7 = tmp_path / "_pipeline" / "events" / "260507.md"
    f6 = tmp_path / "_pipeline" / "events" / "260506.md"
    assert f7.exists() and f6.exists()
    assert "event-2" in f7.read_text(encoding="utf-8")  # 2 posts on 5/7
    assert "event-1" in f6.read_text(encoding="utf-8")  # 1 post on 5/6
    assert (tmp_path / ".state").read_text().strip() == "20260507"
