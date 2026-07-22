import pytest
from pathlib import Path
from src.publish_summary import publish_summary

def _env(tmp_path, monkeypatch, fm='summary_month: "2605"'):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr("src.utils.pipeline.REPO_ROOT", tmp_path)
    d = tmp_path / "_pipeline" / "summary"; d.mkdir(parents=True)
    (d / "2605.md").write_text(f"---\ntitle: t\n{fm}\n---\n正文", encoding="utf-8")

def test_publish_summary_copies_draft(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    publish_summary("2605", deploy=False)
    assert (tmp_path / "source" / "summaries" / "2605.md").read_text(encoding="utf-8").endswith("正文")

def test_publish_summary_rejects_wrong_month(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, fm='summary_month: "2604"')
    with pytest.raises(SystemExit):
        publish_summary("2605", deploy=False)
