"""文档一致性：把 2026-07-22 审计的 prose 不变量固化进 CI（无模型断言，用户裁定）。"""
from pathlib import Path
import re

ROOT = Path(__file__).parents[2]
AGENTS = sorted((ROOT / ".claude" / "agents").glob("*.md"))
DOCS = AGENTS + sorted((ROOT / ".claude" / "skills").rglob("*.md")) + [ROOT / "CLAUDE.md"]


def test_human_section_single_spelling():
    for p in DOCS:
        assert "人类的裁定" not in p.read_text(encoding="utf-8"), f"{p}: 用 人类意见"


def test_agent_files_within_line_cap():
    for p in AGENTS:
        n = len(p.read_text(encoding="utf-8").splitlines())
        assert n <= 180, f"{p.name} {n} 行 > 180（curate 规定需压缩）"


def test_experience_sections_within_entry_cap():
    for p in AGENTS:
        text = p.read_text(encoding="utf-8")
        if "## 累积经验" not in text:
            continue
        tail = text.split("## 累积经验", 1)[1]
        entries = re.findall(r"^- \[(?:NOTE|CANDIDATE)\]", tail, re.MULTILINE)
        assert len(entries) <= 15, f"{p.name} 累积经验 {len(entries)} 条 > 15"
