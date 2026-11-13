# 后端测试与引用修复记录（2026-11-14）

负责人：周芯豪。测试项目：D:\AgentRe。仅修改后端、后端测试、验收工具与文档；未修改前端。

## 结论与边界

已修复报告正文、比较表中内部 evidence ID 直接泄露的问题。已有审计对象保留原始 ID，展示文本转换为前端现有协议 `[[1]]`、`[[2]]`，对应实际证据、具体文档与 PDF 页码。

自动测试与真实模型验收分别记录。真实任务的流式响应结束，不代表审核通过。低预算样例中的 partial/blocked 不写成报告质量通过。

## 已完成的代码修复

- 后端统一转换单方括号、双方括号、同括号多个 ID、裸 ID 和反引号 ID。
- 引用编号统一分配；已在句内引用的证据不再重复追加同一段末编号。
- 正文、适用范围、比较表单元格和条件中的引用必须属于已登记证据，且关联到该主张/比较行；未知 ID 在审核前拦截。
- 模型不得自行分配展示用数字编号，避免与程序映射冲突。
- 比较行的未知值显示为“未知（未报告）”，不展示 Python None；结构化 null 不改写。
- 展示修改不覆盖原始报告草稿、证据快照或审核版本。
- 结构化结果兼容经过严格 Pydantic 校验的映射；普通文字返回后的重试移除研究工具，只整理已取得材料。
- 补充聚焦问题、减少重复取证的 Agent 提示；不降低审核通过要求。
- 本地验收记录目录加入 Git 忽略规则，避免提交论文摘录。

## 自动回归

命令：

```powershell
cd D:\AgentRe
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

最终代码回归：69 passed，13 个来自 LangSmith 的 Python 弃用警告。依赖检查 `python -m pip check` 无损坏依赖。

本次新增 16 项测试，覆盖引用形式转换、未知引用/未关联引用拦截、原始审计保留、空值展示、空资料、非法上传、原文篡改、结构化映射和无研究工具的格式恢复。

既有测试还覆盖本地联网限制、定向返工、预算、身份冲突、错误 PDF、审核版本过期、项目隔离、断开连接与并发记录写入。这些固定样例属于模拟/自动化测试，不等同于真实外部服务验收。

## 原始用户报告回放

运行 ID：`727f092c-6e20-4f04-879c-8c037f213f5c`。

原始结果为 partial，共 14 条主张；18 个展示段落出现内部 evidence ID。重新渲染后，14 条原始主张保持不变，展示正文不再泄露内部证据 ID；12 条证据的文件哈希与原文位置已检查。回放文件保存在本机 `data/manual-test-results/replayed-report.json`。回放没有修改原始数据库记录，也没有把 partial 改成审核通过。

## 真实 HTTP 验收

可重复入口（调用真实模型，会产生费用）：

```powershell
.\.venv\Scripts\python.exe backend/tools/validate_system.py --live
```

需先启动后端。脚本自动读取本地配置，不打印模型密钥或访问令牌；每项顺序运行。默认每项 18 次模型调用、300 秒、1 批返工，适合测试有限预算下的交付行为，不保证每项生成最终审核通过的报告。

检查内容：健康检查、非法 PDF/Content-Type、无效目录、不存在的运行、真实 TCP 取消和同项目重试、证据不足、比较条件、在线检索、混合补证、上传 ID 生成、跨项目隔离、预算停止、引用编号范围、PDF 获取、审核版本一致性。

第一轮记录：`data/manual-test-results/20261114-012834/`。

- 比较任务出现一次 AGENT_SCHEMA_INVALID，已修复并复测。
- 本地、联网、混合、上传样例正常结束但为 partial；预算样例为 blocked。
- 联网实际取得 RAG 的 arXiv 权威身份记录并使用对应 PDF。
- 混合实际触发在线补证查询。候选身份通过不代表相关性或文档对应检查通过；不能据此声称所有在线候选都进入了最终证据。

第二轮记录：`data/manual-test-results/20261114-013705/`。具体每项最终状态、审核结论、调用数、耗时见同目录 summary.json；每个样例 JSON 保留请求、流事件和完整运行记录。

## 人工与离线检查

- 证据不足样例明确保留人民币成本未知，未进行货币换算或成本估算。
- 比较样例保留不同模型、数据集与指标等限制，不应将不同实验直接做全面排名。
- 引用存在性、哈希、页码由本机重新解析实际 PDF 检查；汇总见 `data/manual-test-results/original-verification.json`。
- 上述定位一致不代表所有语义推论都正确；partial 草稿仍需要人工审核，尤其是跨论文比较和“未报告”的范围。
- 本轮通过真实 HTTP/TCP 验证接口与取消行为，没有把程序化测试写成已亲自点击浏览器全部控件。前端点击引用后的视觉行为仍可由团队在页面抽查。

## 如何查看修复

后端重新加载后，新建对话生成新结果。前端已经缓存的历史文字不会被后端代码自动替换；原始审计记录也不会静默改写。页面应显示数字引用，点击后由现有前端定位证据及 PDF。

本文件记录测试时的本地状态；提交与推送版本以 Git 历史为准。

## 最终复测结果

第二轮六项真实 HTTP 样例均通过执行及引用格式检查；比较任务未再出现 AGENT_SCHEMA_INVALID。上传任务的一次普通文字返回触发格式恢复，成功进入 Reviewer。

- comparison：task_status=partial，verdict=None，模型调用 18，61.6 秒；run_id=85c949de-29d5-400c-8192-f179d0ce927d。
- upload：task_status=partial，verdict=undetermined，模型调用 18，70.7 秒；run_id=1b50b051-964b-4fe1-9b2b-1831be49ef88。
- insufficient：task_status=partial，verdict=None，模型调用 18，68.7 秒；run_id=538f2547-e720-48c4-8199-07fde98ed366。
- online：task_status=partial，verdict=None，模型调用 18，78.5 秒；run_id=13793ccf-3970-455e-8131-255a7e4ebcc3。
- hybrid：task_status=partial，verdict=None，模型调用 18，88.4 秒；run_id=9c43de08-98f5-4071-b554-f0c6bc74585b。
- budget：task_status=blocked，verdict=None，模型调用 1，3.8 秒；run_id=ab1c55df-526a-4bed-9bd6-4e656a7f795c。

离线重读原始 PDF：检查 12 次有报告的运行，共 38 条展示引用（包含跨运行重复引用），文件哈希、页码和摘录均匹配；涉及 2 份不同的实际 PDF。原用户报告另有 12 条证据的回放检查。

### 正常预算下的真实审核通过样例

运行 ID：`6be48e50-ab9e-4cad-8c6a-41a2a71301f9`。上传 RAG PDF，知识库目录为空，只问一条窄范围检索机制问题。

结果：task_status=completed，verification=passed，Reviewer status=success/verdict=pass；无未检查主张、无审核问题；报告版本和证据快照与审核一致。实际模型调用 6 次、工具调用 9 次、总 token 33,262。

该结果证明单条主张的真实三 Agent 端到端路径已通过，不代表复杂的多论文比较报告均已审核通过。低预算复杂任务仍有重复补证与成本方面的改进空间。

正向样例原始记录：`data/manual-test-results/single-claim-acceptance.json`。可读报告：`data/manual-test-results/single-claim-report.md`。原用户报告的引用修正版：`data/manual-test-results/replayed-report.md`。
