import pytest
from datetime import date, datetime

from src.tracker import CN_TZ, RateLimited, run_tracker_daily
from src.utils.tracker_state import DEFAULT_STATE, load_state, save_state


def test_load_missing_returns_default(tmp_path):
    s = load_state(tmp_path / "none.json")
    assert s == DEFAULT_STATE


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = load_state(p)
    s["uids"]["111"] = {"last_seen_id": "5300000000000001", "pending": None}
    save_state(s, p)
    assert load_state(p)["uids"]["111"]["last_seen_id"] == "5300000000000001"


def _post(pid, day, text="家暴 事件", top=False):
    dt = datetime(2026, 7, day, 12, 0, tzinfo=CN_TZ)
    return {
        "id": pid, "url": f"u/{pid}", "text": text,
        "retweet_text": "", "created_dt": dt, "is_top": top,
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    pipe = tmp_path / "_pipeline"
    (pipe / "events").mkdir(parents=True)
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", pipe)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("TRACKED_UIDS", "111")
    monkeypatch.setattr(
        "src.tracker.filter_feminist_events",
        lambda posts: [
            {"title": p["text"][:5], "brief": p["text"], "sources": [p["url"]]}
            for p in posts
        ],
    )
    return pipe


def test_daily_stops_at_last_seen(env, monkeypatch):
    pages = {1: [_post("200", 2), _post("150", 1)], 2: [_post("100", 1)]}
    calls = []

    def fake_fetch(web, uid, page=1):
        calls.append(page)
        return pages.get(page, [])

    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    sp = env / ".tracker-state.json"
    save_state({"uids": {"111": {"last_seen_id": "150", "pending": None}}}, sp)

    run_tracker_daily(cookie="c", budget=10, state_path=sp, today=date(2026, 7, 3))

    assert calls == [1]  # page 2 never fetched: page 1 already contained a seen post
    assert load_state(sp)["uids"]["111"]["last_seen_id"] == "200"
    assert (env / "events" / "260702.md").exists()
    content = (env / "events" / "260702.md").read_text(encoding="utf-8")
    assert "u/200" in content and "u/150" not in content


def test_daily_budget_exhaustion_persists_cursor(env, monkeypatch):
    def fake_fetch(web, uid, page=1):
        return [_post(str(1000 - page * 10 - i), 2) for i in range(2)]

    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    sp = env / ".tracker-state.json"

    run_tracker_daily(cookie="c", budget=1, state_path=sp, today=date(2026, 7, 3))

    pend = load_state(sp)["uids"]["111"]["pending"]
    assert pend and pend["next_page"] == 2


def test_daily_rate_limited_persists_and_exits_2(env, monkeypatch):
    def fake_fetch(web, uid, page=1):
        raise RateLimited()

    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    sp = env / ".tracker-state.json"

    with pytest.raises(SystemExit) as ei:
        run_tracker_daily(cookie="c", budget=10, state_path=sp, today=date(2026, 7, 3))
    assert ei.value.code == 2
    pend = load_state(sp)["uids"]["111"]["pending"]
    assert pend and pend["next_page"] == 1


def test_daily_first_run_walks_back_to_cutoff(env, monkeypatch):
    # no prior state: walk until posts older than DAILY_FIRST_RUN_DAYS
    pages = {
        1: [_post("300", 3)],
        2: [_post("200", 2)],
        3: [_post("100", 1)],   # 2026-07-01: older than cutoff (today-3 = 06-30)? no
    }
    # make page 3's post clearly older than cutoff
    old = _post("100", 1)
    old["created_dt"] = datetime(2026, 6, 25, 12, 0, tzinfo=CN_TZ)
    pages[3] = [old]
    calls = []

    def fake_fetch(web, uid, page=1):
        calls.append(page)
        return pages.get(page, [])

    monkeypatch.setattr("src.tracker.fetch_weibo_posts", fake_fetch)
    sp = env / ".tracker-state.json"

    run_tracker_daily(cookie="c", budget=10, state_path=sp, today=date(2026, 7, 3))

    assert calls == [1, 2, 3]
    st = load_state(sp)["uids"]["111"]
    assert st["last_seen_id"] == "300"
    assert st["pending"] is None
    assert (env / "events" / "260703.md").exists()
    assert (env / "events" / "260702.md").exists()
