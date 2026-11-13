# 三 Agent 第一版后端实现与调用

设计基线：用户提供的《设计说明(1).pdf》，文本见根目录 DESIGN.md。主分支 7cdd368 的概览另存为 THREE_AGENT_OVERVIEW.md；其中“未实现”是设计时的状态，不是本次测试结论。

## 本次范围

- Python 3.14；LangChain 1.5.0 create_agent + ToolStrategy，外层 Python 编排；固定 researcher / reporter / reviewer 三种模型职责。
- 不修改前端 src、样式或构建配置。已有 Folio NDJSON 流保持兼容，前端工位 ID 仅作活动展示。
- 保留最新后端的访问令牌、回环限制、结构化错误和缓存修复。
- 原旧流程仅供 architecture=legacy 的兼容回归；默认三 Agent。

## 新请求参数

沿用 POST /api/v1/reviews/stream，同时提供 /api/v2/reviews/stream。请求仍需 conversationId、project、question。
新增可选字段：

```json
{
  "architecture": "three_agent",
  "source_mode": "local",
  "allow_local_metadata_lookup": false,
  "online_query": "ti:Retrieval",
  "subquestions": [{"question": "检索成本是否报告？"}],
  "research_scope": {"domain": "multi-hop QA"},
  "output_requirements": {"language": "zh-CN"},
  "uploaded_file_ids": [],
  "research_budget": {"documents":20,"feedback_batches":2,"model_calls":60,"tool_calls":150,"seconds":600}
}
```

subquestions 的可信 ID 由程序生成；research_scope 是交给 Agent 的研究条件，不是学术服务穷尽检索保证。
现有前端不需要改动即可按默认 local 运行；新增模式和上传需通过 API 使用，页面尚无本次新增控件。

## 上传

POST /api/v2/projects/{project_id}/uploads，Content-Type: application/pdf，正文直接为 PDF 字节，返回 file_id。
把 file_id 放进同项目后续请求的 uploaded_file_ids。也可继续使用本地允许目录 knowledgePaths。
资料复制到项目隔离、按内容哈希命名的 originals；内容及解析版本不静默覆盖。

## 来源与核验

- local 默认不访问学术搜索或元数据服务。材料标为“用户提供的文档；公开发表身份未外部核实”。云端模型仍会收到选中的片段。
- allow_local_metadata_lookup=true 仅允许上传文档头部 DOI 的 Crossref 精确查询及标题/作者对应检查，不开放本地模式的新论文发现。
- online 当前接入 arXiv Atom 搜索，再对每项执行精确版本 ID 查询，保存原始权威记录、时间和结论。只有 verified 候选可获取正文。
- PDF 获取后检查首页标题、作者和 arXiv 版本。matched 才进入在线证据；不确定保留 unresolved，明确标识冲突为 mismatch。
- hybrid 从本地材料开始，缺少本地材料时在线发现，或在具体返工问题出现时定向联网补证。相同内容哈希记录关联，不重复计作新研究。
- 在线发现目前限 arXiv，不能声称覆盖所有期刊；不绕过访问权限。API 无结果、服务故障、未核验候选和全文不可得分别保留。
- unknown 年份/出版信息保持空值，PDF 创建日期不当作发表年份。

## Agent 工具与控制

Researcher：search_document、read_original、record_evidence、list_project_papers、get_paper_record、get_verification_log；仅 online/hybrid 绑定 search_verified_papers、fetch_paper_content。
Reporter：query_evidence、read_original、get_paper_record。Reviewer：read_original、query_evidence、get_paper_record、get_verification_log。
证据原文由程序从登记片段回填，模型不能以自编摘录创建原始材料。
Reviewer 输入包含程序重新读取的实际原文页；必要时分批检查主张，避免静默截断原文。
Reporter 的比较表行同时转为待审核主张，因此比较表中的条件、结果与引用也经过审核。

模型内部格式修正和额外调用计入同一预算；HTTP 瞬态重试最多 3 次并逐次记账；Agent 每次最多 12 次模型、30 次工具调用。
模型 SDK 的隐藏自动重试关闭。记录 token 量；LangSmith 云追踪显式关闭。
任务预算/时间耗尽输出 partial 或 blocked，不强制通过。

## 交付与版本

程序生成任务、子问题、证据、快照、报告和问题 ID。SQLite research_objects 为项目隔离的不可覆盖对象；旧 runs/artifacts 表保留兼容。
GET /api/v2/projects/{project_id}/objects/{object_id} 读取对象。源 PDF 入口仍为 /api/v1/papers/pdf，三 Agent 报告的 paperId 绑定具体 document_id。
审核必须 pass、检查覆盖所有主张、没有开放的 blocking 问题，且 report_version / evidence_snapshot_id 与当前稿一致。
仅 Reporter 问题走 Reporter→Reviewer；证据问题才回 Researcher；补证批次共享同一反馈预算。

执行状态与审核结论分开：兼容层 done 表示响应执行结束，不表示审核 pass；以最终 taskStatus 与 verification，以及报告 review.verdict 为准。v2 固定三 Agent，不能通过 architecture=legacy 降级；旧兼容模式只允许本地来源。
partial 草稿明确标为未完成审核；blocked 不生成貌似正常的综述。最终格式渲染不再调用 Reporter 改写事实。

## 安装、启动、验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\start-backend.cmd
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

真实验收（需要本机模型凭据，会产生 API 费用）：

```powershell
.\.venv\Scripts\python.exe backend/tools/acceptance_three_agent.py --live --mode local
.\.venv\Scripts\python.exe backend/tools/acceptance_three_agent.py --live --mode online
.\.venv\Scripts\python.exe backend/tools/acceptance_three_agent.py --live --mode hybrid
```

配置沿用本机 .env；密钥不写入测试、提示词、日志和文档。本次没有推送远程；前端能力扩展由前端负责人决定。

## 2026-11-14 引用展示与验收

内部 evidence ID 仅用于结构化关联及审计；后端将已校验的正文引用转换为现有前端支持的 `[[n]]`。未知或不属于本条主张的引用会被拒绝。

详细测试记录见 [BACKEND_TEST_REPORT_2026-11-14.md](BACKEND_TEST_REPORT_2026-11-14.md)。真实 HTTP 验收：

```powershell
.\.venv\Scripts\python.exe backend/tools/validate_system.py --live
```

需运行后端；真实模型会产生费用。可用 `--cases comparison,upload` 仅测试指定项。低预算正常停止不代表报告审核通过。
