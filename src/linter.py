"""Mechanical draft linter — catches format violations before the Sonnet review.

Checks are deterministic only (no judgment calls): em dashes, 舆论 without
concrete metrics, source-line format, unregistered tags, invalid categories,
future dates, missing required sections.
"""
from __future__ import annotations
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.publisher import read_frontmatter, load_tag_registry, load_tag_group

VALID_CATEGORIES = {"S", "A", "B", "C", "D", "M", "N"}
# 犯罪 tag 必须同时带一个具体罪名，或说明为什么没有罪名（用户裁定 2026-07-20）
CHARGE_GAP_TAGS = {"未立案", "罪名未公开"}
# 具体数据：计量词，或"数字+转发/评论/点赞/观看"这类计数写法
METRIC_RE = re.compile(
    r"(阅读量|讨论量|转发量|评论量|访问量|播放量|观看量|点赞量|投票|票数"
    r"|[\d.]+\s*[万亿]?\s*(?:条)?\s*(?:转发|评论|点赞|观看|播放|次浏览))"
)
SOURCE_LINE_RE = re.compile(r"^(- )?\d{4}\.\d{1,2}\.\d{1,2}，.+?。\*.+?\*。\S+")
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")
ASSET_REF_RE = re.compile(r"\{%\s*asset_path\s+(.+?)\s*%\}")
# C3（审计裁定，2026-07-22）：填充语/蓝字进展标记为 FAIL；舆论反应措辞为 WARN
FILLER_FAIL_RE = re.compile(r"此事沉寂数月后|网友纷纷表示")
OPINION_WARN_RE = re.compile(r"引发广泛关注|引起广泛关注|引发关注|引发热议")
TITLE_OPINION_RE = re.compile(r"引争议|引发争议|引质疑|引发质疑|引发关注|引发热议|惹众怒")
BLUE_RE = re.compile(r'<font color="blue">(.*?)</font>', re.S)
NO_PROGRESS_RE = re.compile(r"暂无|尚未|无最新进展|未发布通报")
# C1（审计裁定，2026-07-22）：草稿信息来源行必须能在研究文件里核对到；人物称呼只警告
DRAFT_SRC_RE = re.compile(r"^(?:- )?(\d{4}\.\d{1,2}\.\d{1,2})，(.+?)。\*(.+?)\*。(\S+)", re.M)
NAME_RE = re.compile(r"[一-龥]{1,2}(?:某某|某|女士|先生)|小[一-龥]")
ALIAS_RE = re.compile(r"([一-龥]{2,3})（(?:报道使用)?化名）")


def _sections(body: str) -> dict[str, str]:
    """Map '## X' heading → section text (up to next ## heading)."""
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def lint_text(content: str, registry: set[str] | None, today: date) -> list[str]:
    violations: list[str] = []
    fm = read_frontmatter(content)
    body = content.split("---", 2)[-1] if content.startswith("---") else content

    prose = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    if "—" in prose:
        violations.append("破折号 — 出现（风格规则：重组句子，不用破折号）")

    secs = _sections(body)
    for required in ("概述", "信息来源"):
        if required not in secs:
            violations.append(f"缺少必需章节 ## {required}")

    if "舆论" in secs:
        s = secs["舆论"]
        if not (METRIC_RE.search(s) and re.search(r"\d", s)):
            violations.append(
                "## 舆论 无具体数据（阅读量/讨论量/转发量/评论量）——无数据时整节删除"
            )

    for sec in ("前情", "后续"):
        if sec in secs:
            lines = [l for l in secs[sec].splitlines() if l.strip() and not l.strip().startswith("<!--")]
            if lines and not any(re.search(r"参见：\[.+?\]\(/\d{4}/", l) for l in lines):
                violations.append(f"## {sec} 缺站内 参见 链接——该节仅用于链接本站已发布文章")

    if "信息来源" in secs:
        for ln in secs["信息来源"].splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("<!--"):
                continue
            if not SOURCE_LINE_RE.match(ln):
                violations.append(
                    f"信息来源 行格式不符（YYYY.MM.DD，来源。*标题*。URL）：{ln[:50]}"
                )

    cats = fm.get("categories")
    cat_list = cats if isinstance(cats, list) else [cats]
    for c in cat_list:
        if c not in VALID_CATEGORIES:
            violations.append(f"categories 非法值：{c!r}（允许 S/A/B/C/D/M/N）")

    tags = fm.get("tags") or []
    if not tags and not TAG_PROPOSAL_RE.search(content):
        violations.append(
            "tags 为空且无 TAG-PROPOSAL —— 选 2 个以上贴切标签，或用 "
            "<!-- [TAG-PROPOSAL]: 标签名 — 理由 --> 提案新标签"
        )
    if registry:
        for t in tags:
            if t not in registry:
                violations.append(f"未注册 tag：{t}（见 src/tags.yml）")

    if "犯罪" in tags:
        charges = load_tag_group("charge")
        has_charge = any(t in charges for t in tags)
        has_gap = any(t in CHARGE_GAP_TAGS for t in tags)
        if not (has_charge or has_gap):
            violations.append(
                "有 犯罪 tag 但无具体罪名 —— 加官方指控/判决的完整罪名（见 src/tags.yml "
                "charge 组），无刑事立案加 未立案，已立案但官方未公布罪名加 罪名未公开"
            )

    d = fm.get("date")
    if isinstance(d, datetime) or (isinstance(d, str) and re.search(r"\d{2}:\d{2}", d)):
        violations.append("date 含时间成分 —— 只写 YYYY-MM-DD（无 00:00:00）")
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            d = None
            violations.append(f"date 无法解析：{fm.get('date')!r}")
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date) and d > today:
        violations.append(f"date 在未来：{d.isoformat()}")

    if FILLER_FAIL_RE.search(prose):
        violations.append("填充语出现（此事沉寂数月后/网友纷纷表示 类）——直接陈述事实")
    blues = BLUE_RE.findall(prose)
    if len(blues) != 1:
        violations.append(f"蓝字标记应恰好 1 处（现 {len(blues)} 处）——标最新真实进展")
    elif NO_PROGRESS_RE.search(blues[0]):
        violations.append("蓝字内容是'暂无进展'类句子——蓝字必须是真实事实进展")

    return violations


def lint_warnings(content: str) -> list[str]:
    """Reviewer-waivable issues: reported, but never block a draft."""
    # user decision 2026-07-19: standalone ## 前情 / ## 后续 are legal per template
    fm = read_frontmatter(content)
    prose = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    warnings: list[str] = []
    title = str(fm.get("title") or "")
    m = TITLE_OPINION_RE.search(title)
    if m:
        warnings.append(f"标题含舆论反应词（{m.group()}）——除非争议即事件主体，删掉")
    if OPINION_WARN_RE.search(prose):
        warnings.append("正文含舆论反应措辞（引发关注类）——舆论事件难免时可保留，否则删")
    return warnings


def lint_slug_title(path: Path, fm_title: str) -> list[str]:
    """草稿文件名形如 YYMMDD-N-标签-vN.md 时，标题不得与内部索引标签相同。"""
    m = re.match(r"\d{6}-\d+-(.+)-v\d+$", path.stem)
    if m and fm_title.strip() == m.group(1):
        return ["title 与内部索引标签相同——标题必须另写（信息完整、能独立读懂）"]
    return []


def assets_dir_for(path: Path) -> Path:
    """草稿 `_pipeline/draft/{date}-{n}-title-vN.md` → `{date}-{n}-assets/`；
    已发布 `source/_posts/{slug}.md` → `source/_posts/{slug}/`。"""
    m = re.match(r"(\d{6})-(\d+)-", path.name)
    if m and path.parent.name == "draft":
        return path.parent / f"{m.group(1)}-{m.group(2)}-assets"
    return path.parent / path.stem


def lint_assets(path: Path, content: str) -> tuple[list[str], list[str]]:
    """引用的资产必须真实存在；抓到但没用上的资产只警告，不拦。"""
    refs = {m.group(1).strip().strip("\"'") for m in ASSET_REF_RE.finditer(content)}
    assets = assets_dir_for(path)
    present = {p.name for p in assets.iterdir()} if assets.is_dir() else set()
    violations = [
        f"引用的资产文件不存在：{name}（应放在 {assets.name}/）"
        for name in sorted(refs - present)
    ]
    warnings = [
        f"资产未被引用：{assets.name}/{name}（研究阶段抓了图，正文没嵌）"
        for name in sorted(present - refs)
    ]
    return violations, warnings


def crosscheck_research(draft_text: str, research_text: str) -> tuple[list[str], list[str]]:
    """草稿信息来源必须能在研究文件核对到（URL 缺失/标题日期不符 = FAIL）；
    人物称呼未见于研究文件只警告（写手有时须自取化名，不能拦）。"""
    vs, ws = [], []
    body = re.sub(r"<!--.*?-->", "", draft_text, flags=re.S)
    for date_s, _src, title, url in DRAFT_SRC_RE.findall(body):
        if not url.startswith("http"):
            continue
        lines = [l for l in research_text.splitlines() if url in l]
        if not lines:
            vs.append(f"来源 URL 不在研究文件 信息来源：{url}")
            continue
        if not any(date_s in l and title in l for l in lines):
            vs.append(f"来源行与研究文件不一致（日期或标题）：{title} / {date_s}")
    names = set(NAME_RE.findall(body)) | set(ALIAS_RE.findall(body))
    for name in sorted(names):
        if name not in research_text:
            ws.append(f"称呼未在研究文件出现：{name}（自取化名时确认必要性并全篇一致）")
    return vs, ws


def lint_file(path: Path) -> list[str]:
    return lint_text(path.read_text(encoding="utf-8"), load_tag_registry(), date.today())


def main(argv: list[str]) -> int:
    research_path: str | None = None
    paths: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--research":
            research_path = argv[i + 1]
            i += 2
        else:
            paths.append(argv[i])
            i += 1
    if not paths:
        print("usage: python src/linter.py <draft.md>... [--research <research.md>]")
        return 2
    research_text = (
        Path(research_path).read_text(encoding="utf-8") if research_path else None
    )
    rc = 0
    for p in paths:
        path = Path(p)
        content = path.read_text(encoding="utf-8")
        vs = lint_text(content, load_tag_registry(), date.today())
        vs += lint_slug_title(path, str((read_frontmatter(content) or {}).get("title") or ""))
        ws = lint_warnings(content)
        asset_vs, asset_ws = lint_assets(path, content)
        vs += asset_vs
        ws += asset_ws
        if research_text is not None:
            cc_vs, cc_ws = crosscheck_research(content, research_text)
            vs += cc_vs
            ws += cc_ws
        if vs:
            rc = 1
            print(f"LINT FAIL {p}")
            for v in vs:
                print(f"  - {v}")
        else:
            print(f"LINT OK {p}")
        for w in ws:
            print(f"  ~ WARN: {w}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
