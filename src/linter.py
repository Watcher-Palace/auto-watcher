"""Mechanical draft linter — catches format violations before the Sonnet review.

Checks are deterministic only (no judgment calls): em dashes, 舆论 without
concrete metrics, source-line format, unregistered tags, invalid categories,
future dates, missing required sections.
"""
from __future__ import annotations
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.publisher import read_frontmatter, load_tag_registry, load_tag_group
from src.utils.research_doc import E_REF_LOOSE_RE, extracts, is_new_format

VALID_CATEGORIES = {"S", "A", "B", "C", "D", "M", "N"}
# 犯罪 tag 必须同时带一个具体罪名，或说明为什么没有罪名（用户裁定 2026-07-20）
CHARGE_GAP_TAGS = {"未立案", "罪名未公开"}
# 具体数据：计量词，或"数字+转发/评论/点赞/观看"这类计数写法
METRIC_RE = re.compile(
    r"(阅读量|讨论量|转发量|评论量|访问量|播放量|观看量|点赞量|投票|票数"
    r"|[\d.]+\s*[万亿]?\s*(?:条)?\s*(?:转发|评论|点赞|观看|播放|次浏览))"
)
# 与 DRAFT_SRC_RE 必须同样严（都要求补零）：若此处放行不补零而 DRAFT_SRC_RE 不认，
# 该行会格式检查通过、却对 crosscheck_research 隐形，等于绕过"来源须能在研究文件核对到"。
SOURCE_LINE_RE = re.compile(r"^(- )?\d{4}\.\d{2}\.\d{2}，.+?。\*.+?\*。\S+")
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")
ASSET_REF_RE = re.compile(r"\{%\s*asset_path\s+(.+?)\s*%\}")
# C3（审计裁定，2026-07-22）：填充语/蓝字进展标记为 FAIL；舆论反应措辞为 WARN
FILLER_FAIL_RE = re.compile(r"此事沉寂数月后|网友纷纷表示")
OPINION_WARN_RE = re.compile(r"引发广泛关注|引起广泛关注|引发关注|引发热议")

# 标题字数上限（含标点）。用户裁定 2026-07-31：由 35 放宽为 40，超出只报 WARN
TITLE_MAX_LEN = 40
TITLE_OPINION_RE = re.compile(r"引争议|引发争议|引质疑|引发质疑|引发关注|引发热议|惹众怒")
BLUE_RE = re.compile(r'<font color="blue">(.*?)</font>', re.S)
# 破折号是文风规则，管的是写手自己造的句子，不管别人文书的真实名称（用户裁定 2026-08-04）。
# 豁免两处逐字引用：灰字引用 <font color="grey">…</font>，以及来源行的 *标题*——官方公报与
# 判决书标题大量含「——」（如"第七次全国人口普查公报（第四号）——人口性别构成情况"），
# 此前只能删副标题才能过闸口，等于逼写手改写文书真名。
GREY_QUOTE_RE = re.compile(r'<font color="grey">.*?</font>', re.S)
SRC_TITLE_RE = re.compile(r"^((?:- )?\d{4}\.\d{2}\.\d{2}，.+?。)\*.+?\*", re.M)
NO_PROGRESS_RE = re.compile(r"暂无|尚未|无最新进展|未发布通报")
# C1（审计裁定，2026-07-22）：草稿信息来源行必须能在研究文件里核对到；人物称呼只警告
DRAFT_SRC_RE = re.compile(r"^(?:- )?(\d{4}\.\d{2}\.\d{2})，(.+?)。\*(.+?)\*。(\S+)", re.M)
NAME_RE = re.compile(r"[一-龥]{1,2}(?:某某|某|女士|先生)|小[一-龥]")
ALIAS_RE = re.compile(r"([一-龥]{2,3})（(?:报道使用)?化名）")
# 来源行标题里的受害人真名按全角星号打码（用户裁定，2026-08-04）。半角 * 是 DRAFT_SRC_RE 的
# 斜体定界符，写进标题会把标题截断，故只认全角 ＊。研究文件保留真名，比对时打码位走通配。
MASK_RE = re.compile(r"＊+")
# 标题被动句启发（2026-07-31 裁定的机械面）：典型受害人称谓开头 + 遭/被 → WARN。
# 只认受害人称谓起头，避免误报"男子杀害女儿被判死刑"这类加害人主语+被判的正确形态。
TITLE_PASSIVE_RE = re.compile(
    r"(?:女子|女生|女童|女孩|女性|少女|女大学生|女乘客|女顾客|女员工|女教师|母亲|妻子)"
    r"[^，。]{0,8}?(?:遭|被)"
)
# 称谓前允许一小段地名/机构限定语——原来锚在 ^，"吉林女子遭…" 这类带前缀的
# 标题整条漏报（260725-2 靠人工评审才发现）。但限定语里出现施动者称谓或加害
# 动词时，女性称谓是宾语不是主语（"医生猥亵女童被开除"），那是合规标题。
TITLE_PASSIVE_PREFIX_MAX = 6
TITLE_ACTOR_RE = re.compile(r"[男夫父生师警员]|[杀打伤猥奸骚拐拍虐砍捅泼骗]")


def title_is_victim_passive(title: str) -> bool:
    m = TITLE_PASSIVE_RE.search(title)
    if m is None or m.start() > TITLE_PASSIVE_PREFIX_MAX:
        return False
    return not TITLE_ACTOR_RE.search(title[: m.start()])
GREY_SPAN_RE = re.compile(r'<font color="grey">(.*?)</font>', re.S)
RED_SPAN_RE = re.compile(r'<font color="red">(.*?)</font>', re.S)
# 红字与来源逐字重合多少字算「近乎逐字」。16 是实测取的：276 份历史草稿里 12 命中 20 份、
# 16 命中 14 份、18 命中 9 份——16 处仍是人工复核认下的真违规，再低开始混进无害的短套语。
RED_ECHO_MIN = 16
CN_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _dash_scan_text(content: str) -> str:
    """破折号检查的扫描面：剥掉 HTML 注释与逐字引用（见 GREY_QUOTE_RE 注释）。"""
    text = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    text = GREY_QUOTE_RE.sub("", text)
    return SRC_TITLE_RE.sub(lambda m: m.group(1), text)


def _sections(body: str) -> dict[str, str]:
    """Map '## X' heading → section text (up to next ## heading)."""
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def tracked_uids() -> set[str]:
    """本站追踪账号的 UID（`src/.env` 的 TRACKED_UIDS）。

    来源行里出现这些 uid 的微博 URL＝把本站的事件发现源公开挂在文章里（用户裁定
    2026-08-04）。写手无 .env 访问权、也无网络，判不了这件事，所以拦在机械闸口。
    .env 缺失时返回空集合（CI 无 .env，此项检查静默跳过，不误伤）。
    """
    raw = os.environ.get("TRACKED_UIDS")
    if raw is None:
        env = Path(__file__).parent / ".env"
        if not env.is_file():
            return set()
        for ln in env.read_text(encoding="utf-8").splitlines():
            if ln.startswith("TRACKED_UIDS="):
                raw = ln.split("=", 1)[1]
                break
    return {u.strip() for u in (raw or "").split(",") if u.strip()}


def lint_text(content: str, registry: set[str] | None, today: date) -> list[str]:
    violations: list[str] = []
    fm = read_frontmatter(content)
    body = content.split("---", 2)[-1] if content.startswith("---") else content

    prose = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    if "—" in _dash_scan_text(content):
        violations.append("破折号 — 出现（风格规则：重组句子，不用破折号）")
    # 研究层的 [E] 出处回指不进读者可见正文（template 全篇没有它的位置，已发布语料命中
    # 为 0）。新格式研究文件的叙述层每句都挂 [E]，改写进草稿时极易连标记一起带过来——
    # 260804-3 v1 就是这样带进 11 行 57 处，linter 不查、评审当成正常写法、写手自己也
    # 没觉得不对，三道防线同时漏。判据取注释剥离后的全文，含全角方括号变体。
    if (m := E_REF_LOOSE_RE.search(prose)):
        violations.append(
            f"正文出现研究层出处标记 {m.group(0)}——[E] 只用于研究文件内部回指，"
            "成文必须剥离（内容仍须可追溯到某条摘录，那是要求不是排版语法）"
        )

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

    for uid in sorted(tracked_uids()):
        if re.search(rf"weibo\.com/{re.escape(uid)}/", body):
            violations.append(
                f"来源 URL 指向本站追踪账号 uid {uid}（用户裁定 2026-08-04：安全事项）"
                "——发布即公开本站的事件发现源。改用原帖/该媒体自己的原始出处；"
                "取不到就不收该来源，不许借追踪账号的 URL 充数"
            )

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
    # 用户裁定 2026-07-31：标题上限 40 字（含标点），超出报 WARN 不阻断
    if len(title) > TITLE_MAX_LEN:
        warnings.append(
            f"标题 {len(title)} 字，超过 {TITLE_MAX_LEN} 字上限——精简说清事实，"
            "把法院说理、认定依据、过程修饰留给正文"
        )
    if OPINION_WARN_RE.search(prose):
        warnings.append("正文含舆论反应措辞（引发关注类）——舆论事件难免时可保留，否则删")
    if title_is_victim_passive(title):
        warnings.append("标题疑似受害人被动句——改以加害人为主语（加害人未知/无法特指时保留施动主体即可）")
    # frontmatter date 必须是蓝字进展的发生日（template 规定；曾有偏一天靠用户读出）
    d = fm.get("date")
    fm_date = None
    if hasattr(d, "year"):
        fm_date = (d.year, d.month, d.day)
    elif isinstance(d, str) and (md := re.match(r"(\d{4})-(\d{2})-(\d{2})", d)):
        fm_date = tuple(int(x) for x in md.groups())
    blue_m = BLUE_RE.search(content)
    if fm_date and blue_m:
        line_start = content.rfind("\n", 0, blue_m.start()) + 1
        candidate = content[line_start:blue_m.end()]
        dates = {tuple(int(x) for x in g) for g in CN_DATE_RE.findall(candidate)}
        if dates and fm_date not in dates:
            warnings.append(
                "frontmatter date 未出现在蓝字进展所在行——date 必须是蓝字进展的发生日"
                "（不是报道日/撰写日；排期预告不算发生日）"
            )
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
        if MASK_RE.search(title):
            # 标题里的受害人真名已按化名规则打码；研究文件保留真名，故打码位按通配比对。
            pat = re.compile(".{1,6}".join(re.escape(s) for s in MASK_RE.split(title)))
            hit = any(date_s in l and pat.search(l) for l in lines)
        else:
            hit = any(date_s in l and title in l for l in lines)
        if not hit:
            vs.append(f"来源行与研究文件不一致（日期或标题）：{title} / {date_s}")
    names = set(NAME_RE.findall(body)) | set(ALIAS_RE.findall(body))
    for name in sorted(names):
        if name not in research_text and (len(name) < 2 or name[1:] not in research_text):
            ws.append(f"称呼未在研究文件出现：{name}（自取化名时确认必要性并全篇一致）")
    # 灰字／红字的逐字基准：新格式下两者不再共用一个基准。灰字只认 ## 摘录（逐条核过
    # 快照的正文，把「标题当当事人原话引」这类坑天然排除在通道之外）；红字防的是「近乎
    # 逐字复读官方结论」，标题正是最常被复读的对象，故摘录层之外还要并回 ## 信息来源。
    # 旧格式两者都仍看 ## 信息来源，逐字不变。
    _secs = _sections(research_text)
    new_fmt = is_new_format(research_text)
    base_section = "摘录" if new_fmt else "信息来源"
    if new_fmt:
        # 基准取 extracts() 解析出的 .body，不拿整节原文——原文混着每条摘录的头行
        # （`[E1] 信源1 · 正文原话 · 2026-08-07`），头行本身的元数据会被误判成逐字命中。
        # \x00 作分隔符 join：既不在 _norm_quote 的剥除集里（能活下来隔开相邻两条），
        # 又避免「上一条尾部＋下一条头部」拼出一句从未真实存在过的假引文。
        #
        # F-2（fix 轮 1）：灰字与红字各按自己的问题过滤，不再共用同一个 grey_base：
        # 灰字只收 form == 正文原话——只有逐字转录的摘录能作写手灰字依据（blog-writer/
        # blog-reviewer 已明文的规则，这里接机械面）；标题/第三人称转述/图上转录都不能，
        # 排除它们正是堵住「把标题当当事人原话引」这类坑。红字维持现状：extracts() 的
        # 全部形态 + 信息来源 都并进来——红字防的是「近乎逐字复读官方结论」，标题正是
        # 最常被复读的对象，若也按 正文原话 过滤会把它漏掉（与 Task 7 fix 轮 1「不许把
        # 标题重新塞回灰字基准」同向，不能反过来把标题也从红字基准里过滤掉）。
        all_extracts_base = "\x00".join(_norm_quote(e.body) for e in extracts(research_text))
        grey_base = "\x00".join(
            _norm_quote(e.body) for e in extracts(research_text) if e.form == "正文原话"
        )
        red_base = all_extracts_base + "\x00" + _norm_quote(_secs.get("信息来源", "") or "")
    else:
        grey_base = red_base = _norm_quote(_secs.get("信息来源", "") or "")
    # 灰字引文须逐字命中研究文件 base_section 节（blog-writer《带色引文必须逐字回查》的
    # 机械面）。化名替换与外文译文合法地对不上原文，故只 WARN 不拦——WARN 的意义是
    # 逼一次显式核对，不是判定编造。
    for span in GREY_SPAN_RE.findall(body):
        norm = _norm_quote(span)
        if len(norm) < 6:
            continue
        if norm not in grey_base:
            ws.append(
                f"灰字引文未在研究文件 {base_section} 节逐字命中：{span.strip()[:24]}…"
                "（化名替换/外文译文属预期；否则改用确有的摘录，或按缺口上报）"
            )
    # 红字转述官方结论时不得以「近乎逐字、又有改写」的形态呈现（blog-writer 规则的机械面）：
    # 与来源逐字重合 ≥ RED_ECHO_MIN 字即报。改法二选一——够格逐字就改灰字整段引用，
    # 否则去色写成明确转述。只 WARN 不拦：重合也可能落在无法改写的法条名、机构全称上。
    for span in RED_SPAN_RE.findall(body):
        frag = _echo_span(_norm_quote(span), red_base, RED_ECHO_MIN)
        # 案号、金额、外文原句这类本就只能逐字的标识串不构成改写风险，按非汉字占比排除
        if not frag or sum("一" <= c <= "鿿" for c in frag) / len(frag) < 0.6:
            continue
        ws.append(
            f"红字与来源逐字重合 {len(frag)} 字：「{frag[:40]}」"
            f"（红字起始：{span.strip()[:20]}…）"
            "——改灰字逐字引用，或去色写成明确转述，不要两者之间"
        )
    return vs, ws


def _echo_span(a: str, b: str, k: int) -> str:
    """a 中长度 ≥ k、且整段出现在 b 里的一个极大片段（没有则空串）。

    等价于「最长公共子串 ≥ k」：LCS ≥ k 当且仅当 a 的某个 k 字窗口是 b 的子串。
    逐窗 `in` 走 C 层字符串搜索，比 O(len(a)·len(b)) 的 DP 快两个数量级——研究文件
    本身可达上万字，DP 会让每次 lint 多跑几秒。
    """
    for i in range(len(a) - k + 1):
        if a[i:i + k] not in b:
            continue
        j = i + k
        while j < len(a) and a[i:j + 1] in b:
            j += 1
        while i > 0 and a[i - 1:j] in b:
            i -= 1
        return a[i:j]
    return ""


def _norm_quote(s: str) -> str:
    """引文比对前的归一化：剥标签、空白与引号壳，保留其余标点（逐字含标点）。

    引号壳含半角 `"` `'` 与弯引号 `‘’`——漏掉它们时，研究文件把说话人写进引号内
    （`"邓煜：能与我…"`）的摘录会让草稿里同一句灰字判不命中，报假 WARN。
    同一根因 2026-08-06 一天内命中两次（260721-3、260726-1）。剥除集须与
    `srcfetch.normalize` 保持同形（同一函数比同一件事）：`*` 同理剥除——研究文件
    的摘录/事实句常把词加粗，草稿灰字没有这层 markdown，逐字比对否则必然落空
    （fix 轮 1 F-7a／Minor 8）。
    """
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[\s「」『』“”‘’\"'*]", "", s)


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
