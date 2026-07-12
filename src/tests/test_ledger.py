import pytest
from src.utils import ledger


def test_read_rows_missing_file_is_empty(tmp_path):
    assert ledger.read_rows(pipeline_dir=tmp_path) == []


def test_write_read_roundtrip_with_commas_and_quotes(tmp_path):
    rows = [{
        "维护日期": "260711", "收录日期": "260524", "事件编号": "1",
        "标题": '标题，含逗号和"引号"', "状态": "candidate",
        "发布日期": "", "发布标题": "", "经验提取": "",
    }]
    ledger.write_rows(rows, pipeline_dir=tmp_path)
    assert ledger.read_rows(pipeline_dir=tmp_path) == rows


def test_add_rows_prepends_block_below_header(tmp_path):
    ledger.add_rows([{"维护日期": "260610", "收录日期": "260524",
                      "事件编号": "1", "标题": "旧", "状态": "candidate"}],
                    pipeline_dir=tmp_path)
    ledger.add_rows([
        {"维护日期": "260711", "收录日期": "260705", "事件编号": "2",
         "标题": "新b", "状态": "candidate"},
        {"维护日期": "260711", "收录日期": "260705", "事件编号": "1",
         "标题": "新a", "状态": "candidate"},
    ], pipeline_dir=tmp_path)
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    # 新块在最上面，块内按（收录日期, 事件编号）升序；缺省列补空串
    assert [(r["收录日期"], r["事件编号"]) for r in rows] == [
        ("260705", "1"), ("260705", "2"), ("260524", "1")]
    assert rows[0]["发布日期"] == ""


def test_header_mismatch_raises(tmp_path):
    (tmp_path / "events.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        ledger.read_rows(pipeline_dir=tmp_path)


def test_get_and_update_row(tmp_path):
    ledger.add_rows([{"维护日期": "260711", "收录日期": "260524",
                      "事件编号": "1", "标题": "t", "状态": "candidate"}],
                    pipeline_dir=tmp_path)
    assert ledger.get_row("260524", 1, pipeline_dir=tmp_path)["标题"] == "t"
    assert ledger.get_row("260524", 9, pipeline_dir=tmp_path) is None
    ledger.update_row("260524", 1, pipeline_dir=tmp_path, **{"状态": "selected"})
    assert ledger.get_row("260524", 1, pipeline_dir=tmp_path)["状态"] == "selected"
    with pytest.raises(KeyError):
        ledger.update_row("260524", 9, pipeline_dir=tmp_path, **{"状态": "x"})


def _seed(tmp_path, state="candidate"):
    ledger.add_event("990101", 1, "标题一", state=state,
                     maint_date="260711", pipeline_dir=tmp_path)


def test_add_event_and_dedup(tmp_path):
    assert ledger.add_event("990101", 1, "t", maint_date="260711",
                            pipeline_dir=tmp_path) is True
    assert ledger.add_event("990101", 1, "t", maint_date="260711",
                            pipeline_dir=tmp_path) is False
    row = ledger.get_row("990101", 1, pipeline_dir=tmp_path)
    assert row["状态"] == "candidate" and row["维护日期"] == "260711"


def test_record_no_events_once_per_date(tmp_path):
    assert ledger.record_no_events("990102", maint_date="260711",
                                   pipeline_dir=tmp_path) is True
    assert ledger.record_no_events("990102", pipeline_dir=tmp_path) is False
    rows = ledger.read_rows(pipeline_dir=tmp_path)
    assert rows[0]["状态"] == "无事件" and rows[0]["事件编号"] == ""


def test_record_selected_flow_and_guards(tmp_path):
    _seed(tmp_path)
    ledger.record_selected("990101", 1, pipeline_dir=tmp_path)
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["状态"] == "selected"
    ledger.record_selected("990101", 1, pipeline_dir=tmp_path)  # 幂等
    ledger.record_aborted("990101", 1, pipeline_dir=tmp_path)
    with pytest.raises(RuntimeError):
        ledger.record_selected("990101", 1, pipeline_dir=tmp_path)


def test_record_aborted_guards(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="发布题",
                            pub_date="260712", pipeline_dir=tmp_path)
    with pytest.raises(RuntimeError):
        ledger.record_aborted("990101", 1, pipeline_dir=tmp_path)


def test_record_published_sets_fields_and_harvest(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="发布题",
                            pub_date="260712", pipeline_dir=tmp_path)
    row = ledger.get_row("990101", 1, pipeline_dir=tmp_path)
    assert row["状态"] == "published"
    assert row["发布日期"] == "260712"
    assert row["发布标题"] == "发布题"
    assert row["经验提取"] == "待提取"
    # 幂等：重复发布不改字段
    ledger.record_published("990101", 1, pub_title="另一题", pipeline_dir=tmp_path)
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["发布标题"] == "发布题"


def test_record_published_missing_row_raises(tmp_path):
    with pytest.raises(KeyError):
        ledger.record_published("990101", 9, pipeline_dir=tmp_path)


def test_max_index(tmp_path):
    assert ledger.max_index("990101", pipeline_dir=tmp_path) == 0
    ledger.add_event("990101", 2, "b", pipeline_dir=tmp_path)
    ledger.add_event("990101", 1, "a", pipeline_dir=tmp_path)
    assert ledger.max_index("990101", pipeline_dir=tmp_path) == 2


def _artifacts(tmp_path, *relpaths):
    for rel in relpaths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")


def test_reconcile_derives_stage_and_version(tmp_path):
    _seed(tmp_path, state="selected")
    _artifacts(tmp_path,
               "research/990101-1-标题一.md",
               "draft/990101-1-标题一-v1.md",
               "draft/990101-1-标题一-v2.md")
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "draft-v2"}
    _artifacts(tmp_path, "review/990101-1-标题一-v2.md")
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "review-v2"}
    # 对账结果写回了 CSV
    assert ledger.get_row("990101", 1, pipeline_dir=tmp_path)["状态"] == "review-v2"


def test_reconcile_draft_version_beats_older_review(tmp_path):
    _seed(tmp_path, state="selected")
    _artifacts(tmp_path,
               "draft/990101-1-标题一-v1.md",
               "draft/990101-1-标题一-v2.md",
               "review/990101-1-标题一-v1.md")
    # draft-v2 postdates review-v1 (review only covers v1) → true state is draft-v2
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "draft-v2"}
    _artifacts(tmp_path, "review/990101-1-标题一-v2.md")
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "review-v2"}


def test_derive_state_skips_non_numeric_version_suffix(tmp_path):
    _seed(tmp_path, state="selected")
    _artifacts(tmp_path,
               "draft/990101-1-标题一-v1.md",
               "draft/990101-1-标题一-video.md")
    # "-video.md" matches the glob (contains "-v") but its version suffix
    # isn't numeric; must be skipped rather than crashing int().
    assert ledger.event_statuses("990101", pipeline_dir=tmp_path) == {1: "draft-v1"}


def test_reconcile_ignores_terminal_and_other_events(tmp_path):
    _seed(tmp_path)
    ledger.add_event("990101", 10, "十", pipeline_dir=tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    # 事件 1 的工件不得污染事件 10（前缀含结尾连字符）
    _artifacts(tmp_path, "draft/990101-1-标题一-v3.md")
    st = ledger.event_statuses("990101", pipeline_dir=tmp_path)
    assert st == {1: "published", 10: "candidate"}


def test_is_date_terminal(tmp_path):
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is False  # 无行
    _seed(tmp_path)
    ledger.add_event("990101", 2, "二", pipeline_dir=tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is False
    ledger.record_aborted("990101", 2, pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990101", pipeline_dir=tmp_path) is True
    ledger.record_no_events("990103", pipeline_dir=tmp_path)
    assert ledger.is_date_terminal("990103", pipeline_dir=tmp_path) is True


def test_post_slug_second_published_gets_suffix(tmp_path):
    _seed(tmp_path)
    ledger.add_event("990101", 2, "二", pipeline_dir=tmp_path)
    assert ledger.post_slug("990101", 1, pipeline_dir=tmp_path) == "990101"
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.post_slug("990101", 2, pipeline_dir=tmp_path) == "990101-2"


def test_harvest_queue_roundtrip(tmp_path):
    _seed(tmp_path)
    ledger.record_published("990101", 1, pub_title="t", pipeline_dir=tmp_path)
    assert ledger.pending_harvest(pipeline_dir=tmp_path) == [("990101", 1)]
    ledger.mark_harvested("990101", 1, pipeline_dir=tmp_path)
    assert ledger.pending_harvest(pipeline_dir=tmp_path) == []


def test_get_untracked_dates_uses_ledger_coverage(tmp_path):
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).strftime("%y%m%d")
    assert yesterday in ledger.get_untracked_dates(pipeline_dir=tmp_path)
    ledger.record_no_events(yesterday, pipeline_dir=tmp_path)
    assert yesterday not in ledger.get_untracked_dates(pipeline_dir=tmp_path)
    assert len(ledger.get_untracked_dates(days=3, pipeline_dir=tmp_path)) == 2
