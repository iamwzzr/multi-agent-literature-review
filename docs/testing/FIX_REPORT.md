# 缺陷修复与复测报告（2026-11-14）

这是在原始固定论文和固定题目上进行的分轮修复。原始失败记录、后续误判和预算不足结果均保留；下方矩阵选用每题最新的相关版本结果，不冒充一次性七题全通过，也不作为稳定性统计。

**结论：工程缺陷已修复并有自动回归保护；整体验收仍不能宣布完成。G01–G04保留了真实通过案例，G06/G07按预期返回资料不足；G05最新结果仍有事实支持警告，最终门禁离线重验证已将其拒绝，需继续修订与独立复核。**

## Git 与验证范围

- 分支：`fix/corpus-acceptance`。
- 修复前材料检查点：`6e1bece`；核心修复：`c36e263`。最终代码指纹见 fix-results-summary.json。
- 7篇论文、3篇固定集、PDF SHA-256 和 cases.json 的问题及标准未更改。补充了用户提供题录 sidecar；题录不升级身份核验状态。
- 相同模型 deepseek-v4-pro、reasoning_effort=none、max_tokens=4000；每题仍最多24次模型、100次工具、300秒、1批反馈。没有提高预算或取消审核门禁。
- Python 3.12.10 / macOS；完整后端测试89项全部通过，pip check通过。Python 3.14未复测。

## 修复内容

| 缺陷 | 实现与验证 |
|---|---|
| T01 中文首轮空召回 | 研究术语的有限中英对照，保留原问题；Researcher 可生成英文查询。两道纯中文探针均不再为空。不是通用机器翻译。 |
| T02 单篇占满结果 | BM25 结果按文献轮转，支持 document_ids 范围；比较探针能覆盖三篇。但严格指定页码仍有漏召回。 |
| T03 工具循环/交付预算 | 4轮 Researcher、2轮 Reporter/Reviewer 后移除普通工具，仍要求模型交付严格结构；记录工具名、参数摘要/哈希、重复与状态。相同时间/调用总预算下完成收尾。审核批次从至多3条改为至多6条，仍服从上下文长度且逐条核对所有ID。 |
| T04 跨页与限制说明 | 重读原文并附相邻页原文窗口；所有 Reporter 限制说明转成带ID的审核主张。FLARE固定题已正确引用第4、5页。 |
| T05 无关材料被当错误 | 增加 insufficient_evidence / execution_error；保留真正故障的错误路径。对无证据只公开范围明确的程序说明，未审模型备注单独保留。 |
| T06 书目信息不足 | 可选 .metadata.json 与PDF哈希绑定；题录更新刷新索引；仍为用户提供、identity unresolved，不能伪称verified。 |
| 新增比较检查 | 所有审核批次可见比较上下文；对声称数据集不相交却存在共同命名条件的主张生成程序级blocking问题；对不完整阅读与整篇否定的冲突拦截。 |
| 输出与旧审核 | 按请求约束主张数/比较行数；未要求表格时不额外扩张；新草稿清空旧审核，预算停止不会带着旧版本pass。 |

最后新增审核门禁：IssueDraft将问题分类为factual/citation/scope/comparison/style；只有style可保留warning，其余warning自动升级blocking。用G05最新真实记录作离线重验证，得到2条blocking、delivery_allowed=False。该门禁通过自动测试和离线回放验证，没有在最终门禁版本上再次付费运行全部问题。

新增表格风险：一次G05把FLARE表2的StrategyQA 68.6与ASQA 41.3当同列比较。该次虽模型门禁pass，独立核查判为错误，完整保留。现在机制/可比条件问题禁止擅自加入EM/F1等性能得分，并发出blocking问题要求改写；这不等于解决任意复杂PDF表格的量化比较，后者仍需保留布局的表格解析与专门验收。

## 最新相关结果

| 题 | 修复前状态 | 最新状态 | 模型调用 | token | 来源运行 |
|---|---|---|---:|---:|---|
| G01 | completed | completed / passed | 7 | 51,299 | 20261114T080828Z |
| G02 | partial | completed / passed | 8 | 75,584 | 20261114T080828Z |
| G03 | partial | completed / passed | 8 | 74,751 | 20261114T080828Z |
| G04 | completed | completed / passed | 8 | 108,690 | 20261114T082641Z |
| G05 | blocked | 历史completed/pass；新门禁离线拒绝 | 15 | 251,576 | 20261114T083620Z |
| G06 | blocked | blocked / no_evidence | 5 | 147,151 | 20261114T082641Z |
| G07 | failed | blocked / no_evidence | 5 | 77,925 | 20261114T082641Z |

G06/G07 的 blocked/no_evidence 是预期的资料不足行为，不能计作“综述审核通过”。G01–G03来自首轮修复，后续主要修改比较审核与资料不足展示，未对这些题重复付费；G04–G07采用各自最后受影响的定向运行。

独立内容核查由 Codex 回读原文完成，不是人类盲标。每题原始请求、完整流、审核、版本、原文引用和工具日志均留在 data/manual-test-results/。

- G01：两种边缘化机制正确，引用 PDF 第3页；没有逐 token 重新发起检索的错误。 run_id=`0646326d-7309-460e-ba1d-2646c5b78066`。
- G02：区分检索/批判 token 与训练/推理阶段，无需独立推理 critic；已回读支持段落。 run_id=`a2080ec2-6bb1-4137-a47f-147be0a219ef`。
- G03：引用 PDF 第4、5页，包含屏蔽低置信词与生成问题，消除了原先的跨页误读。 run_id=`e9248aa1-2dcc-4c76-9be7-bbb2150eb4bb`。
- G04：三篇各有直接证据；只输出一行比较，区分 RAG-Token 文档边缘化与重新检索。 run_id=`2eca4265-7614-46f4-8e7d-b567bb986144`。
- G05：最新真实运行虽模型pass，但留下两条事实支持警告（FLARE模型名的引用覆盖、RAG基线范围的“仅”限定）。不计为质量通过；最终代码将事实警告升级blocking，离线重验证已拒绝这份原报告，原始运行不改写。 run_id=`9e46b2d9-1ec3-40f1-906f-a6b8735f6b1c`。
- G06：blocked/no_evidence 是预期的资料不足结果，不是预算停止；不显示未经审核的整篇否定，不编造人民币成本。 run_id=`03ac956c-9f99-4a39-a78e-8f30d44e19e6`。
- G07：blocked/no_evidence 是预期的材料不相关结果，不再 AGENT_FAILED，不编造物理实验数据。 run_id=`c0c1a51a-97ca-4f83-8b36-a14b37f0fff4`。

## 所有修复轮次与未隐藏的失败

| 轮次（UTC） | 结果 |
|---|---|
| 20261114T080828Z | G01: completed；G02: completed；G03: completed；G04: completed；G05: completed；G06: blocked；G07: blocked |
| 20261114T081546Z | G05: partial |
| 20261114T082150Z | G04: partial；G05: completed |
| 20261114T082641Z | G04: completed；G05: completed；G06: blocked；G07: blocked |
| 20261114T083241Z | G05: partial |
| 20261114T083620Z | G05: completed |

- 080828：五道后端pass中，G05在独立回读中仍有“任务互不重叠”等错误，因此没有直接结束修复。
- 081546：补全跨行上下文后G05仍partial，24次调用耗尽，旧审核和新草稿版本不一致。后续修复了旧审核展示。
- 082150：G04因审核及返工开销partial；G05虽后端pass，整篇范围否定仍不严谨，继续添加程序检查。
- 082641：G04已一行表格并pass；G05又出现未请求的表格分数错列，独立核查拒绝将其计为质量通过。G06/G07为预期的无证据结果。
- 083241：G05移除了未请求得分，但Reviewer因Bio/ARC等源标签的全称问题要求返工，最终partial/revise；没有将其改记为通过。
- 083620：澄清保留原文标签不等于声称其全称后，再次定向检查G05。未降低事实支持、引用与来源范围门禁。

## 仍保留的限制

严格首轮检索探针从3/6变为4/6。R04可覆盖三篇但FLARE的指定第4页仍未进top-6；R05召回Self-RAG第3页而不是冻结标准的第1/4页。没有改页码标准制造通过。需要精确召回时可按文档范围补检索、读取邻页；通用跨语言召回与排序仍有优化空间。

程序检查只对可识别的矛盾和约束生效，不是科学真伪证明。不同数据集名称别名、表格列结构、模型误判等仍需人工抽查。没有完整前端浏览器验收、完整online/hybrid综述、Python3.14复测、单模型对照或多次稳定性统计。

## 复现与计量

89项自动测试的原始XML：data/manual-test-results/pytest-after-fixes.xml。修复前离线行为从检查点6e1bece重建，路径 baseline-replay-6e1bece；这是新的离线重放，不是伪造首次日志。修复后离线原始结果为corpus-offline/results.json，18项HTTP管道和10项锚点检查通过。事实警告重验证见factual-warning-replay.json。

最新选取的七题累计后端记录：{'model_calls': 56, 'tool_calls': 159, 'tokens': 786976}。全部修复轮次累计：{'model_calls': 190, 'tool_calls': 524, 'tokens': 2738321}。失败和诊断重跑已纳入，未核对供应商账单，不换算费用。

可共享文件：本报告、机器汇总、测试题、论文下载说明与测试脚本。论文、原文日志、SQLite、.env均被Git忽略。
