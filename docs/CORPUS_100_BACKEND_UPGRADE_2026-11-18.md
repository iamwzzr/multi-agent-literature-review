# 100 篇论文下载、后端修复与功能验收（2026-11-18）

## 范围和当前结论

本轮在 D:\AgentRe 下载并校验固定版本的 100 篇公开论文，修复后端问题，完成离线和真实模型功能测试。没有修改前端源码，没有自动提交或推送代码，论文和密钥不进入 Git。

真实模型使用用户已授权的个人 API；具体凭据仅在本地 .env。学校密钥未用于最终验收。所有最终状态以本报告下方的最终一轮结果为准，早期失败/中断记录保留在本机，不改写成通过。

## 论文库和本地配置

- 路径：D:\AgentRe\data\papers-100。
- 100 个 PDF 均通过固定清单中的文件大小与 SHA-256 校验；191,727,279 字节，约 192 MB。
- 实际解析缓存统计为 100 篇、2,092 页，不只引用清单声明。
- 生成与文件哈希绑定的题录 sidecar；它不代表论文身份已经重新外部核验。
- 本机 MAX_PAPERS=100、MAX_TOTAL_PAGES=4000；单轮精读预算仍独立限制，真实测试每题选入 10 篇。
- data/papers-100/ 已被 Git 忽略，防止上传 PDF 和生成题录；data/runtime/、data/manual-test-results/ 与 .env 继续忽略。
- 页面若仍选择 data/papers，只会使用原来的小库。使用新库需将知识库路径改为 data/papers-100，重启后端应用本地新配置。

## 已修复的后端问题

1. 上传合法但无可提取文本的 PDF，现在返回 PDF_NO_EXTRACTABLE_TEXT，说明空白/扫描件问题，避免先显示上传成功再无原因阻塞。
2. 同项目、相同文件内容的重复上传复用确定性 file_id；旧上传 ID 仍可读，不静默迁移历史记录。
3. SQLite 不可覆盖对象使用原子 INSERT OR IGNORE 和内容核对；并发相同对象不会撞唯一键，冲突内容仍拒绝覆盖。
4. 没有可检索原文时保留具体停止原因。
5. 检索视图增加 Unicode 兼容字符、软连字符和跨行断词的附加索引词，保留原始词；不改写 PDF 文本、引文或锚点。
6. 扩充有限的中文领域查询别名。这不是通用机器翻译，也不保证覆盖所有中文问法。
7. 首轮取证实际使用用户提供的子问题，采用有上限的多查询融合，避免只用大而泛的题干。
8. 模型短引文关联错片段时，仅允许在同一实际文档中严格、唯一重定位，登记程序生成的 source span。跨文档、重复或虚构短引文不能自动通过。
9. 无法唯一匹配的短引文可在研究交接阶段退回真实登记片段，写入 quote_precision_fallback 和报告限制。它不是将错误引文视作精确引用，发现与结论仍交由 Reviewer 回读。
10. 重定位的片段在后续索引刷新后仍能读取；原文工具支持 evidence_id、兼容误放在 span_id 中的证据 ID，并在页面无指定 span 时优先读当前证据。
11. Reviewer 输入提供真实 span_ids；提示区分原文窗口、内部关联 ID 与最终数字引用，不为内部 ID 本身制造样式返工。
12. 审核意见中的 [evidence-...] 泛称转成“内部证据编号”，不混作真实引用。
13. “对照表/对比表/比较矩阵”等明确需求不再被错误限制为 0 行；要求表格时校验至少一行，明确不要表格和结构化 0 行覆盖仍可使用。
14. 新增 MODEL_TRUST_ENV 控制模型是否继承环境/系统代理；默认 true，本机诊断后设 false。拥有并关闭每次 Agent 调用的异步 HTTP 客户端，不修改系统网络、不关闭 TLS。
15. 验收工具显式使用 UTF-8 保存中文结果，支持 --project-id 在顺序用例之间复用同一项目索引。

## 离线测试和公平对照

最终完整后端回归：147 passed，13 个既有 LangSmith 弃用警告，无失败。依赖检查无损坏依赖。

全库的固定 6 道有标准页题目，共 11 个目标论文项/证据页：

- 仅题干筛选候选时原报告曾有遗漏；题干加既有子问题时，前 10 篇候选覆盖 11/11 个目标论文项。
- 未限定候选的题干前 6 段：2/11 个标准页；固定英文检索式：4/11。
- 在同一候选论文范围内，旧首轮仅题干命中 2/11；新题干+已有子问题融合命中 4/11。
- 检索函数没有读取标准答案、目标页或目标论文标签。这是固定小样本的对照结果，不能写成通用召回率已经充分提高。
- 实际文献允许多个原文页支持同一结论，固定页命中只是一个指标；最终需要按语义复核。
- 基线冷索引约 100.91 秒；优化检索对照复用了相同缓存，不能将暖缓存时间当成解析性能收益。

100 篇真实 PDF 的 HTTP 集成（Agent 为脚本替身，0 付费调用）已验证：

- 全库索引及 10 篇精读预算，能取到文件名顺序第 99 篇 WebThinker。
- 三个角色交接、报告/审核版本和证据快照一致。
- 原始 PDF 哈希与冻结清单一致，定位接口重新读取文本并匹配。
- 跨项目读取被拒绝；模型预算为 1 时正确停止为 blocked，未伪装通过。
- 真实 RAG PDF 重复上传返回相同 ID 和正确 SHA-256。

结果：data/manual-test-results/corpus-100-functional.json、corpus-100-baseline.json、corpus-100-optimized.json。

## 真实外部服务与模型测试

独立 arXiv 服务探针通过查询、权威记录身份 verified 和实际 PDF correspondence=matched；它不等于整套联网/混合报告质量验收。

早期真实模型测试曾发现 INVALID_EVIDENCE_QUOTE、原文读回 ID 不匹配、占位文本泄露与表格契约误判，已加入回归并修复。模型连接诊断中，继承环境路径失败、直接 HTTPS 请求成功；项目内网络策略调整后个人 API 鉴权和模型生成恢复。

最终一轮结果目录：data/manual-test-results/corpus-100-live-20261118T123415Z。每题最多 32 次模型响应、100 次工具调用、420 秒、1 批反馈，精读候选 10 篇；不是把全部 100 篇全文一次发送给模型。

真实模型的语义质量需要团队人工回读；工具输出中的 execution=passed 仅表示执行、引用结构、来源与版本检查通过，不能代替 task_status 或人工质量验收。review.verdict=pass 若 status=partial 或覆盖不足，同样不能自动交付。

## 复现命令

在项目根目录：

```powershell
.\.venv\Scripts\python.exe backend/tools/prepare_corpus_100.py
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe backend/tools/benchmark_corpus.py --label optimized
.\.venv\Scripts\python.exe backend/tools/test_corpus_functional.py
```

真实模型需要启动后端，会产生费用：

```powershell
.\.venv\Scripts\python.exe backend/tools/test_corpus_live.py --live --suite corpus-100 --project-id corpus-100-evaluation --model-calls 32 --seconds 420
```

本轮实际使用独立后端和独立运行目录，未停止用户的主服务。最终结果还会通过单独的本地程序重新读取 PDF 验证引文位置。

## 尚未解决的范围

- 复杂报告并非全部达到 completed/passed；不能为提高通过率而取消事实、引用、范围或版本门禁。
- 跨语言检索仍是有限别名+BM25+查询融合，没有 embedding/学习式 reranker。
- PDF 坐标高亮、复杂表格/OCR、前端比较表引用汇总边界和审核详情读取失败提示未在本轮修改。
- 本轮实际模型套件为本地 100 篇库；完整联网/混合报告、浏览器视觉交互与导出仍需专项验收。

## 最终个人 API 验收结果

最终七题的 execution 全部 passed；其中 2 题 completed/passed，5 题 partial。部分完成不能计为最终报告质量通过。所有用例均索引全库 100 篇、精读选入 10 篇。

- L01：task_status=completed；审核 status=success / verdict=pass；模型响应 8 次；46.22 秒；run_id=9901811a-bcdb-4531-bca9-ceea87197ed6。
- L02：task_status=partial；审核 status=partial / verdict=revise；模型响应 22 次；108.04 秒；run_id=42714708-b400-4600-99d1-9044623bc242。
- L03：task_status=partial；审核 status=success / verdict=undetermined；模型响应 18 次；102.04 秒；run_id=a07fe73d-cf66-42e0-b2a8-09033f38b2ed。
- L04：task_status=partial；审核 status=partial / verdict=pass；模型响应 16 次；82.98 秒；run_id=cf4fcb30-cdbf-435f-982e-983a88c1cc03。
- L05：task_status=completed；审核 status=success / verdict=pass；模型响应 8 次；48.42 秒；run_id=a4dd7979-c029-485d-9bc0-c1c8219e26a3。
- L06：task_status=partial；审核 status=success / verdict=undetermined；模型响应 23 次；121.69 秒；run_id=d310748c-c24c-47bb-8264-88d4c55fde21。
- L07：task_status=partial；审核 status=partial / verdict=undetermined；模型响应 14 次；79.96 秒；run_id=d764d9b2-a596-40b9-92c3-c8d1e0f80eca。

最终一轮累计模型响应尝试 109 次，报告用量 1,883,827 token。此统计不包含早期排错/中断轮次，不等于服务商最终账单。

独立重读 PDF 的位置核对：40/40 条引文匹配，页码与来源哈希一致。共记录 2 次严格同文档原文重定位、6 次带标记的原始片段回退；未接受虚构短引文为精确引用。

最终引文覆盖固定目标页 10/11 个任务标注项。40 条位置匹配不证明全部主张语义正确，固定页命中也不能代替人工语义审核。

L01 单篇机制与 L05 同缩写辨别达到程序交付门禁；L02/L03/L04/L06/L07 保留为未完成审核或待修订草稿。L04 虽 verdict=pass，但审核执行 status=partial，因此程序仍未放行。剩余改进主要是复杂比较的事实/范围措辞、审核完整性、缺口表达，以及多轮修订成本。不能通过自动将 partial 改成 success 来掩盖问题。

完整输出、期望要点、must_not、审核问题和用量均保留在上述结果目录；semantic_review 保留 pending，正式人工评分尚未完成。
