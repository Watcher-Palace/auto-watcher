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
