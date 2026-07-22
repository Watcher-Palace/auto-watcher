# 审计整改（A/B/C/E 组 + 脚本路径）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按批注过的 `docs/audit-agents-skills-260722.md` 执行全部已裁定项：A 组冲突修复、B 组重复收敛（casebook 迁移）、C 组脚本化（linter 扩展 + 新工具）、E 组 memory 清理，外加 agent 文件里脚本命令的解释器绝对路径修复。

**Architecture:** 先做纯文档修复（A 组 + 路径），再做 B 组 prose 收敛（casebook 为完整反例唯一归宿），然后 TDD 落 C 组代码（先扩 `linter.py`，再新建 `research_linter.py` 等工具，最后 `test_docs_consistency.py` 锁住 prose 不变量），最后清理 memory（E 组）。每任务一提交，直接进 main 并 push。

**Tech Stack:** Python 3 stdlib（venv `src/venv/`）、pytest（hermetic）、markdown prose。

## Global Constraints

- 测试命令：`cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python -m pytest src/tests/ -q`；起点 189 通过，任一任务结束不得低于起点。
- agent/skill 文件的说明文字一律简体中文。
- prose 编辑遵守 blog-curate 新硬规则：一条规则至多一个一行反例；完整错误链条只进 `docs/casebook.md`；writer+reviewer 共用规则归 `source/_drafts/template.md`。
- 提交直接进 main 并 push（solo repo 惯例）；提交信息结尾带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- 行号引用以 2026-07-22 commit `00a0d4d` 后的文件为准；编辑用唯一字符串匹配，不依赖行号。

## 裁定解释（执行前用户确认，如有异议先改这里）

1. **C3 填充语分级**：批注"引起关注/网络舆论有时避免不了"解释为——纯填充语（"此事沉寂数月后""网友纷纷表示"）FAIL；舆论反应词（"引发广泛关注""引发关注""引发热议"）降为 WARN。标题舆论词按原案 WARN。
2. **C7 时间线**：批注"时间线内可以有子标题，但不能拆分过度"与 template 现行"时间线内不再切自定义子节"（2026-07-21 裁定）冲突，按新裁定放宽 template 措辞；不做 lint。
3. **E2 "260525-1 弃置"**解释为：该行状态改为 `abort`（文章不存在于 source/_posts，published 名不副实），经 `ledger.update_row` 代码路径改，不裸编 CSV。
4. **E4 "合并为一条"**解释为：`feedback_usage_limit_breakpoints` 并入 `feedback_commit_to_main`（后者是更宽的规则），加优先级界定后删除前者。

---

## Phase 1 — 文档修复（A 组 + 脚本路径）

### Task 1: A1 评审"人类节"名称统一

**Files:** Modify: `.claude/agents/blog-writer.md`

- [ ] **Step 1: 编辑** — 把 `blog-writer.md` 中唯一一处 `` `## 人类的裁定` `` 改为 `` `## 人类意见` ``（该串在"不许删 review 文件里的 `[USER]` 注释"条内）。
- [ ] **Step 2: 验证**

```bash
grep -rn "人类的裁定" .claude/ CLAUDE.md; echo "exit=$?"
```
Expected: 无输出，exit=1。

- [ ] **Step 3: Commit** `fix(agents): 评审人类节统一为 人类意见（审计 A1）`

### Task 2: A2 summarize 陈旧模型说明删除

**Files:** Modify: `.claude/skills/blog-summarize/SKILL.md`

- [ ] **Step 1: 编辑** — 删除 `(matches the repo convention: research=Haiku, write/review=Sonnet)` 整个括号（含前导空格）。所在句保留为 "…Sonnet because the prose requires reading and grouping post bodies."
- [ ] **Step 2: 验证** `grep -c "Haiku" .claude/skills/blog-summarize/SKILL.md` → 0。
- [ ] **Step 3: Commit** `fix(skills): summarize 删除陈旧的 research=Haiku 说明（审计 A2）`

### Task 3: A3 orchestrate 行号锚点改节名锚点

**Files:** Modify: `.claude/skills/blog-orchestrate/SKILL.md`

- [ ] **Step 1: 编辑三处**
  1. `` (`blog-writer.md:46`) `` → `（见 blog-writer《Revision Mode》）`
  2. 同段 `` `blog-writer.md:78` `` → `blog-writer《不许删 review 文件里的 [USER] 注释》条`
  3. 4b-ii 段 `` （`blog-writer.md:78`） `` → `（blog-writer《不许删 review 文件里的 [USER] 注释》条）`
  4. `` `publisher.py:116` `` → `` publisher.py `publish()` 预检 ``
- [ ] **Step 2: 验证** `grep -n "blog-writer.md:[0-9]\|publisher.py:[0-9]" .claude/skills/blog-orchestrate/SKILL.md` → 无输出。
- [ ] **Step 3: Commit** `fix(skills): orchestrate 行号锚点改节名锚点（审计 A3）`

### Task 4: 脚本命令解释器绝对路径

**Files:** Modify: `.claude/agents/blog-researcher.md`, `.claude/agents/blog-writer.md`, `.claude/agents/blog-reviewer.md`

- [ ] **Step 1: 全部替换** — 三个文件中每处命令的 `src/venv/bin/python` 前缀改为 `/home/jc/Projects/auto-watcher/src/venv/bin/python`（researcher：wbfetch 两处 + review_linter 闸口；writer：linter 闸口 + review_linter 闸口 + 资产节 wbfetch 提及；reviewer：review_linter 闸口）。
- [ ] **Step 2: 验证**

```bash
grep -rn "^ *\`\?src/venv/bin/python\|[^/]src/venv/bin/python" .claude/agents/ | grep -v "/home/jc"
```
Expected: 无输出。

- [ ] **Step 3: Commit** `fix(agents): 闸口命令解释器改绝对路径（命令审计）`

---

## Phase 2 — B 组重复收敛

### Task 5: B2+B3 template 成为评论禁令与风格规则 canonical

**Files:** Modify: `.claude/agents/blog-writer.md`, `.claude/agents/blog-reviewer.md`, `.claude/agents/blog-researcher.md`（template 注释块本身已是全文，不动）

- [ ] **Step 1: writer 压缩** — 替换"只收事件，不收评论"整条为：

```
- **只收事件，不收评论（用户裁定，2026-07-21）：** 全文遵守 template 风格硬规则的评论禁令（含"言论本身即加害行为/被追责对象"这一唯一例外）。此禁令不限 `## 舆论` 节，`## 概述`/`#### 时间线`/`## 相关内容` 同样适用；研究文件收录了评论也不例外，写手自行剔除——"有来源支撑、能逐字引"只是必要条件，不构成可写理由。
```

同时把 Style Rules 前两条（em dash、filler）保留原样（一行级，无重复负担），但在 Style Rules 节首加一句：`（风格硬规则全文见 template 末尾注释块；以下为写手侧义务与展开）`。

- [ ] **Step 2: reviewer 压缩** — 步骤 6 中"评论禁令（用户裁定 2026-07-21：……）"整个括号内容替换为：`评论禁令（以 template 风格硬规则为准，含唯一例外；草稿出现评论转述开 类型：格式 问题，你自己也不得要求写手补入评论内容）`。
- [ ] **Step 3: researcher 压缩** — 替换"不收评论"整条为：

```
- **不收评论（用户裁定，2026-07-21）：** 事实节不收任何人对事件的评论——匿名网民留言、评论区回复、转发评论、微博热评、境外媒体转录的网民言论，与具名专家评论同等对待。唯一例外见 template 风格硬规则：该言论本身就是事件的加害行为或被追责对象时，它是事件事实，照收并注明发布者与出处。舆论规模只收可核实的具体数字（阅读量/讨论量/转发量/评论量/投票结果），不做定性。
```

- [ ] **Step 4: 验证** — `grep -c "加害行为或被追责对象" .claude/agents/*.md source/_drafts/template.md`：template 1 次、reviewer 0 次、researcher/writer 各 ≤1 次（指针句）。
- [ ] **Step 5: Commit** `refactor(agents): 评论禁令收敛至 template canonical（审计 B2/B3）`

### Task 6: B1 四条规则压缩 + casebook 迁移

**Files:** Modify: `.claude/agents/blog-researcher.md`, `.claude/agents/blog-writer.md`, `docs/casebook.md`

- [ ] **Step 1: casebook 录入两条**（追加到 `docs/casebook.md`）：

```
## 260716-7 转引自媒体被"据报道"洗白
- 规则：blog-researcher《转引自媒体的说法不算独立信源》/ blog-writer《转引自媒体的说法＝没有来源》
- 链条：自媒体"四海瞭望"称"因未满足法官要求，王女士最终输掉离婚案件"→ 新唐人电视台转引 → 研究文件标为"（来源：新唐人电视台转引报道）"→ 写手写成"据报道"进正文 → 用户删句。
- 出处：_pipeline_archive/research、review 下 260716-7 各版本。

## 事件号未记录 转发帖被当作来源
- 规则：blog-researcher《转发帖不作来源》/ blog-writer《转发帖不进文章》
- 链条：某案把博主 A 转发博主 B 的内容当来源，来源行只能写"A（转发 B 内容）"，读者无从对应原始出处。
- 出处：规则沉淀时未记事件号。
```

- [ ] **Step 2: researcher 三条压缩**（"不收评论"已由 Task 5 处理）——分别替换为：

```
- **转发帖不作来源，要引就引原帖（用户裁定，2026-07-21）：** 转发帖不进事实基、不进 `## 信息来源`；例外：转发者本人是当事方（含家属）、媒体机构或官方机构（转发按语属该方表态，照收）。普通网民/自媒体的转发只当检索线索：定位原帖，以原帖作者、原帖日期、原帖 URL 入来源；原帖找不到或无法访问，该说法即不可用。原帖本身照收（按评论排除规则剔除评论成分）。（例见 casebook）
```

```
- **转引自媒体的说法不算独立信源（用户裁定，2026-07-21）：** 媒体报道里"据自媒体X报道""某公众号称""网传"的内容，真实出处是自媒体，媒体只是转引——不满足两独立信源，也不得在条目上标成"（来源：某某媒体）"。这类说法不进事实节；确需留作线索时，条目末尾括号写明完整链条（自媒体名→转引媒体）并注明"仅自媒体转述，写手不得使用"。（反例见 casebook：260716-7）
```

```
- **记者行为必须带媒体归属（用户裁定，2026-07-20）：** 事实条目出现"记者致电/采访/暗访/检索文书"必须写明是哪家媒体的记者，转载页追到正文/文末署名的原始采写媒体；确实查不到署名的注明"（采写媒体未署名）"。本博客没有记者，无归属的"记者"会被读者误解为本站采写，写手只能按缺口退回。
```

- [ ] **Step 3: writer 三条压缩**——分别替换为：

```
- **记者必须写明是哪家媒体的记者（用户裁定，2026-07-20）：** 本博客没有记者。正文出现"记者致电""记者采访"必须写清所属媒体；研究文件未注明归属的按缺口上报，不得写无主语的"记者"。"报道发出时""截至发稿"只能指向能对应到的具体真实报道；指本文自身时点一律写"本文撰写时"。
```

```
- **转发帖不进文章、不进来源（用户裁定，2026-07-21）：** 普通网民/自媒体的转发帖不得写进正文或 `## 信息来源`；例外：转发者本人是当事方（含家属）、媒体机构或官方机构。研究文件里只挂转发帖的说法（来源行形如"A（转发 B 内容）"），整句删除、来源行删除，不留"未见证实"式缺口说明。原帖可以用：当事方自述、博主首发爆料照写照引。（例见 casebook）
```

```
- **转引自媒体的说法＝没有来源，不许用"据报道"洗白（用户裁定，2026-07-21）：** 媒体报道里"据自媒体X报道""某公众号称""网传"的内容，出处仍是自媒体，不构成媒体自采、不构成独立信源——整句删除，不进草稿；尤其禁止写成含糊的"据报道""据媒体报道"。凡写不出具体归属的说法，就是不能写。（完整链条见 casebook：260716-7）
```

- [ ] **Step 4: 验证** `grep -c "四海瞭望" .claude/agents/*.md` → 全 0；`grep -c "四海瞭望" docs/casebook.md` → 1。全文重读两 agent 文件确认无断句残留。
- [ ] **Step 5: Commit** `refactor(agents): B1 四条规则压缩，完整反例迁入 casebook（审计 B1）`

### Task 7: B4 researcher 内部去重

**Files:** Modify: `.claude/agents/blog-researcher.md`, `docs/casebook.md`

- [ ] **Step 1: casebook 录入**：

```
## 260707-2 / 260704-1 / 260703-2 tracker 来源归属三类错
- 规则：blog-researcher《Step 0》brief/来源不符即停下报回
- 链条：260707-2 来源 URL 挂到同批另一条无关帖子（湖北龙卷风微博）；260704-1 来源指向转发链末端需回溯原帖；260703-2 把江苏高邮"亡人事件"杀妻案与湖南母亲被造谣案缝进同一句 brief。
- 出处：2026-07-21 用户裁定，三次复现。
```

- [ ] **Step 2: Your Inputs 压缩** — `sources` 字段整条替换为：

```
- `sources`: initial Weibo source URLs, if any (initial mode) — **可能挂错，按 Step 0 的核对规则先验证再用**（tracker 归属由 Haiku 判定，出过错；事件文件 `**Sources**` 行带"来源存疑"字样同样处理）
```

- [ ] **Step 3: Step 0 压缩案例** — "brief／来源与实际内容不符"段中三类错的具体案例描述改为 `出过三类错：来源 URL 挂到同批另一条无关帖子、来源指向转发链末端要回溯原帖、两件不相关的事被缝进同一句 brief（链条见 casebook：260707-2/260704-1/260703-2）`，其余（停下报回、由人裁决）保留。
- [ ] **Step 4: 验证** `grep -c "龙卷风" .claude/agents/blog-researcher.md` → 0。
- [ ] **Step 5: Commit** `refactor(agents): researcher 内部重复收敛（审计 B4）`

### Task 8: B5 批量规则收敛到 Notes

**Files:** Modify: `.claude/skills/blog-orchestrate/SKILL.md`

- [ ] **Step 1: 编辑** — Stage 2 的 `When processing multiple events, dispatch in **batches of up to 3** — wait for the batch to finish before dispatching the next (user directive 2026-07-20).` 改为 `多事件时按批派发（批量规则见 Notes）。`；Stage 3 的 `Dispatch in **batches of up to 3** (user directive 2026-07-20).` 同样改为 `（批量规则见 Notes）`。Notes 节保留全文。
- [ ] **Step 2: 验证** `grep -c "up to 3" .claude/skills/blog-orchestrate/SKILL.md` → 1。
- [ ] **Step 3: Commit** `refactor(skills): 批量派发规则收敛到 Notes（审计 B5）`

### Task 9: B6 summarize N 速记 + C7 template 时间线放宽

**Files:** Modify: `.claude/skills/blog-summarize/SKILL.md`, `source/_drafts/template.md`

- [ ] **Step 1: summarize** — `N 中立事件/等待后续` 改为 `N 中立事件（存疑/已获公正解决/相关性不确定）/等待后续`。
- [ ] **Step 2: template** — 替换整段：

```
**时间线内子节不过度拆分（2026-07-22 放宽，取代 2026-07-21"不切子节"）：**
时间线内可以用自定义子节组织长案情，但不要为相邻几天各起一个小节；
同一天的多条并进同一个日期条目。
```

- [ ] **Step 3: 验证** `grep -c "不再切自定义子节" source/_drafts/template.md` → 0。
- [ ] **Step 4: Commit** `fix(docs): summarize N 速记对齐、时间线子节放宽（审计 B6/C7 裁定）`

---

## Phase 3 — C 组脚本化（每任务 TDD：测试→红→实现→绿→提交）

### Task 10: C3 linter 四条小规则

**Files:** Modify: `src/linter.py`; Test: `src/tests/test_linter.py`

**Interfaces:** Produces: `lint_text` 新增 FAIL 项（填充语、蓝字）；`lint_warnings(content)` 返回舆论词 WARN；`lint_file_title_vs_slug(path, fm_title) -> str | None` 并入 `main` 流程（草稿文件名形如 `YYMMDD-N-标签-vN.md` 时才检查）。

- [ ] **Step 1: 写失败测试**（追加到 `src/tests/test_linter.py`，沿用该文件现有 fixture 风格；若无现成构造函数则直接调 `lint_text(content, None, date(2099,1,1))`）：

```python
def _doc(body, title="独立成文的标题", cats="B", tags="- 犯罪\n- 未立案"):
    return f"---\ntitle: {title}\ndate: 2026-01-01\ncategories: {cats}\ntags:\n{tags}\n---\n{body}"

BODY_OK = "## 概述\nx<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.1.1，来源。*题*。https://a/\n"

def test_filler_phrases_fail():
    vs = lint_text(_doc(BODY_OK.replace("x", "此事沉寂数月后，")), None, date(2099, 1, 1))
    assert any("填充语" in v for v in vs)

def test_blue_font_exactly_one():
    no_blue = lint_text(_doc(BODY_OK.replace('<font color="blue">2026年1月1日判决</font>', "")), None, date(2099, 1, 1))
    two_blue = lint_text(_doc(BODY_OK + '<font color="blue">又一进展</font>'), None, date(2099, 1, 1))
    stale = lint_text(_doc(BODY_OK.replace("2026年1月1日判决", "截至目前暂无进展")), None, date(2099, 1, 1))
    assert any("蓝" in v for v in no_blue) and any("蓝" in v for v in two_blue) and any("蓝" in v for v in stale)

def test_title_opinion_words_warn():
    ws = lint_warnings(_doc(BODY_OK, title="某案宣判引发关注"))
    assert any("舆论反应词" in w for w in ws)

def test_opinion_filler_warn_not_fail():
    content = _doc(BODY_OK.replace("x", "该事件引发广泛关注。"))
    assert not any("填充语" in v for v in lint_text(content, None, date(2099, 1, 1)))
    assert any("舆论" in w for w in lint_warnings(content))

def test_title_equals_slug_fails(tmp_path):
    d = tmp_path / "draft"; d.mkdir()
    p = d / "990101-1-内部标签-v1.md"
    p.write_text(_doc(BODY_OK, title="内部标签"), encoding="utf-8")
    assert any("内部索引标签" in v for v in lint_slug_title(p, "内部标签"))
```

- [ ] **Step 2: 跑红** `python -m pytest src/tests/test_linter.py -q -k "filler or blue or opinion or slug"` → FAIL。
- [ ] **Step 3: 实现**（`src/linter.py`）：

```python
FILLER_FAIL_RE = re.compile(r"此事沉寂数月后|网友纷纷表示")
OPINION_WARN_RE = re.compile(r"引发广泛关注|引起广泛关注|引发关注|引发热议")
TITLE_OPINION_RE = re.compile(r"引争议|引发争议|引质疑|引发质疑|引发关注|引发热议|惹众怒")
BLUE_RE = re.compile(r'<font color="blue">(.*?)</font>', re.S)
NO_PROGRESS_RE = re.compile(r"暂无|尚未|无最新进展|未发布通报")

# lint_text 内追加：
    if FILLER_FAIL_RE.search(prose):
        violations.append("填充语出现（此事沉寂数月后/网友纷纷表示 类）——直接陈述事实")
    blues = BLUE_RE.findall(prose)
    if len(blues) != 1:
        violations.append(f"蓝字标记应恰好 1 处（现 {len(blues)} 处）——标最新真实进展")
    elif NO_PROGRESS_RE.search(blues[0]):
        violations.append("蓝字内容是'暂无进展'类句子——蓝字必须是真实事实进展")

# lint_warnings 重写：
def lint_warnings(content: str) -> list[str]:
    fm = read_frontmatter(content)
    prose = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    warnings: list[str] = []
    title = str(fm.get("title") or "")
    if TITLE_OPINION_RE.search(title):
        warnings.append(f"标题含舆论反应词（{TITLE_OPINION_RE.search(title).group()}）——除非争议即事件主体，删掉")
    if OPINION_WARN_RE.search(prose):
        warnings.append("正文含舆论反应措辞（引发关注类）——舆论事件难免时可保留，否则删")
    return warnings

def lint_slug_title(path: Path, fm_title: str) -> list[str]:
    m = re.match(r"\d{6}-\d+-(.+)-v\d+$", path.stem)
    if m and fm_title.strip() == m.group(1):
        return ["title 与内部索引标签相同——标题必须另写（信息完整、能独立读懂）"]
    return []

# main() 内、算完 vs 之后追加：
        vs += lint_slug_title(path, str((read_frontmatter(content) or {}).get("title") or ""))
```

- [ ] **Step 4: 跑绿 + 全量** `python -m pytest src/tests/ -q` → 全过。
- [ ] **Step 5: writer prose 缩行** — blog-writer.md"标题不追加舆论反应"与"标题自己写"两条末尾各加一句 `（linter 会拦/警告）`；填充语条同理。不删规则本体（判断例外仍需 prose）。
- [ ] **Step 6: Commit** `feat(linter): 标题/填充语/蓝字四条检查（审计 C3，按裁定分级）`

### Task 11: C1 草稿 ↔ 研究文件交叉对账

**Files:** Modify: `src/linter.py`; Test: `src/tests/test_linter.py`

**Interfaces:** Produces: `crosscheck_research(draft_text, research_text) -> tuple[list[str], list[str]]`（violations, warnings）；CLI `python src/linter.py <draft> --research <research.md>`。

- [ ] **Step 1: 写失败测试**：

```python
RESEARCH = ("## 事实\n白女士报案。\n## 信息来源\n"
            "- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录\n")

def test_crosscheck_source_url_missing():
    draft = _doc(BODY_OK.replace("https://a/", "https://other/"))
    vs, _ = crosscheck_research(draft, RESEARCH)
    assert any("URL" in v for v in vs)

def test_crosscheck_source_title_date_mismatch():
    draft = _doc("## 概述\nx<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.1.1，澎湃新闻。*错标题*。https://a/b\n")
    vs, _ = crosscheck_research(draft, RESEARCH)
    assert any("标题" in v or "日期" in v for v in vs)

def test_crosscheck_names_warn():
    draft = _doc("## 概述\n林悦（化名）与高某某。<font color=\"blue\">2026年1月1日判决</font>\n## 信息来源\n2026.1.1，澎湃新闻。*真标题*。https://a/b\n")
    _, ws = crosscheck_research(draft, RESEARCH)
    assert any("林悦" in w for w in ws) and any("高某某" in w for w in ws)
    assert not any("白女士" in w for w in ws)
```

- [ ] **Step 2: 跑红**。
- [ ] **Step 3: 实现**：

```python
DRAFT_SRC_RE = re.compile(r"^(?:- )?(\d{4}\.\d{1,2}\.\d{1,2})，(.+?)。\*(.+?)\*。(\S+)", re.M)
NAME_RE = re.compile(r"[一-龥]{1,2}(?:某某|某|女士|先生)|小[一-龥]")
ALIAS_RE = re.compile(r"([一-龥]{2,3})（(?:报道使用)?化名）")

def crosscheck_research(draft_text: str, research_text: str) -> tuple[list[str], list[str]]:
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

# main()：解析 --research <path>；命中时 vs/ws 各自并入。
```

- [ ] **Step 4: 跑绿 + 全量**。
- [ ] **Step 5: 文档对接** — blog-writer.md Lint gate 命令改为 `…/src/linter.py <draft-path> --research <research-path>`；Sources 条与"人物称呼自查"条末尾加 `（linter --research 会拦/警告）`；orchestrate 无需改（写手自跑）。
- [ ] **Step 6: Commit** `feat(linter): --research 交叉对账，来源 FAIL/称呼 WARN（审计 C1）`

### Task 12: C7 前情/后续链接检查

**Files:** Modify: `src/linter.py`; Test: `src/tests/test_linter.py`

- [ ] **Step 1: 写失败测试**：

```python
def test_prequel_section_requires_site_link():
    body = "## 前情\n1月1日：无链接描述。\n" + BODY_OK
    vs = lint_text(_doc(body), None, date(2099, 1, 1))
    assert any("前情" in v and "参见" in v for v in vs)

def test_prequel_with_link_ok():
    body = "## 前情\n1月1日：简述。参见：[题](/2026/260101/)\n" + BODY_OK
    vs = lint_text(_doc(body), None, date(2099, 1, 1))
    assert not any("前情" in v for v in vs)
```

- [ ] **Step 2: 跑红**。
- [ ] **Step 3: 实现**（`lint_text` 内）：

```python
    for sec in ("前情", "后续"):
        if sec in secs:
            lines = [l for l in secs[sec].splitlines() if l.strip() and not l.strip().startswith("<!--")]
            if lines and not any(re.search(r"参见：\[.+?\]\(/\d{4}/", l) for l in lines):
                violations.append(f"## {sec} 缺站内 参见 链接——该节仅用于链接本站已发布文章")
```

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: Commit** `feat(linter): 前情/后续须带站内参见链接（审计 C7）`

### Task 13: C2 research_linter.py 研究文件闸口

**Files:** Create: `src/research_linter.py`; Test: `src/tests/test_research_linter.py`

**Interfaces:** Produces: `lint_research(path: Path) -> list[str]`；CLI `python src/research_linter.py <research.md>...`，退出码 0/1。资产目录由路径推导：`path.parent.parent / "draft" / f"{date}-{n}-assets"`。

- [ ] **Step 1: 写失败测试**（`src/tests/test_research_linter.py`）：

```python
import pytest
from pathlib import Path
from src.research_linter import lint_research

GOOD = ("# Research: 题 (990101, #1)\n\n## 事实\n"
        "<font color=\"blue\">2026年1月1日宣判</font>\n\n## 当事方\n某人\n\n"
        "## 信息来源\n- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录\n\n## 资产\n无\n")

def _mk(tmp_path, text, assets: list[str] | None = None):
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "research" / "990101-1-题.md"
    p.write_text(text, encoding="utf-8")
    if assets is not None:
        d = tmp_path / "draft" / "990101-1-assets"
        d.mkdir(parents=True)
        for name in assets:
            (d / name).write_text("x", encoding="utf-8")
    return p

def test_good_file_passes(tmp_path):
    assert lint_research(_mk(tmp_path, GOOD)) == []

def test_missing_section_and_bad_source_line(tmp_path):
    text = GOOD.replace("## 当事方\n某人\n\n", "").replace(
        "- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录", "- 澎湃新闻报道了")
    vs = lint_research(_mk(tmp_path, text))
    assert any("当事方" in v for v in vs) and any("来源行" in v for v in vs)

def test_source_line_allows_unverified_date_marker(tmp_path):
    text = GOOD.replace("- 2026.1.1，澎湃新闻。*真标题*。https://a/b — 摘录",
                        "- 澎湃新闻。*真标题*。https://a/b — 摘录（发布日期查证失败）")
    assert lint_research(_mk(tmp_path, text)) == []

def test_blue_mark_rules(tmp_path):
    no_date = GOOD.replace("2026年1月1日宣判", "已经宣判")
    stale = GOOD.replace("2026年1月1日宣判", "截至2026年1月1日暂无进展")
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, no_date)))
    assert any("蓝" in v for v in lint_research(_mk(tmp_path, stale)))

def test_assets_bidirectional(tmp_path):
    listed = GOOD.replace("## 资产\n无\n", "## 资产\n- 990101-1-图.jpg — https://a — 2026.1.1 — 通报截图\n")
    vs = lint_research(_mk(tmp_path, listed, assets=[]))          # 登记了但文件不存在
    assert any("不存在" in v for v in vs)
    vs2 = lint_research(_mk(tmp_path, GOOD, assets=["990101-1-孤儿.jpg"]))  # 存在但未登记
    assert any("未登记" in v for v in vs2)
```

- [ ] **Step 2: 跑红**（import 失败即红）。
- [ ] **Step 3: 实现** `src/research_linter.py`：

```python
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
```

- [ ] **Step 4: 跑绿 + 全量**。
- [ ] **Step 5: 文档对接** — blog-researcher.md 在 Output 节后加 **Lint gate (mandatory)**：`/home/jc/Projects/auto-watcher/src/venv/bin/python /home/jc/Projects/auto-watcher/src/research_linter.py <research-file>`，修完所有违规才许报完成；同时来源行格式条、蓝字条、资产登记条末尾各加 `（research_linter 会拦）`。
- [ ] **Step 6: Commit** `feat: research_linter 研究文件闸口（审计 C2）`

### Task 14: C6 review_linter 标签提案转录检查

**Files:** Modify: `src/review_linter.py`; Test: `src/tests/test_review_linter.py`

- [ ] **Step 1: 写失败测试**（沿用该文件现有 draft/review 目录构造方式；若为直接函数调用风格则如下）：

```python
def test_tag_proposals_must_transcribe():
    from src.review_linter import check_tag_proposals
    draft = "---\ntags:\n---\n<!-- [TAG-PROPOSAL]: 新标签 — 理由 -->\n正文"
    review_missing = "STATUS: CLEAN\n"
    review_ok = "STATUS: CLEAN\n\n## 标签提案\n- 新标签 — 理由\n"
    assert any("新标签" in v for v in check_tag_proposals(review_missing, draft))
    assert check_tag_proposals(review_ok, draft) == []
```

- [ ] **Step 2: 跑红**；**Step 3: 实现**：

```python
TAG_PROPOSAL_RE = re.compile(r"<!--\s*\[TAG-PROPOSAL\]:\s*(.+?)\s*-->")

def check_tag_proposals(review_text: str, draft_text: str) -> list[str]:
    vs = []
    for prop in TAG_PROPOSAL_RE.findall(draft_text):
        name = prop.split("—")[0].split("-")[0].strip()
        if name and name not in review_text:
            vs.append(f"草稿的标签提案未转录进评审 ## 标签提案：{name}")
    return vs
```

`main()` 默认模式在 `validate_anchors` 之后追加 `violations += check_tag_proposals(text, draft_text)`。

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: Commit** `feat(review_linter): 标签提案转录检查（审计 C6）`

### Task 15: C4 pipeline_cli ping-due

**Files:** Modify: `src/utils/pipeline.py`（加 `POSTS = REPO_ROOT / "source" / "_posts"`）, `src/pipeline_cli.py`; Test: `src/tests/test_pipeline_cli.py`

- [ ] **Step 1: 写失败测试**：

```python
def test_ping_due_lists_stale_ping_posts(pipe, tmp_path, monkeypatch, capsys):
    posts = tmp_path / "posts"; posts.mkdir()
    monkeypatch.setattr("src.utils.pipeline.POSTS", posts)
    (posts / "250101.md").write_text(
        "---\ntitle: 旧案\ndate: 2025-01-01\ntags:\n- PING\n---\n", encoding="utf-8")
    (posts / "990101.md").write_text(
        "---\ntitle: 新案\ndate: 2099-01-01\ntags:\n- PING\n---\n", encoding="utf-8")
    assert main(["ping-due"]) == 0
    out = capsys.readouterr().out
    assert "旧案" in out and "新案" not in out
```

- [ ] **Step 2: 跑红**；**Step 3: 实现**（`pipeline_cli.py` 新分支 + docstring 加用法行）：

```python
    if cmd == "ping-due":
        from datetime import date, timedelta
        from src.publisher import read_frontmatter
        from src.utils import pipeline as pl
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        for p in sorted(pl.POSTS.glob("*.md")):
            fm = read_frontmatter(p.read_text(encoding="utf-8"))
            if "PING" in (fm.get("tags") or []) and str(fm.get("date"))[:10] <= cutoff:
                print(f"{p.stem}  {str(fm.get('date'))[:10]}  {fm.get('title', '')}")
        return 0
```

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: 文档** — blog-writer.md PING 条运维句改为 `运维方式：python src/pipeline_cli.py ping-due 列出待巡检文章…`；CLAUDE.md 子命令列表加 `ping-due`。**Step 6: Commit** `feat(cli): ping-due 巡检队列（审计 C4）`

### Task 16: C9 pipeline_cli dedup

**Files:** Modify: `src/pipeline_cli.py`; Test: `src/tests/test_pipeline_cli.py`

- [ ] **Step 1: 写失败测试**：

```python
def test_dedup_scans_ledger_posts_research(pipe, tmp_path, monkeypatch, capsys):
    posts = tmp_path / "posts"; posts.mkdir()
    monkeypatch.setattr("src.utils.pipeline.POSTS", posts)
    (posts / "250101.md").write_text("---\ntitle: 张某案宣判\n---\n正文", encoding="utf-8")
    (pipe / "research").mkdir()
    (pipe / "research" / "990101-1-张某案.md").write_text("张某", encoding="utf-8")
    ledger.add_event("990102", 1, "李某案", pipeline_dir=pipe)
    assert main(["dedup", "张某"]) == 0
    out = capsys.readouterr().out
    assert "250101" in out and "990101-1" in out and "李某" not in out
```

- [ ] **Step 2: 跑红**；**Step 3: 实现**（新分支 + docstring 行；`pl.ARCHIVE / "research"` 一并扫）：

```python
    if cmd == "dedup":
        from src.utils import pipeline as pl
        kws = args
        if not kws:
            print("usage: dedup <关键词>...")
            return 1
        for r in ledger.read_rows():
            if r["标题"] and any(k in r["标题"] for k in kws):
                print(f"账本 {r['收录日期']}-{r['事件编号']} [{r['状态']}] {r['标题']}")
        for base in (pl.POSTS, pl.PIPELINE / "research", pl.ARCHIVE / "research"):
            if not base.exists():
                continue
            for p in sorted(base.glob("*.md")):
                text = p.read_text(encoding="utf-8")
                if any(k in p.name or k in text for k in kws):
                    print(f"{base.parent.name}/{base.name}/{p.name}")
        return 0
```

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: 文档** — blog-researcher.md Step 0 首句加 `先跑 python src/pipeline_cli.py dedup <当事人/地名/关键词>（含账本、已发布、研究存档），再人工判断`；CLAUDE.md 子命令列表加 `dedup`。**Step 6: Commit** `feat(cli): dedup 同案查重扫描（审计 C9）`

### Task 17: C5 publish_summary.py

**Files:** Create: `src/publish_summary.py`; Test: `src/tests/test_publish_summary.py`; Modify: `.claude/skills/blog-summarize/SKILL.md`

- [ ] **Step 1: 写失败测试**：

```python
import pytest
from pathlib import Path
from src.publish_summary import publish_summary

def _env(tmp_path, monkeypatch, fm='summary_month: "2605"'):
    monkeypatch.setattr("src.utils.pipeline.PIPELINE", tmp_path / "_pipeline")
    monkeypatch.setattr("src.utils.pipeline.REPO_ROOT", tmp_path)
    d = tmp_path / "_pipeline" / "summary"; d.mkdir(parents=True)
    (d / "2605.md").write_text(f"---\ntitle: t\n{fm}\n---\n正文", encoding="utf-8")

def test_publish_summary_copies_draft(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    publish_summary("2605", deploy=False)
    assert (tmp_path / "source" / "summaries" / "2605.md").read_text(encoding="utf-8").endswith("正文")

def test_publish_summary_rejects_wrong_month(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, fm='summary_month: "2604"')
    with pytest.raises(SystemExit):
        publish_summary("2605", deploy=False)
```

- [ ] **Step 2: 跑红**；**Step 3: 实现**：

```python
"""月度总结发布：cp → pnpm build → pnpm run deploy（对齐 publisher 的链式顺序）。"""
from __future__ import annotations
import subprocess
import sys
from src.utils import pipeline as pl


def publish_summary(yymm: str, deploy: bool = True) -> None:
    src = pl.PIPELINE / "summary" / f"{yymm}.md"
    if not src.exists():
        raise SystemExit(f"找不到总结草稿：{src}")
    text = src.read_text(encoding="utf-8")
    if f'summary_month: "{yymm}"' not in text:
        raise SystemExit(f"frontmatter summary_month 与参数 {yymm} 不符")
    dst = pl.REPO_ROOT / "source" / "summaries" / f"{yymm}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"已复制 → {dst}")
    if deploy:
        subprocess.run(["pnpm", "run", "build"], cwd=pl.REPO_ROOT, check=True)
        subprocess.run(["pnpm", "run", "deploy"], cwd=pl.REPO_ROOT, check=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python src/publish_summary.py <YYMM>")
    publish_summary(sys.argv[1])
```

（注意 `src/utils/pipeline.py` 里若 `REPO_ROOT` 只是局部常量，本任务顺带确认它是模块级可 monkeypatch 的——现状即是。）

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: 文档** — blog-summarize SKILL Stage B 的 cp/pnpm 代码块替换为 `python src/publish_summary.py {YYMM}`（前缀 cd+activate），语义说明保留。CLAUDE.md Monthly Summary 节 Stage B 同步。**Step 6: Commit** `feat: publish_summary 固化总结发布链（审计 C5）`

### Task 18: C8 imgfetch.py

**Files:** Create: `src/imgfetch.py`; Test: `src/tests/test_imgfetch.py`; Modify: `.claude/agents/blog-researcher.md`

- [ ] **Step 1: 写失败测试**：

```python
import pytest
from src.imgfetch import classify

def test_classify_accepts_real_image():
    assert classify(b"\xff\xd8\xff" + b"x" * 5000) == "jpg"
    assert classify(b"\x89PNG\r\n\x1a\n" + b"x" * 5000) == "png"
    assert classify(b"%PDF-1.4" + b"x" * 5000) == "pdf"

def test_classify_rejects_placeholder_and_html():
    with pytest.raises(ValueError):
        classify(b"\xff\xd8\xff" + b"x" * 100)      # 太小=占位图
    with pytest.raises(ValueError):
        classify(b"<html><body>login</body></html>" + b"x" * 5000)
```

- [ ] **Step 2: 跑红**；**Step 3: 实现**：

```python
"""证据图/文书下载器：带 Referer 抓取并校验类型与大小，防占位图。"""
from __future__ import annotations
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"GIF8": "gif",
         b"RIFF": "webp", b"%PDF": "pdf"}
MIN_BYTES = 2048


def classify(data: bytes) -> str:
    kind = next((k for m, k in MAGIC.items() if data.startswith(m)), None)
    if kind is None:
        raise ValueError(f"不是图片/PDF（前 16 字节：{data[:16]!r}）——可能拿到防盗链占位页")
    if len(data) < MIN_BYTES:
        raise ValueError(f"文件过小（{len(data)}B < {MIN_BYTES}B）——疑似占位图")
    return kind


def fetch(url: str, dest: Path, referer: str | None = None) -> str:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    data = urllib.request.urlopen(req, timeout=30).read()
    kind = classify(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"OK {dest}（{len(data)}B {kind}）"


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit("usage: python src/imgfetch.py <url> <dest> [--referer URL]")
    ref = argv[argv.index("--referer") + 1] if "--referer" in argv else None
    try:
        print(fetch(argv[0], Path(argv[1]), ref))
    except Exception as e:
        raise SystemExit(f"FAIL {argv[0]}: {e}")
```

- [ ] **Step 4: 跑绿 + 全量**；**Step 5: 文档** — blog-researcher.md 资产抓取"怎么抓"条替换为：普通网页图用 `/home/jc/Projects/auto-watcher/src/venv/bin/python /home/jc/Projects/auto-watcher/src/imgfetch.py <图片URL> <目标路径> --referer <页面URL>`（自动校验类型与大小，FAIL 即换源或如实记失败）；微博图仍先 wbfetch 取 `image_urls` 再逐个 imgfetch。**Step 6: Commit** `feat: imgfetch 证据图下载器（审计 C8）`

### Task 19: C10 docs 一致性测试

**Files:** Create: `src/tests/test_docs_consistency.py`

- [ ] **Step 1: 写测试**（此任务测试即产品，直接绿即可）：

```python
"""文档一致性：把 2026-07-22 审计的 prose 不变量固化进 CI（无模型断言，用户裁定）。"""
from pathlib import Path
import re

ROOT = Path(__file__).parents[2]
AGENTS = sorted((ROOT / ".claude" / "agents").glob("*.md"))
DOCS = AGENTS + sorted((ROOT / ".claude" / "skills").rglob("*.md")) + [ROOT / "CLAUDE.md"]


def test_human_section_single_spelling():
    for p in DOCS:
        assert "人类的裁定" not in p.read_text(encoding="utf-8"), f"{p}: 用 人类意见"


def test_agent_files_within_line_cap():
    for p in AGENTS:
        n = len(p.read_text(encoding="utf-8").splitlines())
        assert n <= 180, f"{p.name} {n} 行 > 180（curate 规定需压缩）"


def test_experience_sections_within_entry_cap():
    for p in AGENTS:
        text = p.read_text(encoding="utf-8")
        if "## 累积经验" not in text:
            continue
        tail = text.split("## 累积经验", 1)[1]
        entries = re.findall(r"^- \[(?:NOTE|CANDIDATE)\]", tail, re.MULTILINE)
        assert len(entries) <= 15, f"{p.name} 累积经验 {len(entries)} 条 > 15"
```

- [ ] **Step 2: 跑绿 + 全量** `python -m pytest src/tests/test_docs_consistency.py -q` → 3 passed。
- [ ] **Step 3: Commit** `test: docs 一致性护栏（审计 C10，无模型断言）`

---

## Phase 4 — E 组 memory 清理（memory 目录在 `/home/jc/.claude/projects/-home-jc-Projects-auto-watcher/memory/`，不在 git 内；HANDOFF/账本改动在 git 内）

### Task 20: E1+E2 过时 memory 清理、260525-1 弃置、HANDOFF 删除

**Files:** Delete: `memory/project_tracker_workaround.md`, `memory/project_ledger_followups.md`, repo `HANDOFF.md`; Modify: `memory/MEMORY.md`, `_pipeline/events.csv`（经代码路径）

- [ ] **Step 1: 260525-1 改 abort**（终态间转换走 update_row，代码路径非裸改）：

```bash
cd /home/jc/Projects/auto-watcher && source src/venv/bin/activate && python -c "
from src.utils import ledger
ledger.update_row('260525', 1, **{'状态': 'abort', '经验提取': ''})
print(ledger.get_row('260525', 1))"
```
Expected: 输出行状态为 abort。

- [ ] **Step 2: 删除 HANDOFF** `git rm HANDOFF.md`。
- [ ] **Step 3: 删除两个 memory 文件**，并从 `MEMORY.md` 移除对应两行索引。
- [ ] **Step 4: Commit（repo 部分）** `chore: 260525-1 弃置为 abort；删除过期 HANDOFF.md（审计 E2）`

### Task 21: E3 人类闸口兜底上移 CLAUDE.md

**Files:** Modify: `CLAUDE.md`; Delete: `memory/feedback_pipeline_human_gates.md`; Modify: `memory/MEMORY.md`, `memory/project_haiku_chinese_corruption.md`

- [ ] **Step 1: CLAUDE.md** — Pipeline Overview 节末尾（`Published posts go to …` 段之前）加：

```
**人类闸口兜底（orchestrator 之外同样生效）**：任何流水线阶段（research/draft/review/revision）
完成后一律停下等用户明示，才可触发下一阶段——即使是在 orchestrator skill 之外临时跑的单个阶段。
```

- [ ] **Step 2: 删除** `feedback_pipeline_human_gates.md`；`MEMORY.md` 移除其索引行；`project_haiku_chinese_corruption.md` 末尾的 `Related: [[feedback-pipeline-human-gates]]` 删除（目标已不存在）。
- [ ] **Step 3: Commit（repo 部分）** `docs: 人类闸口兜底句上移 CLAUDE.md（审计 E3）`

### Task 22: E4+E5+E6 memory 合并与索引重写

**Files:** Modify: `memory/feedback_commit_to_main.md`, `memory/MEMORY.md`, `memory/project_haiku_chinese_corruption.md`; Delete: `memory/feedback_usage_limit_breakpoints.md`

- [ ] **Step 1: 合并** — `feedback_commit_to_main.md` 的 "How to apply" 后追加一段：

```
**长时自主运行的检查点节奏（并入自 usage-limit-breakpoints，2026-07-22）：**
仅当用户已明示授权长时自主工作时，每完成一个单元（每个绿测试步/每个任务）就 commit 并 push，
同步勾掉 docs/superpowers/plans/*.md 的 checkbox——配额可能随时切断会话，小步提交保住断点。
其余场景仍按上文等待明示 go-ahead。
```

- [ ] **Step 2: 命名卫生（E6）** — `feedback_commit_to_main.md` frontmatter `name` 确认为 kebab（`feedback-commit-to-main`）；文内 `[[feedback_env_files]]` 链接对齐该 memory 的实际 `name`（`feedback_env_files`，保持原样即可——链接以 name 为准）；`project_haiku_chinese_corruption.md` frontmatter name 已是 kebab，无改。
- [ ] **Step 3: 删除** `feedback_usage_limit_breakpoints.md`；重写 `MEMORY.md` 为最终态：

```
# Memory Index

## Project
- [project_haiku_chinese_corruption.md](project_haiku_chinese_corruption.md) — Haiku subagents corrupt retyped 简体中文 and self-verify wrong; use command-based replaces + codepoint greps

## Feedback
- [feedback_env_files.md](feedback_env_files.md) — Never commit .env files; verify .gitignore before rename/move ops
- [feedback_commit_to_main.md](feedback_commit_to_main.md) — Solo repo: commit/push directly to main; 授权的长时自主运行按检查点节奏小步提交
```

- [ ] **Step 4: 验证** `ls memory/*.md | wc -l` → 4（MEMORY.md + 3 条）。memory 不在 git，无 commit；在对话汇报中说明。

---

## Self-Review 结论

- 审计批注逐条对照：A1→T1，A2→T2，A3→T3，路径→T4，B1→T6，B2/B3→T5，B4→T7，B5→T8，B6→T9，B7→无动作（裁定保留分层），C1→T11，C2→T13，C3→T10，C4→T15，C5→T17，C6→T14，C7→T12+T9（template 放宽），C8→T18，C9→T16，C10→T19，D→本计划外（裁定 BC 后再看），E1/E2→T20，E3→T21，E4/E5/E6→T22。无遗漏。
- 类型一致性：`lint_warnings` 签名保持 `(content) -> list[str]`；`crosscheck_research` 返回 (violations, warnings) 二元组；`POSTS`/`SOURCE_DRAFTS` 均为 `src.utils.pipeline` 模块常量，测试以 monkeypatch 注入。
- 占位符扫描：无 TBD/TODO；prose 替换均给出全文。
