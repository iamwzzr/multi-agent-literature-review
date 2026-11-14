# 第一版前端对接与资料库准备清单

更新：2026-11-14。后端负责人：周芯豪。本文是队友对接说明，本次提交不修改前端代码。

## 当前状态与第一版剩余工作

后端已实现三 Agent（Researcher、Reporter、Reviewer），普通 Python 编排；支持本地、arXiv 联网、混合模式、PDF 上传、原文证据、身份及 PDF 对应检查、定向返工、预算停止和版本门禁。完整后端自动测试 69 项通过，正常预算的一条主张真实任务 completed/passed。详细结果见 BACKEND_TEST_REPORT_2026-11-14.md。

这不表示整个产品已完成第一版验收。还需完成来源模式与上传的页面入口、真实三 Agent 展示、任务状态和审核结果展示，并用固定论文集完成联调与人工抽查。复杂多论文样例目前仍可能 partial，重复补证及调用成本需要继续优化。尚未完成正式质量/成本对照实验。

## 必须优先完成的前端改动

### 1. 资料来源模式

在问题输入附近或项目设置加入一组互斥单选：本地 / 联网 / 混合；默认本地。不要设计成可同时勾选的多个开关。

- 本地：使用配置目录与上传文件；不自动发现在线论文。
- 联网：当前仅支持 arXiv；不使用本地目录和上传资料。提交时 knowledgePaths 与 uploaded_file_ids 置空，避免让用户误以为这些资料也被使用。
- 混合：使用本地资料，必要时补充在线资料；不保证每轮一定联网。

三种模式都可能将选中的论文片段发送给云模型。在线检索可以提供可选英文关键词/检索式输入，映射 online_query；不要向用户承诺全领域穷尽搜索。

### 2. PDF 上传入口

加入选择 PDF 或拖放区域，展示文件名、上传中/成功/失败状态。

接口：POST /api/v2/projects/{project_id}/uploads。

- Content-Type 为 application/pdf，正文为文件原始字节；不是 multipart/form-data。
- 沿用后端访问令牌 Authorization；不是模型 API 密钥。
- 成功返回 {"file_id":"upload-..."}，保存到对应项目的文件列表。
- 同一项目后续生成发送 uploaded_file_ids；不能跨项目复用。
- 浏览器上传与后端知识库目录是不同入口，不能把浏览器本机文件路径当作后端可访问目录。
- 现有上传接口不提供完整的列表/删除管理接口；第一版先保存已上传 ID 和文件名，完整管理能力另行对接。

### 3. 发送新增请求字段

生成接口 POST /api/v2/reviews/stream；现有 /api/v1/reviews/stream 也兼容新字段。建议新增功能使用 v2，但健康检查、运行查询、PDF 仍使用其现有 v1 路径。

在现有 conversationId、project、question、history、references 外增加：

```json
{
  "architecture": "three_agent",
  "source_mode": "hybrid",
  "allow_local_metadata_lookup": false,
  "uploaded_file_ids": ["upload-..."],
  "online_query": "ti:\"Retrieval-Augmented Generation\"",
  "research_budget": {
    "documents": 10,
    "feedback_batches": 1,
    "model_calls": 60,
    "tool_calls": 150,
    "seconds": 600
  }
}
```

上面仅展示新增字段，不能作为完整请求。question 当前最多 400 字符；预算上限为文档 40、返工 3 批、模型调用 60、工具调用 150、时间 600 秒。初版可使用固定预算，不必把所有参数做成控件。

本地书目信息联网核验 allow_local_metadata_lookup 默认 false；若提供高级开关，应独立于来源模式，并解释开启后会请求外部元数据服务。无需让用户在网页输入模型密钥，模型配置继续留在后端环境。

### 4. 明确展示任务与审核状态

现有 src/backend.ts 的 done 分支没有保留 taskStatus；getBackendRun 也未完整返回审核与比较信息，需要扩展类型、状态保存和恢复。

- completed + verification=passed：报告通过程序交付门禁，仍可人工复核。
- partial：部分草稿/未完成审核，醒目标注，保留问题。
- blocked：无法完成，显示资料/预算等停止原因。
- error：执行错误，保留现有错误码和重试提示。

done 只代表流结束；顶层运行 status=completed 也不能代替 report.task_status。原有 verification 与 taskStatus 应一起处理。

通过 X-Run-Id / done.runId 保存运行 ID。GET /api/v1/runs/{run_id}?includeArtifacts=false 可取得 report.review、unresolved、usage、comparison_table、report_version、evidence_snapshot_id。getBackendRun 目前会丢弃部分字段，需保留并用于刷新恢复。报告和审核版本必须一致；不要把预算耗尽的草稿展示成已审核报告。

### 5. 三 Agent 展示

页面当前仍为五工位；新后端实际为三个 Agent，任务路由与协调由 Python 程序负责。

为了保持已有流式协议，后端阶段事件仍使用旧活动 ID：search/analysis 可归到 Researcher，writing 归到 Reporter，verification 归到 Reviewer；planner 如保留，应标为程序协调而非第四个模型 Agent。前端先做显示层分组，不要直接把后端 working/done ID 改成协议未支持的新值。

更新“5 个角色”、说明文案、演示标签和相关统计，避免把动画工位数量当作实际模型 Agent 数量。

### 6. 结果、引用和比较表

- 继续支持现有 [[n]] 数字引用。内部 evidence-/claim-/document- 等 ID 仅作结构化关联，不直接作为正文引用展示。
- 比较表渲染 report.comparison_table；证据引用使用同一份 evidence 数字映射。当前流式正文也包含比较行，但不是专用表格组件。
- 未报告值为 null，应显示“未知/未报告”，不能填 0。
- 文献来源、用户提供且未外部核验等说明至少展示 paper.summary；更细的身份/对应状态可从运行审计记录查看。若需高效的结构化论文状态列表，前后端再约定精简接口，避免把完整文档原文加载进页面状态。
- PDF 沿用 /api/v1/papers/pdf?projectId=...&paperId=...；三 Agent 的 paperId 指实际 document_id，保留 PDF 页序号。
- 展示未解决问题、审核意见与版本；既有 Markdown/PDF 导出应保留 partial 警示与来源信息。

## 本地资料库：已有基础，无需另装一个数据库

- 论文目录：data/papers/；也支持配置其他允许目录或使用上传接口。
- 数据库：data/runtime/workspace.sqlite3，存储项目、运行、对象、证据和审计记录。
- 检索：当前为保留 PDF 页码的分段 BM25，支持英文词和中文双字词；没有实现 embedding 向量数据库。
- 原始 PDF 按内容哈希保存于运行目录，证据绑定实际读取的版本。

第一版不必先引入独立向量数据库。若后续固定评测发现跨语言、同义表达或大规模检索召回不足，再对比向量/混合检索，不应在没有验收依据时仅为技术栈增加组件。

### 给资料负责人准备的内容

先准备同一研究主题的 5–10 篇可提取文本 PDF，再挑 2–3 篇作为稳定回归集。现有 RAG 与 Self-RAG 可作为起点。资料应来自合法取得的文件；PDF 不提交到 Git。

每篇登记文件名、标题、作者、已知年份、DOI/arXiv ID、取得来源和版本。未知信息保留未知；人工清单不等于程序已完成外部身份核验。

每个固定问题准备人工标准：关键结论、原文段落、PDF 页序号、适用条件、不能直接比较的原因、哪些信息未报告。另准备无相关证据、错误文件对应、扫描件/不可解析等反例；错误样例需明确标注，不能混入正常研究库。

共享方式：团队受控共享文件夹或各自下载；Git 只放许可允许的清单、获取说明和验收题，不放论文、密钥、SQLite、原始摘录日志。固定评测可按问题定义期望覆盖，不能只以“输出了一篇长报告”判定通过。

## 联调顺序

1. 来源选择和新增请求字段；分别确认 local/online/hybrid 真正发送到后端。
2. 上传 PDF，只用返回 ID 生成，knowledgePaths 为空。
3. 三 Agent 分组、taskStatus、审核结果及刷新恢复。
4. 数字引用点击、原文 PDF 页码、比较表和导出警示。
5. 固定论文集：本地、联网、混合补证、无证据、取消、预算不足和身份/PDF 错配。
6. 保存真实运行 ID 和人工抽查结果，再确认第一版验收；不得用演示动画替代真实模型测试。
