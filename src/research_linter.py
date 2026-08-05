"""研究文件机械闸口 —— initial/update 研究完成前都必须通过（blog-researcher 的 lint gate）。

FAIL＝阻断；"WARN："前缀的条目只提示不阻断（LINT OK 下方照常打印）。
这些检查只拦"形状"——裸平台品牌作来源名、带引号摘录缺形态标注、标题疑似抄自
URL slug、来源 URL 落在本站追踪账号——署名与标题的**真伪**没有网络判不了，
仍靠研究阶段打开页面核。
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

try:
    from src.linter import tracked_uids
except ImportError:  # 以脚本方式直跑时无包上下文
    from linter import tracked_uids

REQUIRED = ("事实", "当事方", "信息来源", "资产")
# 日期必须补零（2026.01.01）。此处若放行 \d{1,2}，研究阶段随手选的格式会经
# linter.py --research 的逐字比对变成对写手的硬约束：写手照 template 的补零
# 惯例写反而 LINT FAIL，只能倒回去迁就研究文件，格式污染随之进入已发布文章。
SRC_RE = re.compile(r"^- \d{4}\.\d{2}\.\d{2}，.+?。\*.+?\*。\S+")
SRC_PARSE_RE = re.compile(r"^- (\d{4}\.\d{2}\.\d{2})，(.+?)。\*(.+?)\*。(\S+)(.*)$")
UNVERIFIED = "发布日期查证失败"
BLUE_RE = re.compile(r'<font color="blue">(.*?)</font>', re.S)
DATE_IN_RE = re.compile(r"\d{4}年|\d{1,2}月\d{1,2}日")
NO_PROGRESS_RE = re.compile(r"暂无|尚未|无最新进展|未发布通报")
ASSET_LINE_RE = re.compile(r"^- (\S+?) — ")
# 转载/托管门户的品牌本身几乎从不是署名出处（用户裁定 2026-07-20；同批 6 处翻车
# 见 casebook 260721-1/260721-5/260722-2/260723-1）。裸品牌 FAIL；带括注（账号/
# 栏目/转载链条说明）的放行——括注本身就是"核对过署名"的自证。
PLATFORM_BRANDS = {"搜狐", "新浪", "新浪新闻", "新浪财经", "网易", "网易新闻",
                   "腾讯新闻", "腾讯网", "Yahoo新闻香港", "雅虎", "今日头条", "百家号"}
# 摘录带引号时必须标出处形态（用户裁定 2026-08-03）。词表宽握（转述/转录也算数），
# 拦的是"完全没标"，不是用词偏好。
FORM_TOKENS = ("正文原话", "第三人称转述", "标题", "转述", "转录")


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _slug_tokens(url: str) -> list[str]:
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tokens = [t.lower() for t in re.split(r"[-_]", slug) if t]
    # 末尾纯数字长 token 多为站点文章 id（…-met-officers-498512），不算标题词
    if tokens and tokens[-1].isdigit() and len(tokens[-1]) >= 5:
        tokens.pop()
    return tokens


def lint_research(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    vs: list[str] = []
    secs = _sections(text)
    for r in REQUIRED:
        if r not in secs:
            vs.append(f"缺少必需章节 ## {r}")
    src_text = secs.get("信息来源") or ""
    for ln in src_text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        if not SRC_RE.match(ln) and UNVERIFIED not in ln:
            vs.append(f"来源行格式不符（- YYYY.MM.DD，来源。*标题*。URL — 摘录）：{ln[:40]}")
            continue
        m2 = SRC_PARSE_RE.match(ln)
        if not m2:
            continue
        name, title, url, tail = m2.group(2), m2.group(3), m2.group(4), m2.group(5)
        if name in PLATFORM_BRANDS:
            vs.append(
                f"来源名是裸平台品牌「{name}」——写正文/文末署名的原始媒体，"
                f"或括注账号/栏目/转载链条：{ln[:40]}"
            )
        has_quote = "「" in tail or "“" in tail or tail.count('"') >= 2
        if has_quote and not any(t in tail for t in FORM_TOKENS):
            vs.append(f"摘录带引号但缺形态标注（正文原话/标题/第三人称转述）：{ln[:40]}")
        title_tokens = re.findall(r"[a-z0-9]+", title.lower().replace("'", ""))
        if len(title_tokens) >= 3 and _slug_tokens(url) == title_tokens:
            vs.append(f"WARN：标题与 URL slug 完全一致——核对页面真标题（slug 未必是真标题）：{ln[:40]}")
    for uid in sorted(tracked_uids()):
        if re.search(rf"weibo\.com/{re.escape(uid)}/", src_text):
            vs.append(
                f"来源 URL 指向本站追踪账号 uid {uid}（安全事项，用户裁定 2026-08-04）"
                "——换该内容自己的原始出处，取不到就不收"
            )
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
        fatal = [v for v in vs if not v.startswith("WARN：")]
        warns = [v for v in vs if v.startswith("WARN：")]
        if fatal:
            rc = 1
            print(f"LINT FAIL {p}")
            for v in fatal:
                print(f"  - {v}")
        else:
            print(f"LINT OK {p}")
        for v in warns:
            print(f"  ~ {v}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
