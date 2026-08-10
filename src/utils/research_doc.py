"""研究文件的结构解析 —— 节切分、书目行、摘录层。

research_linter（闸口）、linter（草稿逐字基准）、srcfetch（批量抓快照）三处都要读
同一套结构，解析放在这里，不在各处各写一份正则。
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

# 与 research_linter.SRC_PARSE_RE 同形：- YYYY.MM.DD，来源名。*标题*。URL 其余
# URL 段排除全角破折号「—」：" — " 缺空格时（如 "URL—快照失败：..."）\S+ 会把破折号
# 后的内容整段吞进 URL，「快照失败」标记随之从 tail 消失，snapshot_failed 被静默
# 判成 False——而这里解析出的 Source 直接喂给 srcfetch --from-research（研究阶段
# 抓快照时，文件还没被 research_linter lint 过），静默口子不能只堵在 linter 一侧。
SRC_PARSE_RE = re.compile(r"^- (\d{4}\.\d{2}\.\d{2})，(.+?)。\*(.+?)\*。([^\s—]+)(.*)$")
SNAPSHOT_FAILED = "快照失败"
_EVENT_RE = re.compile(r"^(\d{6}-\d+)-")


@dataclass
class Source:
    num: int          # 信源号 ＝ 在 ## 信息来源 中的 1-based 出现次序
    date: str
    name: str
    title: str
    url: str
    tail: str         # URL 之后的部分（快照状态等）
    snapshot_failed: bool


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def sources(text: str) -> list[Source]:
    out: list[Source] = []
    for ln in (sections(text).get("信息来源") or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        m = SRC_PARSE_RE.match(ln)
        if not m:
            continue
        out.append(Source(
            num=len(out) + 1,
            date=m.group(1), name=m.group(2), title=m.group(3),
            url=m.group(4), tail=m.group(5),
            snapshot_failed=SNAPSHOT_FAILED in m.group(5),
        ))
    return out


def event_of(path: Path) -> str:
    """从研究/评审/草稿文件名取事件标识（YYMMDD-N），用于定位快照目录。"""
    m = _EVENT_RE.match(path.name)
    if not m:
        raise ValueError(f"文件名不含事件标识（YYMMDD-N-）：{path.name}")
    return m.group(1)


# 摘录头：[E12] 信源3 · 正文原话 · 2026-08-07
EXTRACT_HEAD_RE = re.compile(r"^\[E(\d+)\]\s+(.+?)\s+·\s+(.+?)\s+·\s+(.+?)\s*$")
E_REF_RE = re.compile(r"\[E(\d+)\]")
# 宽判据：看起来想当摘录标签（行首 [E...，容许误加的列表前缀 ／ 全角方括号），但不保证
# 真解析得出来。只用来识别"标签写歪了"的行——EXTRACT_HEAD_RE 本身不放宽，格式漂移不能
# 被悄悄吃掉。左方括号接受全角「［」：中文输入法全角/半角切换下默认敲出的就是它，不是
# 边缘输入；不放宽会导致该行既不匹配 EXTRACT_HEAD_RE 也不匹配这条宽判据，从而被当成普通
# 正文并入上一条摘录的 body（Task 4 修过的误挂，原样在全角方括号上复现）。
LOOSE_HEAD_RE = re.compile(r"^-?\s*[\[［]E")
# 只有 正文原话 能作写手灰字的依据；标题惯把第三人称改写成第一人称，转述同理。
# 图上转录指向资产图，图是二进制、字节比对不成立，是「有出处但机械核不了」的唯一缺口。
FORMS = {"正文原话", "第三人称转述", "标题", "图上转录"}


@dataclass
class Extract:
    eid: int
    ref: str          # "信源N" 或 "资产 <文件名>"
    form: str
    fetched: str      # 快照日期，图上转录为 "—"
    body: str


def extracts(text: str) -> list[Extract]:
    out: list[Extract] = []
    buf: list[str] = []
    # 上一行是畸形标签：正文归属未知，之后的行一律不并入任何摘录，直到下一个合法标签
    # 出现为止——否则畸形标签自己的正文会被静静并进上一条摘录，冒充它的引文核过闸口。
    orphaned = False
    for ln in (sections(text).get("摘录") or "").splitlines():
        s = ln.strip()
        m = EXTRACT_HEAD_RE.match(s)
        if m:
            if out and not orphaned:
                out[-1].body = " ".join(buf).strip()
            buf = []
            orphaned = False
            out.append(Extract(eid=int(m.group(1)), ref=m.group(2).strip(),
                               form=m.group(3).strip(), fetched=m.group(4).strip(),
                               body=""))
        elif LOOSE_HEAD_RE.match(s):
            if out and not orphaned:
                out[-1].body = " ".join(buf).strip()
            buf = []
            orphaned = True
        elif not orphaned and out and s and not s.startswith("<!--"):
            buf.append(s)
    if out and not orphaned:
        out[-1].body = " ".join(buf).strip()
    return out


def malformed_extract_heads(text: str) -> list[str]:
    """`## 摘录` 里像标签却解析不了的行，原样返回供 linter 报违规。"""
    out: list[str] = []
    for ln in (sections(text).get("摘录") or "").splitlines():
        s = ln.strip()
        if LOOSE_HEAD_RE.match(s) and not EXTRACT_HEAD_RE.match(s):
            out.append(s)
    return out


def is_new_format(text: str) -> bool:
    """有 ## 摘录 节＝两层制新格式。在途事件不带这一节，走旧规则收尾。"""
    return "摘录" in sections(text)
