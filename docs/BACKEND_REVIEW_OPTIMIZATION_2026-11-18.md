# 后端审核与回答范围优化（2026-11-18）

本次只修改后端、后端测试、验收工具及文档。前端源码未改动，尚未提交或推送 GitHub。

## 修复内容

1. 分批审核使用动态 Pydantic 契约：checked、unchecked 必须覆盖本批且互斥、不重复；不接受大纲中其他批次的主张 ID、未知请求 ID 或非法证据 ID。
2. 对审核分类/严重性矛盾的结果要求模型重新判定。例如声称“事实无误”“可选精修”却给 blocking，不能直接接受，也不会由程序擅自降级为通过。仍无效时保留为未完成审核，不能绕过门禁。
3. 每批保存输入、原始返回、无效原因和最终结果，并绑定 batch_id、报告版本、主张 ID 与证据 ID；合并保留错误与未检查项。只有阻塞问题和必要补证进入事实返工。
4. 默认最多四条正文主张、一条可选限制，用户显式 max_claims 仍生效。禁止估算的请求默认两条，强调“本轮证据不足以确认”，减少无关作者机构、GPU、数据集清单与出版信息扩展。
5. 程序向 Agent 提供已取得证据的文献与页码范围；增加单篇研究中两个组件被误当两篇论文的阻塞检查，删除无来源的“另一篇论文”和任务背景。
6. 区分写作者置信标签与程序交付结果：Reporter 的 partial 原样保留。若 Reviewer 成功完整核查、确认原问题已覆盖、无错误/未检查项/阻塞问题，且必要补证、所有引用与版本门禁均通过，可交付一个“证据不足”的完整答案。failed 或存在执行错误绝不通过。此决定保存 completion_decision，报告含 producer_status，不能把任务完成理解为取得了缺失数值。
7. 后端交付对象增加 bibliography：按实际 document_id/版本归组，每组保留所有引用编号、证据 ID、页码和位置。原 evidence 和引用编号保持兼容。前端尚未接入此字段，界面的重复书目信息需由前端队友后续处理。
8. 保存 B/C/D 的原始问题为独立验收样例，不向模型传入 expected、must_not 或标准页码；真实测试工具支持 --case-file、--tool-calls 与每题输出设置。

## 验证结果

最终全部后端测试：**174 passed**，13 条已有 LangSmith/Python 弃用警告，无失败。

新增 16 项用例覆盖越批/重复/遗漏/状态冲突、审核误拦截纠正、失败不得通过、原始记录保留、按版本去重书目、禁止估算策略及用户显式覆盖、对完整证据不足答案的交付判定。最终业务代码测试通过后，仅补充了验收工具参数和样例，工具已检查语法和 --help。

真实测试保留此前基线及中间失败/部分草稿，没有覆盖历史记录。最终结果如下：

- **B：completed / passed**；Reviewer success / pass，0 问题，0 未检查。两篇原论文、5/5 条证据定位匹配；正文 2 段，12 次模型调用，62.72 秒。运行 ID：66e7d59a-8f15-4ffe-be9c-42c5a837961c。
- **C：completed / passed**；Reviewer success / pass，0 问题，0 未检查。限定三篇原论文、5/5 条证据定位匹配；正文 2 段，9 次模型调用，55.82 秒。没有金额编造或估算/换算；结论仍是本轮资料不足以确认人民币成本。写作者 partial 标签保留，独立审核确认问题覆盖后由程序交付。运行 ID：46bfbb10-942e-4757-8731-dbed22a9eb74。
- **D：completed / passed**；Reviewer success / pass，0 问题，0 未检查。仅引用 WebThinker、6/6 条证据定位匹配；正文 4 段，11 次模型调用，66.58 秒。未再出现 Discussion Paper 或第二篇缺失论文。运行 ID：98f85ddf-9daa-402d-8420-4a98cbe043d5。

三题最终各一轮合计 32 次模型调用、16/16 条定位匹配，所有主张的审核版本和证据快照对应，checked/unchecked 交集为零。小样例单次观测不能推出稳定通过率、一般延迟提升或整个 100 篇库的语义准确率；Reviewer 仍可能出错，需要人工抽查。

C 的中间优化运行曾保持 partial：先是过度展开细节，随后是完整审核通过但写作者 partial 标签阻止交付。两者分别通过回答范围策略和明确的交付状态分层处理，而非删除审核问题或给金额填默认值。

## 本地复测

后端全量测试不调用付费模型：

```powershell
cd D:\AgentRe
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

真实 B/C/D 复测会调用已配置的模型 API。先在单独终端启动 `.\start-backend.cmd`，然后在第三个终端运行：

```powershell
cd D:\AgentRe
.\.venv\Scripts\python.exe -X utf8 backend/tools/test_corpus_live.py --live --suite corpus-100 --case-file docs/testing/manual-regression-cases.json --cases B,C,D --model-calls 60 --tool-calls 150 --seconds 600 --project-id manual-bcd-regression --base-url http://127.0.0.1:35549
```

工具的结构检查通过不自动等于人工语义验收，仍要查看最终 task_status、审核状态、问题、引用与原文。新运行结果会单独保存。

前端手动复测：在后端终端 Ctrl+C 后重启 `.\start-backend.cmd`，保持前端运行；选择本地模式、知识库 `D:\AgentRe\data\papers-100`，新建对话重新提交 B/C/D。旧报告不会被本次修改重写。

## 文件与接口

- reviewing.py：动态批次契约、保守失败结果、结果合并。
- contracts.py：输出篇幅与交付条件。
- context.py：批次边界与稳定证据顺序。
- engine.py：运行范围、按批审核/审计、定向返工、交付决定。
- presentation.py：任务前提检查、按版本归组书目。
- agents.py：任务范围、可选建议、证据不足与联合引证准则。
- test_review_boundaries.py：新增回归用例。

运行产物在 Git 忽略的 data/manual-test-results 下：bcd-optimized-summary-20261118.json、test-b-optimized-20261118.json、test-c-optimized-reviewed-20261118.json、test-d-optimized-20261118.json。另有 test-b/c/d-optimized-report-20261118.md 可读返回。
