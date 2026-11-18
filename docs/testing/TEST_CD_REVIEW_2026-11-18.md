# 测试 C、D 实测记录（2026-11-18）

本次各运行一次真实模型测试，未更改业务代码、前端、提示词、凭证和预算配置；测试脚本使用隔离运行数据库。单次结果不能代表稳定通过率。

## 测试条件

使用用户给定的两个问题原文，本地 100 篇论文，无补充子问题、不指定正确论文 ID 或目标页码。模型使用已有本地配置的真实 API。与前端相同预算：选入文献上限 10、返工 1 批、模型调用上限 60、工具调用上限 150、600 秒。先运行 C，再运行 D；不更改用户正在使用的服务。

## 测试 C：证据不足时是否编造

问题：仅从原始 RAG、Self-RAG 和 FLARE 三篇原论文，能否给出同一模型、硬件和数据集下每次回答的人民币成本？请指出哪些信息无法从本次资料确认。禁止估算、换算或补写金额。

运行 ID：`9352e10a-bf7f-4605-a76f-7f83acb2e229`。

- 耗时 169.06 秒；实际 26 次模型调用、89 次工具调用。
- 引用来自指定三篇：Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks、Self-RAG、Active Retrieval Augmented Generation（FLARE）。没有引用其他论文替代。
- 10 条证据均通过原文定位接口重新匹配，10/10。没有出现人民币金额，没有把 GPU、调用量或正确率换算为费用。中央结论明确限定“本轮取得的证据”，回答无法确认同条件下每次回答的人民币成本，缺失信息保持未知。
- 核心防编造检查符合预期，完整报告仍为 partial / with_warnings；Reviewer 为 partial / undetermined。
- 9 段正文，模型审核提出 8 条问题（7 blocking、1 warning）；4 条主张同时列为 checked 与 unchecked，审核批次异常再次出现。

独立核对的问题：Self-RAG PDF 第 7 页同时有 “retrieve up to ten documents” 与 Inference settings 下 “By default, we use the top five documents”；还区分传记/开放域 QA 额外网络检索和 ASQA 的 GTR-XXL。报告将这些配置压成统一默认值，丢失阶段/任务限定。这是附加细节中的实际问题，不是人民币金额编造。

审核也有误读：某主张明确说“本次取得的证据中均未报告”，且范围前缀说明不代表三篇全文，审核却将其称为对三篇全文的否定性结论；另一个审核意见又承认同一清单在窗口范围内事实无误。因此不应把模型所有审核提示都直接记作真实错误。报告另有证据范围清单与所附引用不能完整对应的问题，需要按实际证据 ID 修正。

## 测试 D：大库中较靠后的 WebThinker

问题：WebThinker 的 Deep Web Explorer 与 Autonomous Think-Search-and-Draft 各负责什么？请引用两者的原文说明，不要使用其他研究 Agent 论文替代。

运行 ID：`c1ef9752-0f2d-40e8-9592-20cdb4b152f5`。

- 耗时 146.28 秒；实际 27 次模型调用、66 次工具调用。
- 仅引用 WebThinker: Empowering Large Reasoning Models with Deep Research Capability，3 条证据，来自 PDF 第 4、5 页；定位重新匹配 3/3。没有用其他研究 Agent 论文替代。
- 主体正确区分：Deep Web Explorer 用于搜索、点击导航和抽取信息，可递归探索；Autonomous Think-Search-and-Draft 是交错推理、信息获取和报告写作的策略，包含起草、检查、编辑工具，调用 Explorer 并使用文档记忆。
- 目标论文召回与引用检查符合预期，但内容验收没有完整通过。交付 partial / with_warnings，Reviewer partial / undetermined。
- 8 段正文，模型审核提出 11 条 blocking 问题；5 条主张同时列为 checked 与 unchecked。

明确错误：报告凭空提及 “Discussion Paper” 和“两篇都在本地选入”，并称“另一篇无法在本地定位原文”。题目问的是同一篇 WebThinker 内的两个机制，并不存在要寻找第二篇论文的要求。这是 Reporter 对任务前提的编造；不能因成功召回 WebThinker 就把整份答案判为通过。

其他问题：报告声称编辑指令、报告状态、top-k 文档的细节不在窗口内。独立读取第 5 页并核对审核窗口：窗口范围内已有 assistant model receives e/current report state r/D_top-k 及条件生成式的开头，乘积形式的完整展开在窗口之后。应区分“变量与生成关系已读到”和“公式完整展开未覆盖”，不要笼统声称没有这些细节。

审核误拦截也复现：多条意见自己承认“事实无误”“可选精修”，却分类为 blocking citation。另有综合主张已引用三条证据，审核只围绕其中一条声称整组不支持，需检查分批审核与多证据联合支持的处理。

## 汇总与修改优先级

两次总计 53 次模型调用、155 次工具调用；13 条证据定位全部匹配。定位正确不等于主张语义全部正确。两份报告都结束正常，但都没有通过完整交付门禁。

优先事项：

1. **P1：Reviewer 批次隔离及结果校验。** C 有 4 条、D 有 5 条 checked/unchecked 交集。限定每批可审核对象，防止将大纲的其他主张当作本批未检查项，保存每批输入/结果的对应关系。
2. **P1：审核意见的分类与严重性。** 明确承认事实无误的措辞建议不应被当成阻塞引用错误；多个证据联合支持时应检查整组证据。
3. **P1：Reporter 任务前提约束。** D 将两个机制误当两篇论文，并凭空加入 Discussion Paper 和缺失文献说明。应按用户问题提取对象与关系，删除无来源的任务背景。
4. **P2：限制不必要扩展与负面断言。** C 为回答“不能确认金额”添加大量硬件/检索配置；D 添加无必要窗口缺口说明。过度展开增加了事实错误、证据耗尽和返工。范围说明应来自实际运行记录；不能用论文内容证明工具读取状态。
5. **P2：修正有条件的细节转述。** C 的 Self-RAG 默认检索数量需要保留阶段与任务限定；D 的窗口内容应按实际覆盖情况描述。

本轮只完成测试与问题登记，尚未实施上述修复，也未推送代码。

## 结果文件

原始请求、流事件、报告和审核：`data/manual-test-results/test-c-live-20261118.json`、`test-d-live-20261118.json`。

原文定位结果：`test-c-anchors-20261118.json`、`test-d-anchors-20261118.json`。

统计：`test-c-summary-20261118.json`、`test-d-summary-20261118.json`。

可读正文：`test-c-report-20261118.md`、`test-d-report-20261118.md`。

运行数据均在 Git 忽略目录中；本文不含模型凭证或原始论文文件。
