"""研究文件机械闸口 —— initial 研究完成前必须通过（blog-researcher 的 lint gate）。"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REQUIRED = ("事实", "当事方", "信息来源", "资产")
SRC_RE = re.compile(r"^- \d{4}\.\d{1,2}\.\d{1,2}，.+?。\*.+?\*。\S+")
UNVERIFIED = "发布日期查证失败"
BLUE_RE = re.compile(r'<font color="blue">(.*?)</font>', re.S)
DATE_IN_RE = re.compile(r"\d{4}年|\d{1,2}月\d{1,2}日")
NO_PROGRESS_RE = re.compile(r"暂无|尚未|无最新进展|未发布通报")
ASSET_LINE_RE = re.compile(r"^- (\S+?) — ")


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def lint_research(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    vs: list[str] = []
    secs = _sections(text)
    for r in REQUIRED:
        if r not in secs:
            vs.append(f"缺少必需章节 ## {r}")
    for ln in (secs.get("信息来源") or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        if not SRC_RE.match(ln) and UNVERIFIED not in ln:
            vs.append(f"来源行格式不符（- YYYY.MM.DD，来源。*标题*。URL — 摘录）：{ln[:40]}")
    blues = BLUE_RE.findall(text)
    if len(blues) != 1:
        vs.append(f"蓝字标记应恰好 1 处（现 {len(blues)} 处）")
    else:
        if not DATE_IN_RE.search(blues[0]):
            vs.append("蓝字未标明进展日期——写手无法定 date")
        if NO_PROGRESS_RE.search(blues[0]):
            vs.append("蓝字是'暂无进展'类句子——必须是真实事实进展")
    m = re.match(r"(\d{6})-(\d+)-", path.name)
    if m and "资产" in secs:
        assets_dir = path.parent.parent / "draft" / f"{m.group(1)}-{m.group(2)}-assets"
        listed = {a.group(1) for l in secs["资产"].splitlines()
                  if (a := ASSET_LINE_RE.match(l.strip()))}
        present = {p.name for p in assets_dir.iterdir()} if assets_dir.is_dir() else set()
        vs += [f"资产登记的文件不存在：{n}" for n in sorted(listed - present)]
        vs += [f"资产文件未登记：{n}" for n in sorted(present - listed)]
    return vs


def main(argv: list[str]) -> int:
    rc = 0
    for p in argv:
        vs = lint_research(Path(p))
        if vs:
            rc = 1
            print(f"LINT FAIL {p}")
            for v in vs:
                print(f"  - {v}")
        else:
            print(f"LINT OK {p}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
