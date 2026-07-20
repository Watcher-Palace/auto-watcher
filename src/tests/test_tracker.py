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
from src.utils.web import WebClient


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
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
    assert len(posts) == 2
    assert posts[0]["text"] == "link 女性遭受家暴事件"


def test_parse_weibo_cards_includes_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
    assert posts[0]["retweet_text"] == "转发内容 详细描述"


def test_parse_weibo_cards_empty_retweet():
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
    assert posts[1]["retweet_text"] == ""


def test_parse_weibo_cards_skips_non_mblog():
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
    assert len(posts) == 2


def test_parse_weibo_cards_builds_url():
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
    assert posts[0]["url"] == "https://weibo.com/9999999999/Abc123"


def test_parse_weibo_cards_extracts_created_dt():
    posts = parse_weibo_cards(SAMPLE_CARDS, "9999999999")
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
        result, _ = fetch_weibo_posts_paginated(MagicMock(), "u", cutoff, max_pages=5)
    assert call_count["n"] == 2
    assert len(result) == 2


def test_fetch_paginated_dedupes_by_id():
    """If the API returns overlapping pages, dedupe by id and stop."""
    same_post = {"id": "1", "url": "u", "text": "", "retweet_text": "",
                 "created_dt": datetime(2026, 5, 8, tzinfo=CN_TZ), "is_top": False}
    with patch("src.tracker.fetch_weibo_posts", return_value=[same_post]), \
         patch("src.tracker.time.sleep"):
        result, _ = fetch_weibo_posts_paginated(MagicMock(), "u", datetime(2020, 1, 1, tzinfo=CN_TZ), max_pages=5)
    assert len(result) == 1


def _mk_post(pid, dt):
    return {"id": pid, "url": f"u/{pid}", "text": "", "retweet_text": "",
            "created_dt": dt, "is_top": False}


def test_fetch_paginated_complete_when_cutoff_crossed():
    """Crossing the cutoff attests full coverage of the range."""
    pages = [[_mk_post("1", datetime(2026, 5, 8, tzinfo=CN_TZ))],
             [_mk_post("2", datetime(2026, 5, 4, tzinfo=CN_TZ))]]
    def fake_fetch(web, uid, page=1):
        return pages[page - 1] if page <= len(pages) else []
    with patch("src.tracker.fetch_weibo_posts", side_effect=fake_fetch), \
         patch("src.tracker.time.sleep"):
        _, complete = fetch_weibo_posts_paginated(
            MagicMock(), "u", datetime(2026, 5, 6, tzinfo=CN_TZ), max_pages=5)
    assert complete is True


def test_fetch_paginated_incomplete_at_page_cap():
    """Exhausting max_pages before the cutoff means unfetched posts remain."""
    def fake_fetch(web, uid, page=1):
        return [_mk_post(str(page), datetime(2026, 5, 8, 12, page, tzinfo=CN_TZ))]
    with patch("src.tracker.fetch_weibo_posts", side_effect=fake_fetch), \
         patch("src.tracker.time.sleep"):
        posts, complete = fetch_weibo_posts_paginated(
            MagicMock(), "u", datetime(2026, 5, 1, tzinfo=CN_TZ), max_pages=3)
    assert len(posts) == 3
    assert complete is False


def test_fetch_paginated_complete_when_feed_ends():
    """An empty page means the feed has no older posts — coverage complete."""
    pages = [[_mk_post("1", datetime(2026, 5, 8, tzinfo=CN_TZ))], []]
    def fake_fetch(web, uid, page=1):
        return pages[page - 1] if page <= len(pages) else []
    with patch("src.tracker.fetch_weibo_posts", side_effect=fake_fetch), \
         patch("src.tracker.time.sleep"):
        _, complete = fetch_weibo_posts_paginated(
            MagicMock(), "u", datetime(2026, 5, 1, tzinfo=CN_TZ), max_pages=5)
    assert complete is True


def test_fetch_paginated_incomplete_on_fetch_error():
    """A mid-walk fetch error leaves the rest of the range unattested."""
    def fake_fetch(web, uid, page=1):
        if page == 2:
            raise WebClient.FetchError("boom")
        return [_mk_post("1", datetime(2026, 5, 8, tzinfo=CN_TZ))]
    with patch("src.tracker.fetch_weibo_posts", side_effect=fake_fetch), \
         patch("src.tracker.time.sleep"):
        _, complete = fetch_weibo_posts_paginated(
            MagicMock(), "u", datetime(2026, 5, 1, tzinfo=CN_TZ), max_pages=5)
    assert complete is False


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
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    monkeypatch.setenv("TRACKED_UIDS", "should,not,be,used")
    called_uids = []
    def fake_paginate(web, uid, cutoff, max_pages=20):
        called_uids.append(uid)
        return [], True
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
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    pre = pipeline_mod.events_path("260507")
    pre.write_text("# Events — 2026-05-07\n\n## 1. 已有事件\n**Sources**: \n**Brief**: x\n",
                   encoding="utf-8")
    post = {"id": "x", "url": "u", "text": "", "retweet_text": "",
            "created_dt": datetime(2026, 5, 7, 12, tzinfo=CN_TZ), "is_top": False}
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=([post], True)), \
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
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    sleeps = []
    def fake_sleep(s): sleeps.append(s)
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=([], True)), \
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
        return posts_for_uid[uid], True
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
    from src.utils import ledger
    assert ledger.get_row("260507", 1, pipeline_dir=tmp_path / "_pipeline")["标题"] == "event-2"
    assert ledger.get_row("260506", 1, pipeline_dir=tmp_path / "_pipeline")["标题"] == "event-1"


def test_range_truncated_does_not_mark_unreached_dates(tmp_path, monkeypatch):
    """A walk cut off at the page cap must not record 无事件 for dates it
    never reached — only dates strictly newer than the oldest fetched post
    are fully covered."""
    import src.utils.pipeline as pipeline_mod
    from src.utils import ledger
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    posts = [_mk_post("a", datetime(2026, 5, 7, 10, tzinfo=CN_TZ)),
             _mk_post("b", datetime(2026, 5, 6, 10, tzinfo=CN_TZ))]
    def fake_filter(bucket):
        return [{"title": f"event-{bucket[0]['id']}", "brief": "x", "sources": []}]
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=(posts, False)), \
         patch("src.tracker.filter_feminist_events", side_effect=fake_filter), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        run_tracker_range(date(2026, 5, 7), days=3, cookie="c", uids=["u1"])
    pipe = tmp_path / "_pipeline"
    # 260507 fully covered → events written
    assert ledger.get_row("260507", 1, pipeline_dir=pipe)["标题"] == "event-a"
    # 260506 partial (oldest fetched post's own day) → its events still land
    assert ledger.get_row("260506", 1, pipeline_dir=pipe)["标题"] == "event-b"
    # 260505 never reached → no row of any kind, stays untracked
    assert not any(r["收录日期"] == "260505" for r in ledger.read_rows(pipeline_dir=pipe))


def test_range_complete_marks_no_events(tmp_path, monkeypatch):
    """When the walk crossed the cutoff, an empty covered date IS 无事件."""
    import src.utils.pipeline as pipeline_mod
    from src.utils import ledger
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    posts = [_mk_post("a", datetime(2026, 5, 7, 10, tzinfo=CN_TZ))]
    with patch("src.tracker.fetch_weibo_posts_paginated", return_value=(posts, True)), \
         patch("src.tracker.filter_feminist_events",
               return_value=[{"title": "T", "brief": "x", "sources": []}]), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        run_tracker_range(date(2026, 5, 7), days=2, cookie="c", uids=["u1"])
    pipe = tmp_path / "_pipeline"
    rows = {r["收录日期"]: r for r in ledger.read_rows(pipeline_dir=pipe)}
    assert rows["260506"]["状态"] == "无事件"


def test_range_rate_limited_writes_partials_but_no_no_events(tmp_path, monkeypatch):
    """A rate-limited run has whole UIDs unfetched: fetched events still land,
    but no date may be marked 无事件."""
    import src.utils.pipeline as pipeline_mod
    from src.utils import ledger
    from src.tracker import RateLimited
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    (tmp_path / "_pipeline" / "events").mkdir(parents=True)
    def fake_paginate(web, uid, cutoff, max_pages=20):
        if uid == "b":
            raise RateLimited()
        return [_mk_post("a", datetime(2026, 5, 7, 10, tzinfo=CN_TZ))], True
    with patch("src.tracker.fetch_weibo_posts_paginated", side_effect=fake_paginate), \
         patch("src.tracker.filter_feminist_events",
               return_value=[{"title": "T", "brief": "x", "sources": []}]), \
         patch("src.tracker.time.sleep"):
        from src.tracker import run_tracker_range
        with pytest.raises(SystemExit) as ei:
            run_tracker_range(date(2026, 5, 7), days=2, cookie="c", uids=["a", "b"])
    assert ei.value.code == 2
    pipe = tmp_path / "_pipeline"
    assert ledger.get_row("260507", 1, pipeline_dir=pipe)["标题"] == "T"
    assert not any(r["状态"] == "无事件" for r in ledger.read_rows(pipeline_dir=pipe))


def test_write_events_file_records_ledger_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file
    from src.utils import ledger
    out = write_events_file("990101", [
        {"title": "甲", "brief": "b", "sources": []},
        {"title": "乙", "brief": "b", "sources": []},
    ])
    assert out is not None and out.exists()
    st = {int(r["事件编号"]): r for r in ledger.read_rows(pipeline_dir=tmp_path)}
    assert st[1]["标题"] == "甲" and st[1]["状态"] == "candidate"
    assert st[2]["标题"] == "乙"


def test_write_events_file_empty_records_no_events_without_md(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file
    from src.utils import ledger
    out = write_events_file("990102", [])
    assert out is None
    assert not (tmp_path / "events" / "990102.md").exists()
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    assert rows[0]["收录日期"] == "990102" and rows[0]["状态"] == "无事件"


def test_write_events_file_offsets_by_existing_ledger_rows(tmp_path, monkeypatch):
    """If the events md is gone (e.g. archived after the date went terminal)
    but ledger rows remain (a terminal row at index 1), write_events_file must
    number the new event starting after the ledger's max index — not from 1,
    which would collide with (and silently no-op against) the old row."""
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file
    from src.utils import ledger
    ledger.add_event("990104", 1, "旧", pipeline_dir=tmp_path)
    out = write_events_file("990104", [{"title": "新事件", "brief": "b", "sources": []}])
    assert out is not None
    row = ledger.get_row("990104", 2, pipeline_dir=tmp_path)
    assert row is not None and row["标题"] == "新事件"
    assert "## 2." in out.read_text(encoding="utf-8")


def test_append_events_empty_and_missing_file_records_nothing(tmp_path, monkeypatch):
    """Append callers (daily buckets, URL mode) hold partial samples — an
    empty result must NOT become a 无事件 row (that asserts a full-day check).
    The date must stay untracked."""
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.utils import ledger
    out = append_events_to_file("990105", [])
    assert out is None
    assert not (tmp_path / "events" / "990105.md").exists()
    assert not any(r["收录日期"] == "990105" for r in ledger.read_rows(pipeline_dir=tmp_path))


def test_append_events_continues_ledger_index(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    from src.tracker import write_events_file, append_events_to_file
    from src.utils import ledger
    write_events_file("990103", [{"title": "甲", "brief": "b", "sources": []}])
    append_events_to_file("990103", [{"title": "乙", "brief": "b", "sources": []}])
    assert ledger.get_row("990103", 2, pipeline_dir=tmp_path)["标题"] == "乙"


# ---- _extract_events_json：LLM 回复的健壮解析 ----

_EV = {"title": "某案", "brief": "一句概述", "sources": ["https://weibo.com/x"]}
_EV_JSON = json.dumps([_EV], ensure_ascii=False)


def test_extract_fenced_json_with_bracket_prose():
    from src.tracker import _extract_events_json
    content = f"帖子[1]和[5]为同一事件，合并如下：\n```json\n{_EV_JSON}\n```"
    assert _extract_events_json(content) == [_EV]


def test_extract_bare_array_after_bracket_echoes():
    # 260706 实际故障形态：回复先引用 "[1]" 式帖子编号，再给裸数组
    from src.tracker import _extract_events_json
    content = f"[1] 是旧闻回顾，排除。[2] 收录。\n{_EV_JSON}"
    assert _extract_events_json(content) == [_EV]


def test_extract_array_with_trailing_bracket_refs():
    from src.tracker import _extract_events_json
    content = f"{_EV_JSON}\n（由帖子[2]与[7]合并）"
    assert _extract_events_json(content) == [_EV]


def test_extract_plain_empty_array():
    from src.tracker import _extract_events_json
    assert _extract_events_json("[]") == []
    assert _extract_events_json("无符合条件的内容，返回空数组：\n[]") == []


def test_extract_no_valid_array_returns_none():
    from src.tracker import _extract_events_json
    assert _extract_events_json("你好，未发现相关内容。") is None
    assert _extract_events_json("见帖子[3]与[9]。") is None


def test_filter_raises_on_malformed_reply():
    # 解析不出合法数组必须抛错触发重试，绝不能静默返回 []（会被记成无事件）
    from src.tracker import filter_feminist_events
    fake = MagicMock(returncode=0, stdout="见帖子[3]。", stderr="")
    with patch("subprocess.run", return_value=fake), \
         patch("time.sleep"), \
         pytest.raises(Exception):
        filter_feminist_events([{"url": "u", "text": "t", "retweet_text": ""}])


# ---- 跨运行去重（write/append 前按来源 URL 对照已有记录） ----

def _dedup_env(tmp_path, monkeypatch):
    from src.utils import pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr(pipeline_mod, "ARCHIVE", tmp_path / "_pipeline_archive")
    return tmp_path / "_pipeline"


def test_dedupe_skips_urls_already_in_live_file(tmp_path, monkeypatch):
    pdir = _dedup_env(tmp_path, monkeypatch)
    from src.tracker import write_events_file
    from src.utils import ledger
    write_events_file("990201", [{"title": "甲", "brief": "b", "sources": ["https://weibo.com/1/A"]}])
    write_events_file("990201", [
        {"title": "甲重复", "brief": "b", "sources": ["https://weibo.com/1/A"]},
        {"title": "乙", "brief": "b", "sources": ["https://weibo.com/1/B"]},
    ])
    assert ledger.get_row("990201", 2, pipeline_dir=pdir)["标题"] == "乙"
    assert ledger.get_row("990201", 3, pipeline_dir=pdir) is None  # 甲重复 未入账


def test_dedupe_all_duplicates_writes_nothing_and_no_wushijian(tmp_path, monkeypatch):
    pdir = _dedup_env(tmp_path, monkeypatch)
    from src.tracker import write_events_file
    from src.utils import ledger
    write_events_file("990202", [{"title": "甲", "brief": "b", "sources": ["https://weibo.com/1/A"]}])
    write_events_file("990202", [{"title": "甲又来", "brief": "b", "sources": ["https://weibo.com/1/A"]}])
    assert ledger.get_row("990202", 2, pipeline_dir=pdir) is None
    assert ledger.get_row("990202", "无事件", pipeline_dir=pdir) is None


def test_dedupe_checks_archived_events_md(tmp_path, monkeypatch):
    pdir = _dedup_env(tmp_path, monkeypatch)
    arch = tmp_path / "_pipeline_archive" / "events"
    arch.mkdir(parents=True)
    (arch / "990203.md").write_text(
        "# Events — 99-02-03\n\n## 1. 旧事\n**Sources**: [https://weibo.com/1/C]\n**Brief**: b\n",
        encoding="utf-8",
    )
    from src.tracker import append_events_to_file
    from src.utils import ledger
    append_events_to_file("990203", [
        {"title": "旧事重复", "brief": "b", "sources": ["https://weibo.com/1/C"]},
        {"title": "新事", "brief": "b", "sources": ["https://weibo.com/1/D"]},
    ])
    rows = ledger.event_statuses("990203", pipeline_dir=pdir)
    titles = [ledger.get_row("990203", n, pipeline_dir=pdir)["标题"] for n in rows]
    assert "新事" in titles and "旧事重复" not in titles


def test_dedupe_keeps_events_without_sources(tmp_path, monkeypatch):
    _dedup_env(tmp_path, monkeypatch)
    from src.tracker import write_events_file, dedupe_events
    write_events_file("990204", [{"title": "甲", "brief": "b", "sources": ["https://weibo.com/1/A"]}])
    kept = dedupe_events("990204", [{"title": "手工条目", "brief": "b", "sources": []}])
    assert [e["title"] for e in kept] == ["手工条目"]


# ---- single-day date-filtered mode (searchProfile) ----

def test_parse_searchprofile_items_maps_fields():
    from src.tracker import parse_searchprofile_items
    items = [{
        "id": 5001, "idstr": "5001", "mblogid": "Qabc",
        "created_at": "Tue Jul 07 23:33:31 +0800 2026",
        "text_raw": "正文", "text": "<span>正文</span>",
        "retweeted_status": {"text_raw": "转发正文"},
    }]
    p = parse_searchprofile_items(items, "u1")[0]
    assert p["id"] == "5001"
    assert p["url"] == "https://weibo.com/u1/Qabc"
    assert p["text"] == "正文" and p["retweet_text"] == "转发正文"
    assert p["created_dt"].date() == date(2026, 7, 7)
    assert p["is_top"] is False


def test_fetch_by_day_rejects_non_ok_response():
    """{} (expired-cookie soft-fail) must raise, never return [] silently —
    a silent [] would let the caller attest 无事件 for an unchecked day."""
    from src.tracker import fetch_weibo_posts_by_day
    web = MagicMock()
    web.fetch_json.return_value = {}
    with pytest.raises(WebClient.FetchError):
        fetch_weibo_posts_by_day(web, "u1", date(2026, 7, 7))


def test_fetch_by_day_captcha_raises_ratelimited():
    from src.tracker import fetch_weibo_posts_by_day, RateLimited
    web = MagicMock()
    web.fetch_json.return_value = {"ok": -100, "url": "https://weibo.com/captcha"}
    with pytest.raises(RateLimited):
        fetch_weibo_posts_by_day(web, "u1", date(2026, 7, 7))


def test_fetch_by_day_paginates_until_empty():
    from src.tracker import fetch_weibo_posts_by_day
    web = MagicMock()
    web.fetch_json.side_effect = [
        {"ok": 1, "data": {"list": [{"idstr": "1", "mblogid": "a",
            "created_at": "Tue Jul 07 10:00:00 +0800 2026", "text_raw": "x"}]}},
        {"ok": 1, "data": {"list": []}},
    ]
    with patch("src.tracker.time.sleep"):
        posts = fetch_weibo_posts_by_day(web, "u1", date(2026, 7, 7))
    assert len(posts) == 1
    assert web.fetch_json.call_count == 2


def test_run_tracker_day_writes_events_and_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    (tmp_path / "events").mkdir(parents=True)
    monkeypatch.setenv("TRACKED_UIDS", "u1")
    from src.tracker import run_tracker_day
    from src.utils import ledger
    post = {"id": "1", "url": "u", "text": "t", "retweet_text": "",
            "created_dt": datetime(2026, 7, 7, 12, tzinfo=CN_TZ), "is_top": False}
    with patch("src.tracker.fetch_weibo_posts_by_day", return_value=[post]), \
         patch("src.tracker.filter_feminist_events",
               return_value=[{"title": "测试事件", "brief": "b", "sources": ["s"]}]), \
         patch("src.tracker.time.sleep"):
        run_tracker_day("260707", cookie="c")
    events_file = tmp_path / "events" / "260707.md"
    assert events_file.exists() and "测试事件" in events_file.read_text(encoding="utf-8")
    rows = [r for r in ledger.read_rows(pipeline_dir=tmp_path) if r["收录日期"] == "260707"]
    assert rows and rows[0]["标题"] == "测试事件" and rows[0]["状态"] == "candidate"


def test_run_tracker_day_attests_no_events_only_when_covered(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path)
    (tmp_path / "events").mkdir(parents=True)
    monkeypatch.setenv("TRACKED_UIDS", "u1")
    from src.tracker import run_tracker_day
    from src.utils import ledger
    # clean fetch + 0 events → 无事件 row
    with patch("src.tracker.fetch_weibo_posts_by_day", return_value=[]), \
         patch("src.tracker.filter_feminist_events", return_value=[]), \
         patch("src.tracker.time.sleep"):
        run_tracker_day("260707", cookie="c")
    rows = [r for r in ledger.read_rows(pipeline_dir=tmp_path) if r["收录日期"] == "260707"]
    assert rows and rows[0]["状态"] == "无事件"
    # fetch error → no attestation at all
    with patch("src.tracker.fetch_weibo_posts_by_day",
               side_effect=WebClient.FetchError("boom")), \
         patch("src.tracker.filter_feminist_events", return_value=[]), \
         patch("src.tracker.time.sleep"):
        run_tracker_day("260703", cookie="c")
    rows = [r for r in ledger.read_rows(pipeline_dir=tmp_path) if r["收录日期"] == "260703"]
    assert rows == []
