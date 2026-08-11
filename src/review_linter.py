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

# 本文件既作为包模块被导入（`from src.review_linter import ...`），也按各 agent
# 文档记载的方式以裸脚本直跑（`python src/review_linter.py <path>`）。后一种调用
# 方式下仓库根目录不在 sys.path 上，check_snapshots/main 里 `from src.xxx import`
# 会 ModuleNotFoundError——同 srcfetch.py 的开场白，同样的修法。
sys.path.insert(0, str(Path(__file__).parent.parent))

STATUS_RE = re.compile(r"^STATUS: (CLEAN|ISSUES)$")
ITEM_RE = re.compile(r"^## 问题 (\d+)\s*$", re.MULTILINE)
TYPE_RE = re.compile(r"^类型：(.+?)\s*$", re.MULTILINE)
QUOTE_RE = re.compile(r"^原文：`(.+?)`\s*$", re.MULTILINE | re.DOTALL)
DISP_RE = re.compile(r"^处理：(.*?)\s*$", re.MULTILINE)
VALID_TYPES = {"事实", "格式"}
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")
# 锚点是来源行的问题应定 事实：署名/标题/日期错误的修复点在研究文件 ## 信息来源，
# 写手无权改研究文件，定成 格式 会绕过补研究闸口（review_fact_items 只认 事实）。
# 少数纯格式形状问题（如斜体缺失）确属 格式，故只 WARN 不拦。
SRC_ANCHOR_RE = re.compile(r"(?:- )?\d{4}\.\d{2}\.\d{2}，.+?。\*")
REVIEWER_COMMENT_RE = re.compile(r"<!--\s*\[REVIEWER\]:(.*?)-->", re.S)
# fix 轮 1（评审 C-1）：手工逐字符列举排除集是错误方向——加一个漏一个（上一轮补的
# "（）「」『』【】"仍漏了"——…“”‘’·；：！？》《"等一整批评审散文常用的中文/通用标点，
# 逐个实测均被吞进"URL"），且上一轮加的 ASCII 左括号反过来把维基消歧义链接这类
# 合法带括号 URL（如 .../水星_(行星)）从中间反向截断——两个方向都是"污染后的字符串
# 永远无法通过抓取收敛"的同一类故障。改用 Unicode 区段一次性排除，不再单字符打补丁：
#    -⁯ 通用标点（— … “ ” ‘ ’ 等）
#   　-〿 CJK 标点（。、《》「」『』【】，含全角空格）
#   ＀-￯ 全角形式（， （ ） ； ： ！ ？ 等）
#   ·        中点 ·（不落在以上任何区段内，单列）
# ASCII 的 ( ) 不进排除集——切掉它们就是上一轮反噬维基链接的原因；抓漏的右括号/
# 句末标点改由 _strip_trailing() 事后剥离，且右括号只在左右不配平时才剥，
# 配平的（如 "_(行星)"）原样保留。
HTTP_RE = re.compile(
    r"https?://[^\s<>\"' -⁯　-〿＀-￯·]+"
)
_TRAILING_PUNCT = ".,;:!?"


def _strip_trailing(url: str) -> str:
    """剥掉与后续中文行文粘连、明显不属于 URL 本身的尾部字符。

    句末 ASCII 标点（. , ; : ! ?）直接剥；右括号只在这段匹配文本里左右不配平时才剥——
    维基消歧义链接这类 URL 内部合法带 (...)，配平时必须原样保留，否则抓的是个残缺 URL，
    同样永远对不上真实快照的哈希。"""
    while url:
        if url[-1] in _TRAILING_PUNCT:
            url = url[:-1]
        elif url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


@dataclass
class Item:
    num: int
    type: str | None = None
    quote: str | None = None
    disposition: str | None = None
    body: str = ""


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
        item.body = block
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
        if it.type == "格式" and it.quote and SRC_ANCHOR_RE.match(it.quote.strip()):
            v.append(
                f"WARN：问题 {it.num}: 原文锚点是来源行、类型却是 格式——署名/标题/日期"
                "错误应定 事实（修复点在研究文件；格式型会绕过补研究闸口）"
            )
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
        if (it.disposition or "").startswith("已删除（用户裁定）"):
            continue  # 用户裁定删除的内容不补研究，永远不会有标记
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


def check_snapshots(text: str, event: str) -> list[str]:
    """事实项引外部来源作反证时，该来源必须有快照。

    评审的独立性不变——它自己选哪些 URL 去查一律不受研究文件影响；这里管的只是
    「断言要有证据」：WebFetch 返回的是小模型对页面的答复，拿它去推翻一个已经逐字
    核过快照的研究文件，方向上并不比被推翻者可靠。只怀疑（"请研究阶段核实"）不需要快照。
    """
    from src.srcfetch import load as load_snapshot

    v: list[str] = []
    for it in parse_review(text).items:
        if it.type != "事实":
            continue
        # fix 轮 1（评审 M-1）：去重范围从"单条注释"提到"整个问题项"——同一 URL 分散在
        # 该项下两条不同 [REVIEWER] 注释里时只报一次；不同问题项各自独立，不跨项去重
        # （两个问题各自引同一 URL，处理的是不同问题，本来就该各报一条）。
        urls = [
            _strip_trailing(u)
            for comment in REVIEWER_COMMENT_RE.findall(it.body)
            for u in HTTP_RE.findall(comment)
        ]
        for url in dict.fromkeys(urls):
            if load_snapshot(url, event) is None:
                v.append(
                    f"问题 {it.num}: 引作反证的来源无快照——跑 src/srcfetch.py "
                    f"--event {event} --refresh {url}"
                )
    return v


def check_dispositions(text: str) -> tuple[list[str], bool]:
    """处理 行必须是五种形式之一：已修改 / 拒绝：<理由> / 已删除（查证失败） / 已删除（用户裁定） / 未解决：<缺口说明>。"""
    v, unresolved = [], False
    for it in parse_review(text).items:
        d = it.disposition
        if not d:
            v.append(f"问题 {it.num}: 处理 行为空")
        elif (
            d.startswith("已修改")
            or d.startswith("已删除（查证失败）")
            or d.startswith("已删除（用户裁定）")
        ):
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
                f"（已修改/拒绝：…/已删除（查证失败）/已删除（用户裁定）/未解决：…）"
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
        if not [x for x in violations if not x.startswith("WARN：")] and unresolved:
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

                from src.utils.research_doc import event_of

                violations += check_snapshots(text, event_of(resolved))
            else:
                violations.append(f"找不到同版本草稿：{draft}")
    for x in violations:
        print(f"  - {x}")
    if [x for x in violations if not x.startswith("WARN：")]:
        return 1
    print(f"OK{'（含 未解决 项）' if exit_code == 2 else ''}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
