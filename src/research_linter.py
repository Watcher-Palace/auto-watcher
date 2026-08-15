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
        E_REF_LOOSE_RE, E_REF_RE, FORMS, event_of, extracts, is_new_format,
        malformed_extract_heads, sections as _doc_sections, sources as doc_sources,
    )
except ImportError:  # 以脚本方式直跑时无包上下文
    from linter import tracked_uids
    from srcfetch import load as load_snapshot, normalize as norm_quote
    from utils.research_doc import (
        E_REF_LOOSE_RE, E_REF_RE, FORMS, event_of, extracts, is_new_format,
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
# 与 research_doc.SRC_PARSE_RE 同形——两处必须同改，不许留一边旧一边新。旧格式的
# `_lint_legacy` 在解析前已经过 SRC_RE 这道格式闸，但 research_doc.sources() 是
# 独立的第二条解析路径（`_lint_extracts`/`srcfetch --from-research` 都走它，后者
# 研究阶段就会跑、文件还没被 lint 过），URL 组同样必须排除全角破折号，否则那条路径
# 里 snapshot_failed 依旧会被静默吞成 False。日期字段同时放宽到接受「发布日期查证
# 失败」（可带 （…） 括注）——见 research_doc.py 同一行的注释，理由一致。
SRC_PARSE_RE = re.compile(
    r"^- (\d{4}\.\d{2}\.\d{2}|发布日期查证失败(?:（[^）]*）)?)，(.+?)。\*(.+?)\*。([^\s—]+)(.*)$"
)
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
# 事实层引号跨度认哪些形态作逐字凭据（理由见 _lint_facts 的 F-2 注释）：摘录四种形态都
# 逐字取自快照，只排除 标题。将来若给 FORMS 添形态，默认按"可作凭据"收——新形态若同
# 标题一样是被媒体改写过的文本，须在这里显式排除。
FACT_VERBATIM_FORMS = FORMS - {"标题"}
# 标着 `正文原话` 的摘录拿 srcfetch 快照逐字核（快照走裸 HTTP／无头浏览器，模型不介入；
# WebFetch 返回的是小模型对页面的答复，拿它比对＝两次改写互比，核不出伪引用）。
# 抓不到快照的信源（JS 壳、反爬、付费墙）旧格式只给 WARN——机械核不了是事实，不能假装
# 核过了；新格式（_lint_extracts）升级为 FAIL，见该函数注释。
VERIFY_MIN = 6
# update 模式的更正说明要原样引回被推翻的错句（"原稿…误标正文原话"），那是留痕不是主张
CORRECTION_RE = re.compile(r"更正（|误标|原稿|伪引用|查证失败")
CORRECTION_LOOKBEHIND = 60
# 260731-1 受控演练：文档规定的更正格式是
# `**更正（评审vN-问题K）**：正确表述（原错误信息：原句）`——被推翻的旧错句结构上就排在
# 正确表述之后，距标记天然超过 60（实测 63／81／105，三条留痕全落窗外）。旧错句按定义
# 在快照里查不到（查得到就不叫错），窗口盖不住＝逼 agent 删掉评审留痕。
# 但**不能靠放宽字符数解决**：实测把窗口推到 150 会顺带豁免掉挨着更正标记的标签化引号
# （"本人自述，见信源1" 这类本该拦的），而句号判据同样分不开——留痕引文与邻近标签的
# 区别是语义的，不是位置的。改判"引文前紧邻留痕提示词"：演练那 6 条正反例 6/6 分开。
# 窗口留 25 字符——提示词与被引旧句之间通常只隔"：""为""写成"等一两个连接词。
TRAIL_CUE_RE = re.compile(r"原错误信息|原稿|原句|原摘录|原表述|误标|误概括|该合并句|伪引用")
TRAIL_CUE_LOOKBEHIND = 25
# 事实层每句必须挂出处。切句后去掉 [E] 与加粗标记，汉字不足这个数的不算句子——
# 小标题、分组行、日期前缀会被误报成"无出处"。
SENT_SPLIT_RE = re.compile(r"(?<=[。！？])")
SENT_MIN_CJK = 8
SENT_END = "。！？"
# 引号成对表：「」“” 计深度，直引号 " 对称、只能开关
QUOTE_OPEN, QUOTE_CLOSE = "「“", "」”"


def split_sentences(text: str) -> list[str]:
    """按 。！？ 切句，但**不在引号内部切**。

    260731-1 受控演练：逐字引语跨句是常态（当事人连说两句、文书连写两段），此前
    切句不认引号嵌套，跨句引语被拦腰截断、前半截判"无 [E] 出处"。agent 的两条出路
    都是错的——把 [E] 焊进引语内部＝污染原文，拆成两段各挂一个 [E]＝伪造出两句
    从未分开说过的话。句级归因本身不变，只是引号内不算句界。
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    straight = False
    for ch in text:
        buf.append(ch)
        if ch in QUOTE_OPEN:
            depth += 1
        elif ch in QUOTE_CLOSE:
            depth = max(0, depth - 1)
        elif ch == '"':
            straight = not straight
        elif ch in SENT_END and depth == 0 and not straight:
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out
CJK_RE = re.compile(r"[一-鿿]")
# 两种句子豁免 [E]：查证失败（定义上就没有出处）、检索记录（对自身检索行为的陈述，
# 任何信源都无法作证）。此外没有第三种。判据锚在"加粗且紧跟在 ** 之后"——140 份存量
# 实测过 34 个真实片段里只精确匹配旧版硬编码格式的 14 个，其余 20 个都是同一类
# 加粗标记但括注/尾缀写法不同（**查证失败**、**查证失败，写手不得使用该细节**、
# **查证失败（评审v1-问题2），详见事实第10条** 等），放宽到词族即可全收（fix 轮 1 F-2）。
# 不放宽到"加粗片段中间出现该词"：语料里"**判定为查证失败**""**该说法查证失败，
# 不应写入事实或草稿**"这类是叙述性结论，不是标记；本闸口豁免按整行摘除（见
# `_lint_facts` F-1 部分），若连这类词也认，整段长叙述行会被从中间的一个词整行豁免掉。
EXEMPT_RE = re.compile(r"\*\*(?:查证失败|检索记录)[^*]*\*\*")
# F-3 专用：引号跨度豁免窗口（_lint_facts，新格式）改成只认加粗的正式标记——与
# EXEMPT_RE 同一族（查证失败/检索记录），外加"更正（…）"（140 份存量里"**更正"
# 开头的加粗标记 100% 紧跟括注，未见裸"**更正**"用法）。不复用 CORRECTION_RE：
# 那是词面裸匹配（"查证失败"三个字出现即生效，不要求加粗），"逐字通道只有摘录层
# 一条"这个承诺一旦接上词面豁免就形同虚设——旧格式的 CORRECTION_RE/`_lint_legacy`
# 不动，两条路径本就分岔。窗口宽度沿用 CORRECTION_LOOKBEHIND，不新引入第三个阈值。
FORMAL_MARK_RE = re.compile(r"\*\*(?:查证失败|检索记录)[^*]*\*\*|\*\*更正（[^*]*\*\*")
# fix 轮 2 F-4：`### 姓名（角色）` 这类 markdown 小标题不是事实主张，不该被当句子核
# 出处——语料里 140 份文件有 25 份、共 155 处用 `### ` 给 `## 事实`/`## 当事方` 里的
# 人物分节（"### 李捷（女方，当事人）"这类），标题行本身通常不带句末标点，会作为
# 独立残留片段被判"该句无 [E] 出处"。只认 `#` 语法——`**加粗小标题**：` 是另一种写法，
# 后面常跟着需要出处的事实主张，不在此列（同 F-2 第二条边界，不能顺手放过）。
HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
# fix 轮 1 F-3：[E] 标记若跟在句末标点**之后**（脚注式 `甲。[E1] 乙。[E2]`），
# SENT_SPLIT_RE 按标点切句时标记会随下一句被切走——句 1 的出处丢失、错记到句 2 头上，
# 依此类推整份错位一位。切句前把标记搬到它前面那个标点之前，脚注式与行内式
# （`甲[E1]。乙[E2]。`）就归一到同一语义。收全半角方括号（沿用 E_REF_LOOSE_RE
# 的理由：中文输入法容易敲出 ［］）——E_REF_RE 本身不放宽，全角标记搬完位置后
# 仍不会被当作合法引用，只是不再连累下一句。
MARK_AFTER_PUNCT_RE = re.compile(r"([。！？])(\s*(?:[\[［]E\d+[\]］]\s*)+)")
# fix 轮 1 F-7b：省略号节略的逐字引文——`## 事实`／`## 当事方` 转述时用「……」跳过
# 无关内容是正常写法（转发……照片图文并搭配不雅视频），整串比对必然落空，不是编造。
# 按省略号切段、每段单独达到 QUOTE_MIN 门槛且命中即算命中。
ELLIPSIS_RE = re.compile(r"…+|\.{3,}")


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
        # 抓不到快照 ≠ 引文有问题：形态标注照页面实况，不许因工具抓不到而改标。
        # 命令必须能照着直接跑——绝对路径解释器 + --event（漏了 --event 实跑会
        # 直接打 usage 退出 2，agent 会以为是自己命令写错了）
        return [f"WARN：无原文快照，`正文原话` 无法机械核对——跑 "
                f"/home/jc/Projects/auto-watcher/src/venv/bin/python "
                f"/home/jc/Projects/auto-watcher/src/srcfetch.py --event {event} {url} "
                f"落快照；抓不到不改形态标注"]
    body = norm_quote(snap)
    return [f"摘录自称 `正文原话`，但该句不在原文快照里（拼接/改写/张冠李戴）：{q[:30]}"
            for q in quotes if norm_quote(q) not in body]


def _lint_source_lines(src_text: str, new_format: bool = False) -> list[str]:
    """来源行格式 ＋ 裸平台品牌 ＋ slug ＋ 追踪账号——新旧格式共用的书目行检查。

    「摘录带引号但缺形态标注」不在此列——新格式的来源行不再带内嵌摘录，那条检查
    只在旧格式（`_lint_legacy`）里启用。
    """
    # 新格式行尾不许放长引文（见 _lint_new_source_quotes），提示语跟着分岔——旧格式
    # 提示照抄一段摘录到行尾是对的，新格式下那样做会立刻撞上另一条闸口，是把 agent
    # 指向一件它做不到的事
    tail_hint = "— 快照 YYYY-MM-DD（N字）／快照失败：<原因>" if new_format else "— 摘录"
    vs: list[str] = []
    for ln in src_text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        if not SRC_RE.match(ln) and UNVERIFIED not in ln:
            vs.append(f"来源行格式不符（- YYYY.MM.DD，来源。*标题*。URL {tail_hint}）：{ln[:40]}")
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


def _lint_new_source_quotes(src_text: str) -> list[str]:
    """新格式专用：来源行尾不得内嵌**长**引文——逐字通道只有 ## 摘录 一条。

    评审实证：同一条伪造引文写在来源行尾，旧格式 FAIL（走 `_verify_quotes`），
    新格式零违规——把逐字核对接回来源行尾（`_verify_quotes`）会造出第二条逐字
    通道，与"逐字通道只有摘录层一条"的设计相反；但完全不闻不问又是覆盖倒退
    （研究 agent 从旧格式切过来，"引文写在来源行尾"是肌肉记忆，写手读的又正是
    这份文件）。折中：行尾出现够长的引号跨度就报违规，逼着把引文挪进 ## 摘录，
    不在这里核对内容。

    判据不是"出现引号字符"（复审复现三例假阳性：「深度报道」栏目名、12"／15"
    英寸符、"回应"这类短词加引号——旧格式命中后还有补形态标注放行的逃生口，
    新格式命中就是硬 FAIL、只能整句挪走，粗判据的误伤成本被放大，闸口一旦
    开始误伤就会被绕开）。改用 `QUOTE_RES` 取出引号跨度、量长度是否 ≥
    `QUOTE_MIN`——两个常量都是 `_lint_legacy` 判"是不是当真引用"现成用的，
    不新写正则、不新引阈值。
    """
    vs: list[str] = []
    for ln in src_text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        m2 = SRC_PARSE_RE.match(ln)
        if not m2:
            continue
        tail = m2.group(5)
        spans = [qm.group(1) for qre in QUOTE_RES for qm in qre.finditer(tail)]
        if any(len(s.strip()) >= QUOTE_MIN for s in spans):
            vs.append(
                f"来源行尾带着长引文——新格式的引文一律写进 ## 摘录（逐字通道只有摘录层"
                f"一条，来源行尾的引文不会被核对，也不会被写手看到）：{ln[:40]}"
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


def _lint_narrative_nonempty(secs: dict[str, str]) -> list[str]:
    """`## 事实`／`## 当事方` 不许是空节——新旧格式共用。

    260804-3 实测：`## 当事方` 整节留空仍拿 LINT OK。既有两道闸口都盖不住它——
    REQUIRED 只核标题在不在；孤儿检查按 [E] 编号算，某条摘录只要在 `## 事实` 里
    被引用过就不算孤儿，哪怕它独有的内容（当事人及家属表态之类）没被任何叙述句
    消费。而写手的叙述只取这两节，摘录层是逐字凭据、不是叙述来源，所以空节＝该节
    材料整批漏出流水线，且不留痕迹。
    """
    return [
        f"## {sec} 是空节——叙述层只有 事实/当事方 两节（摘录是逐字凭据层，不是叙述来源），"
        f"空节等于该节材料整批不进草稿"
        for sec in NARRATIVE_SECTIONS
        if sec in secs and not secs[sec].strip()
    ]


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
    # 不变量：过了格式闸（SRC_RE 匹配，或含 发布日期查证失败 旁路）的来源行条数
    # 必须等于 doc_sources() 实际解析出的信源数——Source.num 是"解析成功的第几条"
    # 不是"第几行"，两者一旦不等，它之后所有信源的编号在 linter 眼里全部错位，
    # 摘录写"信源N"引用的其实是另一条来源，逐字核对可能拿错来源的快照核（转载多的
    # 语料下核得过的概率还不低）。这条闸不依赖任何具体脏行样式，SRC_RE 与
    # SRC_PARSE_RE 今后任何一侧单独改动导致的分歧都会被它拦住，而不是静默错位。
    passed_lines = 0
    for ln in (secs.get("信息来源") or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("<!--"):
            continue
        if SRC_RE.match(ln) or UNVERIFIED in ln:
            passed_lines += 1
    if passed_lines != len(srcs):
        vs.append(
            f"## 信息来源 节有 {passed_lines} 行过了格式闸，但只解析出 {len(srcs)} 个"
            "信源——有来源行未能解析，其后所有信源编号会整体错位，摘录里的「信源N」"
            "会指向错误的来源"
        )
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
                f"[E{e.eid}] 信源{src.num} 无快照——跑 "
                f"/home/jc/Projects/auto-watcher/src/venv/bin/python "
                f"/home/jc/Projects/auto-watcher/src/srcfetch.py --event {event} "
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


def _lint_facts(text: str, eids: set[int], failed: dict[int, bool]) -> list[str]:
    """事实层每句必须挂 [E] 出处，引号跨度须命中某条摘录——逐字通道只有摘录层一条。

    句级归因是设计上限，不是本闸口的缺陷：一句内用逗号续接的独立事实主张不会被单独
    核出处（按逗号再切的误伤代价实测 28%，权衡后不做，fix 轮 1 F-1/F-2 讨论区）。
    """
    secs = _doc_sections(text)
    es = extracts(text)
    # F-2：四种形态的摘录**都**逐字取自快照，能作事实层"这句有出处"的凭据——只排除
    # 标题：媒体惯把第三人称改写成第一人称当标题，标题文本本身就可能是被制造出来的
    # "原话"，拿它背书直接引语＝把媒体的改写升格成当事人的话。
    # 260731-1 受控演练更正：此前连 第三人称转述 一并排除（理由写的是"转述同理，都不是
    # 当事人原话"），但事实层要引的大量是行政处罚决定书措辞与记者叙述，它们逐字躺在快照
    # 里、摘录层也照收，却没有任何合法出路——去掉引号＝把文书原文降格成转述，补一条摘录
    # ＝同一段再抄一遍改标 正文原话，等于教 agent 伪造形态。人称篡改不需要形态白名单挡：
    # 逐字比对本身就挡住了，转述摘录里没有的第一人称引文照样落空。
    # 写手层（linter.py 的灰字/红字基准）仍只认 正文原话——"这话是谁说的"归那里管。
    # 图上转录必须留在内：图上文字也是逐字转录，排除它会造出一类没有合法出路的假 FAIL。
    # 保留逐条列表（不只是 join 后的整串）——F-7b 的分段回退要挨条试"是不是同一条
    # 摘录里的"，不能只看拼起来的整串里有没有，那样等于把两条摘录的内容焊在一起。
    verbatim_bodies = [norm_quote(e.body) for e in es if e.form in FACT_VERBATIM_FORMS]
    # \x00 不在 normalize 的剥除集里，join 后不会让引文跨两条摘录拼出假命中
    base = "\x00".join(verbatim_bodies)
    vs: list[str] = []
    for sec in NARRATIVE_SECTIONS:
        # F-3：切句前把句末标点后的 [E] 标记搬到标点之前，脚注式与行内式归一到
        # 同一语义——否则脚注式的标记会随下一句被切走，出处整体错位一位
        body = MARK_AFTER_PUNCT_RE.sub(
            lambda m: m.group(2).strip() + m.group(1), secs.get(sec) or ""
        )
        for raw in split_sentences(body):
            s = raw.strip()
            if not s:
                continue
            # F-1：豁免只摘掉标记所在的那一行，不整片跳过。EXEMPT_RE 命中的是"一行"
            # 而 SENT_SPLIT_RE 只在 。！？ 处切句——豁免标记行本身常常不带句末标点
            # （后面紧跟着另一条独立事实，语料里 17 条豁免行有 4 条是这个形态），
            # 原实现按整片豁免会把这条独立事实一并放过、零信号。
            # F-4：同一逻辑下摘掉 `### ` markdown 小标题行——它们同样常年不带句末标点，
            # 单独留下会被当成"没挂出处的事实句"。`**加粗小标题**：` 不受影响（不同语法）。
            lines = [ln for ln in s.split("\n")
                     if ln.strip() and not EXEMPT_RE.search(ln)
                     and not HEADING_LINE_RE.match(ln.strip())]
            s = "\n".join(lines).strip()
            if not s:
                continue
            if len(CJK_RE.findall(E_REF_RE.sub("", s))) < SENT_MIN_CJK:
                continue
            ids = [int(x) for x in E_REF_RE.findall(s)]
            if not ids:
                vs.append(f"## {sec} 该句无 [E] 出处：{s[:30]}")
                continue
            for i in ids:
                if i not in eids:
                    vs.append(f"## {sec} 引用了不存在的 [E{i}]：{s[:30]}")
            known = [i for i in ids if i in eids]
            if known and all(failed.get(i) for i in known):
                vs.append(
                    f"## {sec} 该句只由 快照失败 的信源单独支撑，须与另一条有快照的来源并列："
                    f"{s[:30]}"
                )
        for qre in QUOTE_RES:
            for qm in qre.finditer(body):
                q = qm.group(1).strip()
                if len(q) < QUOTE_MIN:
                    continue
                # F-3：豁免窗口只认加粗的正式标记（FORMAL_MARK_RE），不用 CORRECTION_RE
                # 那种词面裸匹配——旧格式的 CORRECTION_RE/_lint_legacy 不动，见常量定义处注释
                if FORMAL_MARK_RE.search(
                    body[max(0, qm.start() - CORRECTION_LOOKBEHIND):qm.start()]
                ):
                    continue
                # 演练补：被推翻的旧错句排在正确表述之后，离标记远得超出上面的窗口，
                # 但紧跟着"原错误信息／原稿／误标"这类留痕提示词（见常量定义处注释）
                if TRAIL_CUE_RE.search(
                    body[max(0, qm.start() - TRAIL_CUE_LOOKBEHIND):qm.start()]
                ):
                    continue
                if norm_quote(q) in base:
                    continue
                # F-7b：省略号节略的逐字引文——整串比对必然落空（省略号本来就是承认
                # "这中间跳过了"，不是拼接），按省略号切段、每段单独命中即算命中。
                # 短于 QUOTE_MIN 的段不检查（沿用现成常量，不新引阈值）。
                #
                # fix 轮 2（controller 复核发现的 Critical）：每段必须命中**同一条**
                # 摘录，不能各段分别在 base（所有摘录拼起来的整串）里各找各的——那样
                # 会放行"E1 命中前半段、E2 命中后半段"的跨摘录拼接假引用，而省略号
                # 闸口原本就是防拼接的。改成对每一条摘录单独试"这条摘录是否同时包含
                # 全部分段"，任一条全中才放行。
                # 分段仍要走 norm_quote 再比对——body 是 norm_quote(e.body) 过的，
                # 段内混进 markdown 强调/引号壳（F-7a 刚修过的那一类）不归一化会被
                # 误判成不命中（fix 轮 2 R-1 复核发现：上一版比对漏了这一步）
                segs = [seg for seg in (t.strip() for t in ELLIPSIS_RE.split(q))
                        if len(seg) >= QUOTE_MIN]
                if segs and any(
                    all(norm_quote(seg) in body for seg in segs) for body in verbatim_bodies
                ):
                    continue
                # F-7c：只说"未命中"会让 agent 以为只能补一条假摘录——给出两条合法出路
                vs.append(
                    f"## {sec} 的引号跨度未命中任何摘录（摘录层是唯一逐字来源）——去掉"
                    f"引号写成不带引号的转述，或补一条摘录：{q[:30]}"
                )
    return vs


def lint_research(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    try:
        event_of(path)
    except ValueError as e:
        # 文件名不含 YYMMDD-N- 前缀：新旧两条路径都会无保护地调 event_of(path)
        # 抛裸 traceback。main() 是给人跑的，崩出 traceback 会让人以为是环境坏了，
        # 这里改成一条正常的 lint 违规。
        return [str(e)]
    # sections() 是 dict：同名的 `## ` 标题后者覆盖前者，前一节的全部内容会被
    # 整节静默丢弃——与结转第 4 项描述的失败模式一模一样，但因为标题是已知的，
    # 未知节标题闸口（见下）拦不住。放在分派之前、新旧两条路径都走：旧格式里
    # 同一个坑（比如两个 `## 信息来源`）同样会静默吞前一节。
    heads = [h.strip() for h in re.findall(r"^## (.+)$", text, re.MULTILINE)]
    if len(heads) != len(set(heads)):
        dupes = sorted({h for h in heads if heads.count(h) > 1})
        return [
            f"存在同名重复的二级标题：{'、'.join(dupes)}——sections() 是 dict，"
            "同名节后者覆盖前者，前一节的全部内容会被整节静默丢弃。若并非笔误新增了"
            "两个真实标题，也可能是 ## 摘录 里某条逐字引文本身顶格写着「## 事实」"
            "一类文本（判决书/聊天记录转录场景常见）——同样会被切开、吞掉其后内容；"
            "这种情况应让该行不顶格（缩进或加前缀），不要改引文的字（摘录必须逐字）"
        ]
    if is_new_format(text):
        return _lint_new(path, text)
    secs = _doc_sections(text)
    # 旧格式绝不会带 [E] 引用，也绝不会有含「摘录」的节标题（140 份存量实测为 0）。
    # 命中任一条＝这是一份摘录节标题写歪了的新格式文件，不能悄悄降级走旧闸口——
    # 旧闸口对摘录层一无所知，会让整套新闸口连跑都没跑却仍报"过了"，是"闸口失效
    # 不会有人发现"的教科书形态。判据取全文而非只取 事实/当事方 两节：更严格，
    # 也能兜住"标题缺空格且事实层恰好没挂 [E]"这类变体，140 份存量实测假阳性仍是 0。
    # [E] 判据用 E_REF_LOOSE_RE（收全半角方括号）而非 E_REF_RE——复审复现：标题漂成
    # 不含"摘录"的变体、且全文 [E] 引用全写成全角 ［E1］ 时，E_REF_RE 只认半角会同样
    # 落空，两个兜底判据一起哑火。E_REF_RE 本身不放宽，理由见该常量的定义处注释。
    drifted = [k for k in secs if "摘录" in k]
    if drifted or E_REF_LOOSE_RE.search(text):
        return [
            f"疑似新格式但没有恰好名为 ## 摘录 的节（现有：{drifted or '无'}）——"
            "摘录层闸口会被整体跳过，必须把标题改回 ## 摘录"
        ]
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
    vs += _lint_source_lines(secs.get("信息来源") or "", new_format=True)
    vs += _lint_new_source_quotes(secs.get("信息来源") or "")
    ex_vs, failed = _lint_extracts(path, text)
    vs += ex_vs
    vs += _lint_facts(text, {e.eid for e in extracts(text)}, failed)
    vs += _lint_blue(text)
    vs += _lint_narrative_nonempty(secs)
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
    vs += _lint_narrative_nonempty(secs)
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
