"""评审文件校验器 —— 硬化评审格式的机器检查。

模式：默认（格式+原文锚点，草稿路径由 review→draft 目录互换推导）、
--check-marks <research-path>（格式+事实项标记完备性）、
--check-dispositions（格式+处理完备性；无违规但存在 未解决 时退出码 2）。
退出码：0 通过；1 违规；2 仅 dispositions 模式：处理齐全但含 未解决。
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

STATUS_RE = re.compile(r"^STATUS: (CLEAN|ISSUES)$")
ITEM_RE = re.compile(r"^## 问题 (\d+)\s*$", re.MULTILINE)
TYPE_RE = re.compile(r"^类型：(.+?)\s*$", re.MULTILINE)
QUOTE_RE = re.compile(r"^原文：`(.+?)`\s*$", re.MULTILINE | re.DOTALL)
DISP_RE = re.compile(r"^处理：(.*?)\s*$", re.MULTILINE)
VALID_TYPES = {"事实", "格式"}
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")


@dataclass
class Item:
    num: int
    type: str | None = None
    quote: str | None = None
    disposition: str | None = None


@dataclass
class Review:
    status: str | None = None
    items: list[Item] = field(default_factory=list)


def parse_review(text: str) -> Review:
    first = text.splitlines()[0] if text.splitlines() else ""
    m = STATUS_RE.match(first)
    review = Review(status=m.group(1) if m else None)
    # 只解析到下一个 ## 标题为止的块，避免吞掉 标签提案/人类意见 等节
    matches = list(ITEM_RE.finditer(text))
    for i, im in enumerate(matches):
        start = im.end()
        next_heading = re.compile(r"^## ", re.MULTILINE).search(text, start)
        end = next_heading.start() if next_heading else len(text)
        block = text[start:end]
        item = Item(num=int(im.group(1)))
        if (t := TYPE_RE.search(block)):
            item.type = t.group(1)
        if (q := QUOTE_RE.search(block)):
            item.quote = q.group(1)
        if (d := DISP_RE.search(block)):
            item.disposition = d.group(1)
        review.items.append(item)
    return review


def validate_format(text: str) -> list[str]:
    v: list[str] = []
    r = parse_review(text)
    if r.status is None:
        v.append("第 1 行必须是 STATUS: CLEAN 或 STATUS: ISSUES")
    if r.status == "CLEAN" and r.items:
        v.append("STATUS: CLEAN 不得包含 问题 项")
    if r.status == "ISSUES" and not r.items:
        v.append("STATUS: ISSUES 必须至少包含一个 问题 项")
    nums = [it.num for it in r.items]
    if nums != list(range(1, len(nums) + 1)):
        v.append(f"问题编号必须从 1 连续递增，实际为 {nums}")
    for it in r.items:
        if it.type is None:
            v.append(f"问题 {it.num}: 缺少 类型 行")
        elif it.type not in VALID_TYPES:
            v.append(f"问题 {it.num}: 类型 必须是 事实 或 格式，实际为 {it.type}")
        if it.quote is None:
            v.append(f"问题 {it.num}: 缺少 原文：`...` 行")
        if it.disposition is None:
            v.append(f"问题 {it.num}: 缺少 处理： 行")
    return v


def validate_anchors(text: str, draft_text: str) -> list[str]:
    v = []
    for it in parse_review(text).items:
        if it.quote and it.quote not in draft_text:
            v.append(f"问题 {it.num}: 原文引文未在草稿中逐字出现")
    return v


def check_marks(text: str, research_text: str, version: int) -> list[str]:
    v = []
    for it in parse_review(text).items:
        if it.type != "事实":
            continue
        if f"（评审v{version}-问题{it.num}）" not in research_text:
            v.append(f"问题 {it.num}: 研究文件缺少（评审v{version}-问题{it.num}）标记")
    return v


def check_tag_proposals(review_text: str, draft_text: str) -> list[str]:
    """草稿的 [TAG-PROPOSAL] 注释必须逐条转录进评审文件的 ## 标签提案 节，否则会随草稿修订消失。"""
    vs = []
    for prop in TAG_PROPOSAL_RE.findall(draft_text):
        name = prop.split("—")[0].split("-")[0].strip()
        if name and name not in review_text:
            vs.append(f"草稿的标签提案未转录进评审 ## 标签提案：{name}")
    return vs


def check_dispositions(text: str) -> tuple[list[str], bool]:
    """处理 行必须是四种形式之一：已修改 / 拒绝：<理由> / 已删除（查证失败） / 未解决：<缺口说明>。"""
    v, unresolved = [], False
    for it in parse_review(text).items:
        d = it.disposition
        if not d:
            v.append(f"问题 {it.num}: 处理 行为空")
        elif d.startswith("已修改") or d.startswith("已删除（查证失败）"):
            pass  # 合法；允许其后附加说明
        elif d.startswith("拒绝："):
            if not d[len("拒绝："):].strip():
                v.append(f"问题 {it.num}: 拒绝： 后必须给出理由")
        elif d.startswith("未解决："):
            if d[len("未解决："):].strip():
                unresolved = True
            else:
                v.append(f"问题 {it.num}: 未解决： 后必须给出缺口说明")
        else:
            v.append(
                f"问题 {it.num}: 处理 值不在词汇表"
                f"（已修改/拒绝：…/已删除（查证失败）/未解决：…）"
            )
    return v, unresolved


def main(argv: list[str]) -> int:
    review_path = Path(argv[0])
    text = review_path.read_text(encoding="utf-8")
    violations = validate_format(text)
    exit_code = 0
    if "--check-dispositions" in argv:
        dv, unresolved = check_dispositions(text)
        violations += dv
        if not violations and unresolved:
            exit_code = 2
    elif "--check-marks" in argv:
        research = Path(argv[argv.index("--check-marks") + 1])
        version = int(review_path.stem.rsplit("-v", 1)[-1])
        violations += check_marks(text, research.read_text(encoding="utf-8"), version)
    else:
        resolved = review_path.resolve()
        if resolved.parent.name != "review":
            violations.append("评审文件必须位于 review/ 目录下（用于推导同版本草稿路径）")
        else:
            draft = resolved.parent.parent / "draft" / resolved.name
            if draft.exists():
                draft_text = draft.read_text(encoding="utf-8")
                violations += validate_anchors(text, draft_text)
                violations += check_tag_proposals(text, draft_text)
            else:
                violations.append(f"找不到同版本草稿：{draft}")
    for x in violations:
        print(f"  - {x}")
    if violations:
        return 1
    print(f"OK{'（含 未解决 项）' if exit_code == 2 else ''}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
