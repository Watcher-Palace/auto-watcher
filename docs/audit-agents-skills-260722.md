# Agents / Skills 审计底稿（2026-07-22）

**范围**：`.claude/agents/`（blog-researcher / blog-writer / blog-reviewer）、`.claude/skills/`（blog-orchestrate / blog-curate / blog-summarize）、`source/_drafts/template.md`、`CLAUDE.md`，并对照 `src/linter.py`、`src/review_linter.py`、`src/publisher.py` 核实了文档声称的代码行为。
**用法**：每条末尾的 `处理：` 留给人写裁定（建议词汇：修复 / 保留现状 / 搁置 / 改为…）。行号为 2026-07-22 快照，写手文件（git 状态 M）后续变动会使行号漂移。

**总览**：冲突 3 · 重复 7 · 脚本化建议 10 · 篇幅观察 1 · Memory 对账 6（E 组，2026-07-22 批注后追加）· 免查项见附录。

---

## A. 冲突（互相矛盾或已过时，建议全部修复）

### A1. 评审文件"人类节"名称不一致（最高优先）

- **现状**：`blog-writer.md:87` 要求用户裁定原文留在 **`## 人类的裁定`** 节；其余所有地方均叫 **`## 人类意见`**——同文件 `blog-writer.md:48`、`blog-reviewer.md:63`、`blog-orchestrate/SKILL.md:197`、`blog-curate/SKILL.md:33`、`CLAUDE.md:122`、`src/review_linter.py:40`（注释）。
- **影响**：写手按 87 行的名字找节找不到，或另建一个新节，破坏"裁定永久留痕"约定。
- **建议**：统一为 `## 人类意见`（多数派 + linter 注释用法），改 `blog-writer.md:87` 一处即可。
- 处理：同意

### A2. blog-summarize 的模型说明已过时

- **现状**：`blog-summarize/SKILL.md:23` 写 "(matches the repo convention: research=Haiku, write/review=Sonnet)"。研究 agent 早已钉 Sonnet（`blog-researcher.md:5`；`CLAUDE.md` 明言 Haiku 只存活于 tracker 过滤）。
- **影响**：动作本身（派 Sonnet）没错，但陈旧理由正是 CLAUDE.md anti-drift 条款要清除的对象；后续读者可能据此误判仓库惯例。
- **建议**：删掉括号内那句，或改为 "(all pipeline subagents run on Sonnet)"。
- 处理：删除括号

### A3. orchestrate 中的行号引用已漂移

- **现状**：`blog-orchestrate/SKILL.md:163-165` 引用 `blog-writer.md:46`（实际规则在 48 行）与 `blog-writer.md:78`（实际在 87 行）；`SKILL.md:198` 再次引用 `blog-writer.md:78`。同段引用的 `publisher.py:116` 目前仍准确。
- **影响**：writer 是 curate 最常改动的文件，行号锚点必然持续漂移，引用会指向无关规则。
- **建议**：行号锚点改为规则名/节名锚点（如 "blog-writer《不许删 review 文件里的 [USER] 注释》条"）；`publisher.py:116` 属代码引用、相对稳定，可保留但同样建议附函数名。
- 处理：同意

---

## B. 重复（同一规则多处成文，漂移风险按严重度排序）

### B1. researcher ↔ writer 四条长规则近乎逐字双份

| 规则 | researcher | writer |
|---|---|---|
| 转发帖不作来源/不进文章 | :83 | :83 |
| 转引自媒体≠独立信源（含"四海瞭望→新唐人"整段反例） | :84 | :84 |
| 记者必须带媒体归属（大江新闻/南都湾财社例） | :85 | :81 |
| 评论禁令 + 加害言论例外句 | :82 | :82 |

- **说明**：双侧成文有分工理由（研究管入库、写手管入稿），规则本身建议两侧都留；但反例叙事整段×2 没有必要。
- **建议**：每侧留"规则 + 一行最短反例"，完整错误链条只留一处（或移入 curate 的沉淀记录）。
- 处理：同意，移入记录

### B2. 评论禁令例外句共四份

- **现状**："该言论本身就是事件的加害行为或被追责对象……"整句出现于 `blog-researcher.md:82`、`blog-writer.md:82`、`blog-reviewer.md:29`、`template.md:61-63`。
- **影响**：将来调整例外范围需同步四处，漏一处即产生新冲突。
- **建议**：定一处为 canonical（template 或 writer），其余三处压缩为一句引用式提示。
- 处理：template

### B3. template.md"风格硬规则"块与 writer Style Rules 重复，且与 CLAUDE.md 分工冲突

- **现状**：`template.md:59-63` 注释块含破折号禁令、填充语禁令、no-inference、评论禁令——全部与 `blog-writer.md` Style Rules 重复。按 `CLAUDE.md` 自己的分工（格式→template；style/no-inference 判断规则→writer），这块放错了位置。
- **功能性理由（收敛前需先裁决）**：reviewer 只读 template 不读 writer 文件，靠这块才能把风格违规当 `类型：格式` 检查。收敛方向二选一：①风格规则单一归 writer，reviewer 文件补一行"风格硬规则见 blog-writer"；②承认 template 为风格规则 canonical，writer 侧压缩。
- 处理：②给template

### B4. researcher 文件内部重复

- **现状**："sources 可能挂错"告诫 + 260707-2 湖北龙卷风反例，在 Your Inputs（`blog-researcher.md:22-26`）与 Step 0（`:41-47`）讲了两遍。
- **建议**：Your Inputs 处压缩为一句 + 指向 Step 0。
- 处理：同意

### B5. "批量 ≤3 派发"规则四份

- **现状**：`blog-orchestrate/SKILL.md:119`、`:136`、`:290` 三处 + `CLAUDE.md` 一处，均带 "(user directive 2026-07-20)"。
- **建议**：orchestrate 内留一处（Notes 节），其余两处删；CLAUDE.md 那份作为全局概览可留。
- 处理：同意

### B6. summarize 的 N 档速记与 writer 定义不符

- **现状**：`blog-summarize/SKILL.md:198` 把 N 写成"中立事件/**等待后续**"；`blog-writer.md:103` 的 N 定义三条里没有"等待后续"——那是 `PING` 的语义。
- **建议**：改为"中立事件（存疑/已获公正解决/相关性不确定）"。
- 处理：部分同意，N有时候是为了让等待后续的文章通过格式检测，改为“中立事件（存疑/已获公正解决/相关性不确定）/等待后续”

### B7. CLAUDE.md Stage Details ↔ orchestrate 大面积平行文本（记录在案，不建议动）

- **现状**：两者是仓库里最大的一对同构文本（概览 vs 运行手册），当前内容一致、无冲突。
- **建议**：不收敛（分层有意为之），但明确"改流程必须双改"的义务；可考虑 C 组第 10 项的一致性测试覆盖关键同步点。
- 处理：同意

---

## C. 脚本化建议（把机器可判定的 prose 规则固化为代码）

背景：草稿有 `linter.py`、评审有 `review_linter.py`，**initial 研究文件完全没有机械闸口**；而文档标注"复发率最高"的返工类别多数是确定性可查的。blog-curate 自身原则即 "Prefer code over prose"——每落地一条，对应 prose 可缩成一行"linter 会拦"，同时缓解 D 组篇幅问题。

### 第一梯队（直接砍掉最高复发的返工）

**C1. 草稿 ↔ 研究文件交叉对账（`linter.py` 加 `--research <path>` 模式）**
- 来源行对账：草稿每条来源 URL 必须在研究文件 `## 信息来源` 存在，日期、斜体标题与研究行一致。动因：`blog-writer.md:75` 自述"这一节被评审逐条推翻返工过多轮，是格式问题里复发率最高的一类"。
- 称呼回查：草稿所有 `X某/X某某/X女士/小X` 代称及带 `（化名）` 标记的名字，必须在研究文件逐字存在。动因：二次化名 2026-07-21 一天复发两次（260716-8、260716-7）。
- 处理：同意对账，称呼降为warning（有时无可用现存化名，必须自己取）

**C2. 新建 `src/research_linter.py`（研究文件闸口，对称于写手 lint gate）**
- 检查：四必需节齐全（事实/当事方/信息来源/资产）；来源行格式 `- YYYY.MM.DD，来源。*标题*。URL — 摘录`（允许"（发布日期查证失败）"标记）；恰好一处蓝字、句内含日期、不含"暂无进展/尚未"类措辞；`## 资产` 登记 ↔ assets 目录双向对账（含"含身份信息"标记格式）。
- 动因：研究是上游，缺日期/缺标题的来源行直接导致写手停工返工。
- 处理：同意

**C3. `linter.py` 补四条小规则**（各对应一次已记录的用户纠正）
| 规则 | 检查 | 级别 | 出处 |
|---|---|---|---|
| 标题 ≠ 内部标签 | frontmatter `title` 与文件名 slug 相等 → FAIL | FAIL | 2026-07-22 多次复现 |
| 标题舆论反应词 | 标题含"引争议/引质疑/引发关注/惹众怒" → WARN（"争议即事件主体"例外留人裁） | WARN | 2026-07-21 |
| 填充语黑名单 | 正文含"此事沉寂数月后/引发广泛关注/网友纷纷表示"等 | FAIL | template+writer 双份 prose |
| 蓝字唯一性 | 恰好一处蓝字且不含"暂无进展"类句子 | FAIL | researcher/reviewer/template 三份 prose |
- 处理：部分同意，例如引起关注/网络舆论有时在舆论事件中避免不了

### 第二梯队（流程运维负担）

**C4. `pipeline_cli.py ping-due`** — 列出挂 `PING` 且已满一个月的已发布文章（`blog-writer.md:143` 的巡检流程目前无工具支撑）。
- 处理：同意

**C5. `src/publish_summary.py YYMM`** — 固化 blog-summarize Stage B 的 cp → build → deploy 三连（CLAUDE.md 明示"跳过 build 静默发陈旧内容"是已知坑）。
- 处理：同意

**C6. review_linter 默认模式补一条** — 草稿每个 `<!-- [TAG-PROPOSAL] -->` 必须出现在评审 `## 标签提案` 节（reviewer 职责第 7 条本是纯转录；默认模式已推导同版草稿路径，成本低）。
- 处理：同意

**C7. 结构细则入 linter** — `#### 时间线` 块内禁再出现子标题；`## 前情`/`## 后续` 每行须含站内 `参见：[...](/...)` 链接。
- 处理：不同意时间线，时间线内可以有子标题，但不能拆分过度。同意前情后续。

### 第三梯队（辅助工具，非闸口）

**C8. `src/imgfetch.py <url> <dest> [--referer]`** — 封装带 Referer 的下载 + MIME/大小校验，替代 `blog-researcher.md:93` 教子代理手写 curl 防占位图的流程。
- 处理：同意

**C9. `pipeline_cli.py dedup <关键词>...`** — 同案查重的机械扫描（`source/_posts/` + 在途账本 + 研究文件）一条命令出结果，判断仍归研究员。动因：同一案件曾以四个标题被收录、整轮作废。
- 处理：同意

**C10. `src/tests/test_docs_consistency.py`** — 把本次审计固化为 CI 测试：全仓仅允许 `## 人类意见` 一种写法；各 agent `累积经验` ≤15 条；agent 文件 ≤180 行；三个 agent 均 `model: sonnet`。
- 处理：除模型确认sonnet以外同意，模型后续可能改

### 不建议脚本化（保持 prose）

评论禁令的边界判断（加害言论例外）、A/B 判级、转引自媒体的识别、no-inference——判断规则，正则只会用假阴性制造假自信。

---

## D. 篇幅观察

| 文件 | 行数 | 大小 | 评估 |
|---|---|---|---|
| blog-writer.md | 151 | 22.9KB | 未超 curate ~180 行阈值，但字节最重 |
| blog-researcher.md | 148 | 14.3KB | 接近阈值，含 B4 内部重复 |
| blog-orchestrate | 291 | — | 最长 skill，删重复（B5 等）可压 10–15% |
| blog-reviewer.md | 86 | 6.5KB | 合理 |
| blog-curate | 99 | — | 合理 |
| blog-summarize | 204 | — | 合理（长在嵌入式统计代码，正当） |

writer 的重不在行数在密度：多条规则是"规则 + 两三个案例名 + 完整错误链条复述"。curate 对累积经验的要求是 "general principles only — never case names, dates"，而正文规则区恰恰堆满案例名与日期。反例有防合理化价值，不建议全删；建议每条规则保留一个最短反例，长链条复述砍半（与 B1、C 组联动：规则进 linter 后 prose 缩为一行）。

- 处理：BC组完成后再看

---

## E. Memory 对账（memory 目录 ↔ CLAUDE.md/skills/agents，2026-07-22 批注后追加）

依据 CLAUDE.md anti-drift 条款："Auto-memory is for facts *not yet* in the canonical docs; once a fact lands here, in a skill, or in an agent file, the memory should be deleted." 目录：`~/.claude/projects/-home-jc-Projects-auto-watcher/memory/`。

### E1. project_tracker_workaround — 已落入 canonical，应删

- **现状**：手工 brief 流程已完整落入 `blog-orchestrate/SKILL.md:88`（`pipeline_cli.py add` + 手写 events 条目），CLAUDE.md 也登记了 `add` 子命令。memory 的 "How to apply" 还比 skill 版弱（"write a minimal events entry **if needed**"——skill 是必写，账本+events 双落）。
- **建议**：删除该 memory（canonical 已覆盖且更严格）。
- 处理：同意

### E2. project_ledger_followups — 半陈旧，建议瘦身或结清后删

- **已核实的现状（2026-07-22）**：①重构完成叙事与"events.csv 唯一权威"重复 git 历史与 CLAUDE.md；②"仓库 track 了 10 个 .pyc"已过时（现为 0）；③260325-3 已 2026-07-15 发布结清；④**260525-1 published 行的发布日期/发布标题至今仍为空**（`,260525,1,,published,,,已提取`）——唯一仍待用户裁决的数据项；⑤HANDOFF.md 仍是过期 v1 引导文档（"已接受不修"状态未变）。
- **建议**：memory 瘦身为仅剩 ④⑤ 两个未决项；若本轮顺手裁决 260525-1（补齐或确认弃置），则整条删除。
- 处理：0525-1弃置，handoff删除，整条memory删除

### E3. feedback_pipeline_human_gates — 与 orchestrate 的重叠是兜底设计，去向二选一

- **现状**：no-auto-chain 的 canonical 在 `blog-orchestrate/SKILL.md:36-38`，但 skill 只在被调用时加载；该 memory 自述是"非 orchestrator 场景的兜底"，靠 MEMORY.md 索引行进入每个会话。与 B7 的分层逻辑同源。
- **建议**：①保留现状（索引行已起兜底作用）；或 ②把兜底句上移进 CLAUDE.md（全会话必载、更符合 anti-drift 的单一归宿），然后删除该 memory。倾向 ②，与 B7 裁定（CLAUDE.md 承担兜底层）一致。
- 处理：同意2

### E4. memory ↔ memory 冲突：commit_to_main vs usage_limit_breakpoints

- **现状**：`feedback_commit_to_main`（较旧）说 "Still wait for explicit go-ahead before committing/pushing"；`feedback_usage_limit_breakpoints`（较新）说长时自主工作中 "Commit AND push to main after every completed unit of work"。自主长跑场景下两条互斥，且互链只有单向。
- **建议**：在 usage_limit 条内补一句优先级界定："仅适用于用户已明示授权的长时自主运行；其余场景仍按 commit_to_main 等待明示"，并双向互链。
- 处理：合并为一条，同意优先界定

### E5. MEMORY.md 索引两处失准

- **现状**：①`feedback_usage_limit_breakpoints.md` 不在索引里（7 个文件只列 6 条），违反"每个 memory 一行索引"约定；②`project_ledger_followups` 的索引钩子仍写"260525-1/**260325-3** 发布信息待用户裁决"，而 260325-3 已结清（memory 正文自己已更新，索引没跟上）。
- **建议**：补 usage_limit 索引行；ledger 钩子改为仅 260525-1（若 E2 走整条删除则一并处理）。
- 处理：视E4、E2处理

### E6. 命名/链接卫生（小）

- **现状**：`feedback_pipeline_human_gates.md` 的 frontmatter `name` 是整句英文（"Pipeline is human-gated — never auto-chain stages"），不符合 kebab-slug 约定；`[[feedback-pipeline-human-gates]]`、`[[feedback-commit-to-main]]` 等互链用连字符，实际文件名用下划线，slug 与文件名两套写法并存。
- **建议**：统一 name 为 kebab slug、互链对齐实际 name；顺手即可，不单独排期。
- 处理：同意

### 核查过且无问题的 memory（免复查）

- `project_haiku_chinese_corruption` — canonical 文档无覆盖，保留。注：流水线 subagent 已全 Sonnet，此条只在未来再派廉价模型改中文文件时生效（适用面收窄，不构成删除理由）。
- `feedback_env_files` — 与 CLAUDE.md 互补不重复（CLAUDE.md 只说 .env 位置，泄漏史与操作规程仅在 memory）。
- `feedback_commit_to_main` — 内容本身与仓库文档无冲突（它冲突的是全局默认，这正是其存在意义）；仅涉 E4 的优先级界定。

---

## 附录：核查过且无问题的部分（免复查清单）

- orchestrate 派单字段与三个 agent 的 Your Inputs 完全吻合（initial/update/revision 各模式）。
- 文档声称的 linter 能力全部真实存在：`--check-marks`、`--check-dispositions`（含退出码 2 语义）、罪名标签拦截、资产引用核对、TAG-PROPOSAL 识别。
- 三个 agent 均钉 `model: sonnet`，writer 无 web 工具，与 CLAUDE.md 一致。
- `publisher.py:116` 的引用（[USER]/[REVIEWER]/[WRITER-*] 拦截）目前准确。
- PING/TODO 语义、S–N 分类定义各处一致（除 B6 速记小差）。
- 状态流（candidate → … → published/abort）与人类闸口定义各处一致。
