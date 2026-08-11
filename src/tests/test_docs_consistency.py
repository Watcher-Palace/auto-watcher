"""文档一致性：把 2026-07-22 审计的 prose 不变量固化进 CI（无模型断言，用户裁定）。"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).parents[2]
AGENTS = sorted((ROOT / ".claude" / "agents").glob("*.md"))
DOCS = AGENTS + sorted((ROOT / ".claude" / "skills").rglob("*.md")) + [ROOT / "CLAUDE.md"]

# 西里尔块 + 希腊块。整串的外文是合法的（俄语信源标题、人名、化学名里的希腊字母），
# 要抓的是外文字母**紧贴 ASCII 字母**——那只可能是一个拉丁单词被顶掉了词首。
_CONFUSABLE = r"Ѐ-ӿͰ-Ͽ"
MIXED_SCRIPT_RE = re.compile(f"[{_CONFUSABLE}][A-Za-z]|[A-Za-z][{_CONFUSABLE}]")


def test_human_section_single_spelling():
    assert AGENTS, "agents glob came up empty"
    for p in DOCS:
        assert "人类的裁定" not in p.read_text(encoding="utf-8"), f"{p}: 用 人类意见"


DEFAULT_LINE_CAP = 180
# blog-researcher 的职责在 2026-08-09 的快照重构里整体改写（抓快照存档＋整合），
# 新增的流程说明抵不过可删的旧叮嘱（可删的只有 5 行）。按文件临时放宽，不抬全局帽——
# 抬全局帽等于顺带给 blog-writer 松了 27 行的绳。欠账记在 CLAUDE.md ## 待办，
# 由 blog-curate 压回 180 后删掉这一条。
LINE_CAPS = {"blog-researcher.md": 190}


def test_agent_files_within_line_cap():
    for p in AGENTS:
        cap = LINE_CAPS.get(p.name, DEFAULT_LINE_CAP)
        n = len(p.read_text(encoding="utf-8").splitlines())
        assert n <= cap, f"{p.name} {n} 行 > {cap}（curate 规定需压缩）"


def test_experience_sections_within_entry_cap():
    for p in AGENTS:
        text = p.read_text(encoding="utf-8")
        if "## 累积经验" not in text:
            continue
        tail = text.split("## 累积经验", 1)[1]
        entries = re.findall(r"^- \[(?:NOTE|CANDIDATE)\]", tail, re.MULTILINE)
        assert len(entries) <= 15, f"{p.name} 累积经验 {len(entries)} 条 > 15"


def test_mixed_script_rule_separates_corruption_from_legitimate_foreign_text():
    # 全部用 \u 转义写：一来字面量会让上面那条全仓库扫描抓到本文件自己，二来手打
    # 这些字符正是出错的地方——本条测试第一版就把 γ 打成了西里尔 г。
    mon = "\u043c\u043e\u043d"                     # 西里尔 м о н，形同拉丁 mon
    tri = "\u0442\u0440\u0438"                     # 西里尔 т р и，形同拉丁 tri
    ie = "\u0415"                                    # 西里尔大写 Е，形同拉丁 E
    tyumen = "\u0422\u044e\u043c\u0435\u043d\u044c"   # 俄语地名 Тюмень（秋明）
    gamma = "\u03b3"                                 # 希腊 gamma，化学名用

    for bad in (mon + "keypatch", tri + "age", "SRC_PARSE_R" + ie):
        assert MIXED_SCRIPT_RE.search(bad), f"没抓到词首/词尾被顶掉的 {bad!r}"

    # 成串的外文，以及外文后接标点或汉字，都是本博客真实存在的合法内容，不许误伤
    for ok in (
        f"俄罗斯秋明市（{tyumen}）列宁区",   # 外文串裹在全角括号里
        f"{tyumen}.RU",                       # 外文串 + 点 + 拉丁词
        f"{gamma}-羟基丁酸的前体物质",        # 化学名：希腊字母后接连字符
        "EA News（欧亚新闻社）",              # 纯拉丁，不该有任何反应
    ):
        assert not MIXED_SCRIPT_RE.search(ok), f"误伤了合法外文 {ok!r}"


def test_no_mixed_script_words_in_tracked_files():
    # 中文散文里嵌英文标识符时，紧邻上文是汉字、没有拉丁脚本惯性，英文词的**词首**
    # token 会被同形的西里尔 token 顶掉：2026-08-10 实际发生两次，一次是 `мон` 接
    # `keypatch`，一次是 `три` 接 `age`。词首之后脚本被锁住，所以坏的总是开头一两个
    # 字符，肉眼与正体无异。落在中文注释里无害，落在标识符或字符串常量里会让闸口静默
    # 失效——本仓库的闸口全靠字符串常量比对，静默失效正是它最不能承受的失败模式。
    #
    # 判据是「外文字母紧贴 ASCII 字母」而不是「出现外文字母」：后者会误伤真实存在的
    # 合法用法（俄语案件的信源标题与人名、化学名 γ-羟基丁酸），而闸口一旦开始误伤，
    # 下一步就是被绕开。
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    hits, scanned = [], 0
    for name in out.split(b"\0"):
        if not name:
            continue
        p = ROOT / name.decode("utf-8")
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制资产（jpg/pdf/…），或已从工作区删除但尚未提交
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            m = MIXED_SCRIPT_RE.search(line)
            if m:
                hits.append(f"{name.decode('utf-8')}:{i}: {m.group()!r} 于 {line.strip()[:60]!r}")
    # 防空转：git 不可用或全体读失败时上面的循环会一个字符也没看就"通过"
    assert scanned > 300, f"只扫到 {scanned} 个文本文件，本仓库应有近千个——扫描没生效"
    assert not hits, "拉丁词里混进了西里尔/希腊同形字（中文夹英文时的词首采样错误）：\n" + "\n".join(hits)


def test_agent_python_commands_use_absolute_interpreter():
    # bare `python src/...` is not runnable in this environment (venv not on PATH,
    # shell state doesn't persist) — every command mention must go through the
    # absolute venv interpreter (`.../src/venv/bin/python src/...` or fully
    # absolute script paths).
    for p in AGENTS:
        text = p.read_text(encoding="utf-8")
        m = re.search(r"(?<!bin/)python src/", text)
        assert m is None, f"{p.name}: bare 'python src/' found near {text[max(0, m.start()-40):m.start()+40] if m else ''!r}"
