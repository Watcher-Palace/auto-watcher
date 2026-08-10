"""研究文件机械闸口 —— initial/update 研究完成前都必须通过（blog-researcher 的 lint gate）。

FAIL＝阻断；"WARN："前缀的条目只提示不阻断（LINT OK 下方照常打印）。

新旧两套格式分派（`is_new_format` 按有无 `## 摘录` 节判据）：
- 旧格式（在途事件，无 `## 摘录`）走 `_lint_legacy`：多数检查只拦"形状"——裸平台品牌作
  来源名、带引号摘录缺形态标注、自称正文原话的引文只在来源标题里找得到、标题疑似抄自
  URL slug、来源 URL 落在本站追踪账号；唯一真核内容的是来源行内嵌引文的逐字核：标着
  `正文原话` 的引文拿 `srcfetch` 的原文快照比对（无快照＝WARN，不阻断）。
- 新格式（有 `## 摘录`）走 `_lint_new`：摘录层每条非「图上转录」的条目都要逐字核对快照
  （无快照或不在快照里＝FAIL，不再是 WARN——上一轮全量扫出的 82 条无快照 WARN 全被忽略）。

署名与标题的**真伪**仍没有网络判不了，靠研究阶段打开页面核。
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

try:
    from src.linter import tracked_uids
    from src.srcfetch import load as load_snapshot, normalize as norm_quote
    from src.utils.research_doc import (
        E_REF_RE, FORMS, event_of, extracts, is_new_format,
        malformed_extract_heads, sections as _doc_sections, sources as doc_sources,
    )
except ImportError:  # 以脚本方式直跑时无包上下文
    from linter import tracked_uids
    from srcfetch import load as load_snapshot, normalize as norm_quote
    from utils.research_doc import (
        E_REF_RE, FORMS, event_of, extracts, is_new_format,
        malformed_extract_heads, sections as _doc_sections, sources as doc_sources,
    )

REQUIRED = ("事实", "当事方", "信息来源", "资产")
# 新格式在 REQUIRED 之外唯一合法的额外节。sections() 按 `## ` 切分整份文档——
# `## 摘录` 节正文里一旦混入任何未预期的二级标题，该行之后的一切（含格式完全合规的
# 摘录）会从 extracts()/malformed_extract_heads() 同时消失、无报错无痕迹（本重构最
# 危险的静默口子）。这个缺陷不能在解析层修（放宽解析＝把异常悄悄吞掉，`## ` 切分本身
# 又是既定规格），只能在这里堵成因：出现已知集合之外的标题就报违规，不管它有没有
# 恰好把什么东西藏没了。
KNOWN_SECTIONS_NEW = set(REQUIRED) | {"摘录"}
# 日期必须补零（2026.01.01）。此处若放行 \d{1,2}，研究阶段随手选的格式会经
# linter.py --research 的逐字比对变成对写手的硬约束：写手照 template 的补零
# 惯例写反而 LINT FAIL，只能倒回去迁就研究文件，格式污染随之进入已发布文章。
# URL 段排除全角破折号「—」并要求收尾要么到此为止、要么以 " — " 起头——
# 缺空格时（如 "URL—快照失败：..."）\S+ 会把破折号后的内容整段吞进 URL，
# 「快照失败」标记被吞没后 snapshot_failed 会静默判成 False（Task 2 评审 Important）。
# 首选修法不动 SRC_PARSE_RE 的 URL 捕获组（那个正则在 research_doc.py 里也要用
# 于实际抽取，改了两处必须同改），而是在这个纯格式校验正则里收紧，让缺空格的行
# 直接报格式违规——把静默误判变成响的失败。
SRC_RE = re.compile(r"^- \d{4}\.\d{2}\.\d{2}，.+?。\*.+?\*。[^\s—]+(?: — .+)?$")
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
# 拦的是"完全没标"，不是用词偏好。旧格式专用——新格式的形态标注在 [E] 头里，见 FORMS。
FORM_TOKENS = ("正文原话", "第三人称转述", "标题", "转述", "转录")
# 叙述节里的引文若只在某条来源的 *标题* 里出现、任何摘录里都没有，那是把标题措辞
# 当成了当事人原话（标题惯把第三人称改写成第一人称）。写手无网络、灰字全押研究文件的
# 标注，只能照单全收，最后由评审判成伪引用。agent「形态标注」条明文禁止，四次复现
# （260717-1/260721-3/260724-2/260731-1）后落成机械闸口。旧格式专用。
NARRATIVE_SECTIONS = ("事实", "当事方")
QUOTE_RES = (re.compile(r"「([^」]+)」"), re.compile(r'"([^"]+)"'), re.compile(r"“([^”]+)”"))
QUOTE_MIN = 8          # 短词（案由、状态）撞上标题不算伪引用
FORM_LOOKAHEAD = 30    # 引号后多远内出现「正文原话」＝作了这个声明
# 标着 `正文原话` 的摘录拿 srcfetch 快照逐字核（快照走裸 HTTP／无头浏览器，模型不介入；
# WebFetch 返回的是小模型对页面的答复，拿它比对＝两次改写互比，核不出伪引用）。
# 抓不到快照的信源（JS 壳、反爬、付费墙）旧格式只给 WARN——机械核不了是事实，不能假装
# 核过了；新格式（_lint_extracts）升级为 FAIL，见该函数注释。
VERIFY_MIN = 6
# update 模式的更正说明要原样引回被推翻的错句（"原稿…误标正文原话"），那是留痕不是主张
CORRECTION_RE = re.compile(r"更正（|误标|原稿|伪引用|查证失败")
CORRECTION_LOOKBEHIND = 60


def _slug_tokens(url: str) -> list[str]:
    slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    tokens = [t.lower() for t in re.split(r"[-_]", slug) if t]
    # 末尾纯数字长 token 多为站点文章 id（…-met-officers-498512），不算标题词
    if tokens and tokens[-1].isdigit() and len(tokens[-1]) >= 5:
        tokens.pop()
    return tokens


def _claimed_verbatim(tail: str) -> list[str]:
    """摘录里明确声明为 `正文原话` 的引文（其余形态照收，不在此核）。旧格式专用。"""
    out = []
    for qre in QUOTE_RES:
        for qm in qre.finditer(tail):
            q = qm.group(1).strip()
            if len(q) >= VERIFY_MIN and "正文原话" in tail[qm.end():qm.end() + FORM_LOOKAHEAD]:
                out.append(q)
    return out


def _verify_quotes(tail: str, url: str, event: str) -> list[str]:
    """旧格式专用：来源行 tail 里自称 `正文原话` 的引文拿快照逐字核。"""
    quotes = _claimed_verbatim(tail)
    if not quotes:
        return []
    snap = load_snapshot(url, event)
    if snap is None:
        # 抓不到快照 ≠ 引文有问题：形态标注照页面实况，不许因工具抓不到而改标
        return [f"WARN：无原文快照，`正文原话` 无法机械核对——跑 src/srcfetch.py "
                f"落快照；抓不到不改形态标注：{url}"]
    body = norm_quote(snap)
    return [f"摘录自称 `正文原话`，但该句不在原文快照里（拼接/改写/张冠李戴）：{q[:30]}"
            for q in quotes if norm_quote(q) not in body]


def _lint_source_lines(src_text: str) -> list[str]:
    """来源行格式 ＋ 裸平台品牌 ＋ slug ＋ 追踪账号——新旧格式共用的书目行检查。

    「摘录带引号但缺形态标注」不在此列——新格式的来源行不再带内嵌摘录，那条检查
    只在旧格式（`_lint_legacy`）里启用。
    """
    vs: list[str] = []
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
        title_tokens = re.findall(r"[a-z0-9]+", title.lower().replace("'", ""))
        if len(title_tokens) >= 3 and _slug_tokens(url) == title_tokens:
            vs.append(f"WARN：标题与 URL slug 完全一致——核对页面真标题（slug 未必是真标题）：{ln[:40]}")
    for uid in sorted(tracked_uids()):
        if re.search(rf"weibo\.com/{re.escape(uid)}/", src_text):
            vs.append(
                f"来源 URL 指向本站追踪账号 uid {uid}（安全事项，用户裁定 2026-08-04）"
                "——换该内容自己的原始出处，取不到就不收"
            )
    return vs


def _lint_blue(text: str) -> list[str]:
    """蓝字三检查——新旧格式共用。"""
    vs: list[str] = []
    blues = BLUE_RE.findall(text)
    if len(blues) != 1:
        vs.append(f"蓝字标记应恰好 1 处（现 {len(blues)} 处）")
    else:
        if not DATE_IN_RE.search(blues[0]):
            vs.append("蓝字未标明进展日期——写手无法定 date")
        if NO_PROGRESS_RE.search(blues[0]):
            vs.append("蓝字是'暂无进展'类句子——必须是真实事实进展")
    return vs


def _lint_assets(path: Path, secs: dict[str, str]) -> list[str]:
    """资产双向一致——新旧格式共用。"""
    vs: list[str] = []
    m = re.match(r"(\d{6})-(\d+)-", path.name)
    if m and "资产" in secs:
        assets_dir = path.parent.parent / "draft" / f"{m.group(1)}-{m.group(2)}-assets"
        listed = {a.group(1) for l in secs["资产"].splitlines()
                  if (a := ASSET_LINE_RE.match(l.strip()))}
        present = {p.name for p in assets_dir.iterdir()} if assets_dir.is_dir() else set()
        vs += [f"资产登记的文件不存在：{n}" for n in sorted(listed - present)]
        vs += [f"资产文件未登记：{n}" for n in sorted(present - listed)]
    return vs


def _lint_extracts(path: Path, text: str) -> tuple[list[str], dict[int, bool]]:
    """核摘录层。返回（违规列表，{eid: 该摘录所依信源是否 快照失败}）。

    覆盖 `## 摘录` 节里**全部**条目，不做任何抽样或早停——Task 3 评审用的临时核对脚本
    只认「引号后 30 字内出现 正文原话」一种写法，14 条摘录只覆盖到 3 条，漏掉了「一个
    标签管多句引号」的场景；欠采样的闸口比没有闸口更坏，因为它会让人以为查过了。
    """
    event = event_of(path)
    srcs = {s.num: s for s in doc_sources(text)}
    es = extracts(text)
    secs = _doc_sections(text)
    assets_dir = path.parent.parent / "draft" / f"{event}-assets"
    present = {p.name for p in assets_dir.iterdir()} if assets_dir.is_dir() else set()
    vs: list[str] = []
    failed: dict[int, bool] = {}
    seen: set[int] = set()
    for e in es:
        failed[e.eid] = False
        if e.eid in seen:
            vs.append(f"[E{e.eid}] 编号重复——编号只增不改，重编会让历史引用全部错位")
        seen.add(e.eid)
        if e.form not in FORMS:
            vs.append(f"[E{e.eid}] 形态不合法「{e.form}」（{'/'.join(sorted(FORMS))}）")
        if not e.body:
            vs.append(f"[E{e.eid}] 摘录正文为空")
            continue
        if e.form == "图上转录":
            fn = e.ref.removeprefix("资产").strip()
            if fn not in present:
                vs.append(f"[E{e.eid}] 图上转录指向的资产文件不存在：{fn}")
            continue
        m = re.fullmatch(r"信源(\d+)", e.ref)
        if not m:
            vs.append(f"[E{e.eid}] 来源标注须为「信源N」或「资产 <文件名>」，实为「{e.ref}」")
            continue
        src = srcs.get(int(m.group(1)))
        if src is None:
            vs.append(f"[E{e.eid}] 引用了不存在的信源{m.group(1)}")
            continue
        if src.snapshot_failed:
            failed[e.eid] = True
            if e.form == "正文原话":
                vs.append(
                    f"[E{e.eid}] 信源{src.num} 标了 快照失败，不得作 正文原话 依据：{src.url}"
                )
            continue
        snap = load_snapshot(src.url, event)
        if snap is None:
            vs.append(
                f"[E{e.eid}] 信源{src.num} 无快照——跑 src/srcfetch.py --event {event} "
                f"--from-research：{src.url}"
            )
            continue
        if norm_quote(e.body) not in norm_quote(snap):
            vs.append(
                f"[E{e.eid}] 摘录不在原文快照里（拼接/改写/张冠李戴）：{e.body[:30]}"
            )
    # ] 后缺空格、· 两侧缺空格、行首多 - 、eid 非纯数字——这四类手误原实现会静默丢弃
    # 整条摘录、并把它的正文并进上一条的 body（那不是漏判是误挂：属于 E2 的引文会拿
    # E1 的身份通过核对）。每条畸形标签必须单独出一条违规，不许只是个没人调的函数。
    for bad in malformed_extract_heads(text):
        vs.append(
            f"摘录标签解析失败（缺空格/多余「- 」前缀/编号非纯数字之类的手误，其正文不会"
            f"被并入相邻摘录，须单独修正）：{bad[:40]}"
        )
    # 书目行有 URL 却既无快照也无 快照失败 标记——上一轮 82 条无快照 WARN 全被忽略，
    # 证明 WARN 在这里不起作用，改 FAIL。
    for s in srcs.values():
        if not s.snapshot_failed and load_snapshot(s.url, event) is None:
            vs.append(
                f"信源{s.num} 无快照且未标 快照失败——跑 srcfetch，抓不到就在行尾写"
                f"「快照失败：<原因>」：{s.url}"
            )
    used = {int(x) for sec in ("事实", "当事方") for x in E_REF_RE.findall(secs.get(sec) or "")}
    for e in es:
        if e.eid not in used:
            vs.append(f"WARN：[E{e.eid}] 摘录无人引用（孤儿）——用上或删掉")
    return vs, failed


def lint_research(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if is_new_format(text):
        return _lint_new(path, text)
    return _lint_legacy(path, text)


def _lint_new(path: Path, text: str) -> list[str]:
    vs: list[str] = []
    secs = _doc_sections(text)
    for r in REQUIRED + ("摘录",):
        if r not in secs:
            vs.append(f"缺少必需章节 ## {r}")
    for name in secs:
        if name not in KNOWN_SECTIONS_NEW:
            vs.append(
                f"出现未知章节 ## {name}——## 摘录 节内误加二级标题会让其后内容连带"
                "从摘录里蒸发、无报错无痕迹；若是笔误请改回已知章节名，不要在这几节内用 ## 标题"
            )
    vs += _lint_source_lines(secs.get("信息来源") or "")
    ex_vs, _failed = _lint_extracts(path, text)
    vs += ex_vs
    vs += _lint_blue(text)
    vs += _lint_assets(path, secs)
    return vs


def _lint_legacy(path: Path, text: str) -> list[str]:
    vs: list[str] = []
    secs = _doc_sections(text)
    for r in REQUIRED:
        if r not in secs:
            vs.append(f"缺少必需章节 ## {r}")
    src_text = secs.get("信息来源") or ""
    event = event_of(path)
    src_titles: list[str] = []
    src_tails: list[str] = []
    for ln in src_text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        if not SRC_RE.match(ln) and UNVERIFIED not in ln:
            continue  # 格式违规已由 _lint_source_lines 报过，这里只为取 title/tail 供后续检查
        m2 = SRC_PARSE_RE.match(ln)
        if not m2:
            continue
        name, title, url, tail = m2.group(2), m2.group(3), m2.group(4), m2.group(5)
        src_titles.append(title)
        src_tails.append(tail)
        has_quote = "「" in tail or "“" in tail or tail.count('"') >= 2
        if has_quote and not any(t in tail for t in FORM_TOKENS):
            vs.append(f"摘录带引号但缺形态标注（正文原话/标题/第三人称转述）：{ln[:40]}")
        vs += _verify_quotes(tail, url, event)
    vs += _lint_source_lines(src_text)
    for sec in NARRATIVE_SECTIONS:
        body = secs.get(sec) or ""
        for qre in QUOTE_RES:
            for qm in qre.finditer(body):
                q = qm.group(1).strip()
                # 只拦"自称正文原话"的：引号里放标题/话题/案由本身是常态写法，
                # 不带这个声明就不是伪引用（全量扫 140 份研究文件校准过）
                if len(q) < QUOTE_MIN or "正文原话" not in body[qm.end():qm.end() + FORM_LOOKAHEAD]:
                    continue
                if CORRECTION_RE.search(body[max(0, qm.start() - CORRECTION_LOOKBEHIND):qm.start()]):
                    continue
                if any(q in t for t in src_titles) and not any(q in t for t in src_tails):
                    vs.append(
                        f"## {sec} 的引文只见于来源标题、未见于任何摘录——标题措辞不是正文原话"
                        f"（标题惯把第三人称改写成第一人称）：{q[:30]}"
                    )
    vs += _lint_blue(text)
    vs += _lint_assets(path, secs)
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
