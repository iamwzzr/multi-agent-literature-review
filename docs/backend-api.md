# Folio 后端联调与接口设计

## 联调入口

Folio 默认访问 `http://localhost:35549`。本机开发时请让后端监听回环地址的 `35549` 端口。远程地址使用 HTTPS，可填写反向代理的路径前缀。前端会拼接 `/api/v1`。

后端配置 `ACCESS_TOKEN` 后，在「设置 → 后端连接」填写同一令牌。前端通过 `Authorization: Bearer …` 发送，令牌保存在当前标签页。未配置令牌时，后端仅接受回环连接。令牌对应单个工作区所有者。已生成的对话与后端地址绑定。

本版前端负责项目配置、对话历史和界面状态。每次生成把当前项目和对话上下文发给后端。后端负责本地文献索引、Agent 协作、模型调用、核查和返回结果。浏览器在当前标签页保存完成的对话。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 检查服务是否就绪以及是否支持 Folio v1 |
| `POST` | `/api/v1/reviews/stream` | 新建或续写综述，流式返回进度、报告和证据 |
| `GET` | `/api/v1/folders?path=…` | 列出后端允许目录下的子目录。省略 `path` 时列出允许的根目录 |
| `POST` | `/api/v1/projects/validate` | 校验项目和知识库路径，返回规范化目录 |
| `GET` | `/api/v1/papers/pdf?projectId=…&paperId=…` | 可选。提供引用对应的源论文 PDF |
| `GET` | `/api/v1/runs/{run_id}?projectId=…&conversationId=…&includeArtifacts=false` | 查询任务状态并取回完成稿 |
| `DELETE` | `/api/v1/projects/{project_id}/conversations/{conversation_id}` | 删除对话对应的服务端报告和运行记录 |

## `GET /api/v1/health`

服务就绪时返回 `200` 和以下 JSON。前端的「测试连接」在 5 秒内等待这个响应。

```json
{"status":"ok","apiVersion":"v1"}
```

服务未就绪时可返回 `503`，错误体使用下文的格式。健康检查可以独立于单次模型调用运行。

## `POST /api/v1/reviews/stream`

请求头使用 `Content-Type: application/json` 和 `Accept: application/x-ndjson`。首次请求的示例如下。

```json
{
  "conversationId": "c13a471e-c254-48a5-a3ec-6bf72aa62b85",
  "project": {
    "id": "literature",
    "name": "文献综述研究",
    "workingDirectory": "/Users/researcher/Research/review",
    "knowledgePaths": ["papers", "notes"]
  },
  "question": "不同文献检索策略如何影响综述的证据覆盖？",
  "history": [],
  "references": []
}
```

| 字段 | 约定 |
| --- | --- |
| `conversationId` | 前端生成。同一对话的追问和重试沿用此 ID。 |
| `project` | `id` 标识项目。`workingDirectory` 是后端可访问的工作目录。`~/` 由后端展开为服务账户的主目录，相对工作目录以服务配置的工作区根目录为基准，相对知识库路径以工作目录为基准。解析后的目录均按后端允许范围校验。 |
| `question` | 本轮研究问题或修改要求，前端最多输入 400 字符。 |
| `history` | 按时间顺序排列最近三轮。每轮包含 `question`、`sections` 和 `evidence`，可包含 `reply` 和 `reportUnchanged: true`。末轮保留完整稿和证据，较早轮只发送问答文字。 |
| `references` | 通过 `@` 选中的同项目、同后端对话，最多 10 条。每项包含 `conversationId`、最多 300 字符的 `title` 和 `turn`。`turn` 带最新稿件，上下文里的证据数组可为空。 |

`sections` 的元素形如 `{"id":"findings","heading":"主要发现","paragraphs":["正文[[1]]"]}`。`evidence` 是下面 `evidence` 事件中的 `item` 数组。每轮独立编号，历史和引用对话属于上下文，当前轮的证据由后端重新核对。

真实后端模式使用服务端目录浏览，支持手填服务器上的绝对或相对路径。校验接口接收 `project` 对象，返回 `workingDirectory`、`knowledgePaths` 和 `workingDirectoryLocked`。项目首次运行后会绑定工作目录，使用其他目录时可新建项目。目录列表返回 `current`、`parent`、`folders`（每项包含 `name`、`path`）和 `truncated`。

### 流式响应

成功开始时返回 `200` 和 `Content-Type: application/x-ndjson; charset=utf-8`。每个事件占一行 UTF-8 JSON 并以换行结束。发送后及时刷新缓冲区，长时间等待期间可发送空行保活。反向代理应关闭该路由的响应缓冲。

| `type` | 额外字段 | 规则 |
| --- | --- | --- |
| `phase` | `title`、`summary`、`working`、`done`，可选 `feedback`、`taskDetails` | `working`、`done` 是 Agent ID 数组。`feedback: true` 显示退回补查。`taskDetails` 以 Agent ID 为键、当前任务说明为值。 |
| `evidence` | `index`、`item` | `index` 从 1 连续递增。在正文出现对应 `[[n]]` 前发送。 |
| `section` | `id`、`heading` | 声明章节。同一轮中 `id` 唯一，章节按声明顺序显示。 |
| `delta` | `sectionId`、`paragraph`、`text` | 向已声明章节追加纯文本。`paragraph` 从 0 连续递增。同一段落可收到多次追加。 |
| `reply` | `text` | 可选。分段追加对话回复，用于说明本轮改动或回答问题。 |
| `done` | `runId`、`verification`、可选 `reportUnchanged: true` | 成功的最后一行。核验状态为 `passed`、`with_warnings` 或 `no_evidence`，用于右栏和导出。仅回复时使用 `reportUnchanged: true`。随后关闭响应。 |
| `error` | `code`、`message` | 流开始后的失败终止事件。`message` 会直接显示在前端。随后关闭响应。 |

Agent ID 固定为 `planner`（统筹规划）、`search`（文献检索）、`analysis`（论文分析）、`writing`（综述撰写）、`verification`（事实核查）。建议先发送工作进度，核查完成后再发送最终报告的证据和正文。以下示例演示事件和引用编号的对应关系。

```ndjson
{"type":"phase","title":"规划任务","summary":"拆解研究问题并确定检索范围。","working":["planner"],"done":[]}
{"type":"phase","title":"并行研究","summary":"检索、分析和撰写正在进行。","working":["search","analysis","writing"],"done":["planner"]}
{"type":"phase","title":"事实与引用核查","summary":"核对主张与原文页码。","working":["verification"],"done":["planner","search","analysis","writing"]}
{"type":"evidence","index":1,"item":{"paper":{"id":"paper-42","title":"研究文献标题","author":"Lin 等","year":2025,"pages":18,"summary":"比较两种检索流程。"},"page":7,"excerpt":"按子问题分组能够发现检索空白。","context":"该段比较了按主题和按子问题组织的检索结果。"}}
{"type":"section","id":"findings","heading":"主要发现"}
{"type":"delta","sectionId":"findings","paragraph":0,"text":"按子问题记录命中结果，有助于定位证据缺口。[[1]]"}
{"type":"done"}
```

`paper.id` 应在项目内稳定。同一论文的不同页码可以对应不同引用。`year` 为整数或 `null`，`pages` 为 PDF 总页数，`page` 为从 1 开始的 PDF 页序，满足 `1 <= page <= pages`。`excerpt` 提供可核对的原文，`context` 提供上下文，`summary` 提供文献简介。证据栏会用这些字段显示来源和原文摘录。有效检索没有找到支持材料时，返回说明证据缺口的正文和 `done`，正文可没有引用。

### 修订与追问

收到修改请求时，以 `history` 的末轮稿件为基础。通过 `section`、`delta` 和 `evidence` 返回一份完整修订稿，包含保留的章节和此次改动。可用 `reply` 简短说明改动。前端收到 `done` 后发布新版本，右侧与导出入口同步使用该版本。

若这轮只回答问题或汇报核查结果，发送 `reply` 和 `{"type":"done","reportUnchanged":true}`。此模式需要已有完整稿件和非空回复，本轮无需发送 `section`、`delta` 或 `evidence`。前端沿用上一版的稿件和引用，继续显示在右侧。流中断、出错或被停止时，上一份完成稿仍可查看和导出。

### 错误与取消

写出流响应前，使用合适的非 `2xx` 状态和如下错误体。流已开始时，使用 `error` 事件。前端收到 `done` 后保存完成稿，也可凭 `X-Run-Id` 查询服务端已完成的稿件。任务 ID 必须在 CORS 的 `Access-Control-Expose-Headers` 中声明。重试会重新发送本轮请求。

```json
{"error":{"code":"INVALID_KNOWLEDGE_PATH","message":"知识库目录 papers 不存在，请检查项目配置。"}}
```

HTTP 错误的 `error` 对象和流式 `error` 事件都包含 `code`、`message`，也可以带 `agent`、`providerStatus`、`retryable`。`agent` 沿用上面的 Agent ID。`providerStatus` 是模型服务返回的 HTTP 状态，`retryable` 表示当前配置和输入下是否适合直接重试。失败任务的查询响应也可包含同样的 `error` 对象。

```ndjson
{"type":"error","code":"MODEL_RATE_LIMITED","message":"请稍后重试。","agent":"writing","providerStatus":429,"retryable":true}
```

模型鉴权、余额、限流、超时和输出异常使用独立错误码。返回给前端的消息使用可直接展示的处理提示，省略模型服务原始响应和凭据。失败时保留上一份完成稿。

可以用 `400` 表示请求格式错误，`422` 表示项目目录或知识库配置不可用，`503` 表示模型或服务暂时不可用。用户点击「停止生成」时，浏览器会中止 HTTP 请求。删除服务端记录返回 `204`，项目正在运行时返回 `409`。归档和「仅移除本标签页」只影响浏览器记录。

## 源论文 PDF

能提供整份 PDF 时，在流式 `evidence` 事件的 `item.paper` 中设置 `pdfAvailable: true`。前端用当前生成服务的地址和项目、论文 ID 组成 `/api/v1/papers/pdf?projectId=…&paperId=…`，在浏览器 PDF 阅读器打开并通过 `#page=N` 定位到证据页。原文摘录入口仍独立可用。 [PDF 页码定位规范](https://www.rfc-editor.org/rfc/rfc8118.html#section-3)

按 `projectId` 和 `paperId` 查找索引中的论文并校验访问范围。成功响应返回 PDF 字节，使用 `Content-Type: application/pdf` 和 `Content-Disposition: inline`。大文件可支持 HTTP Range 请求。前端使用的页码与提供的 PDF 版本应一致。

成品综述的 PDF 和 Markdown 由前端根据已完成的报告生成，使用同一份章节和引用数据。

## 后端开发任务

1. **服务和联调。** 实现健康检查和流式路由，监听 `35549`。前端开发源包括 `http://localhost:5173` 和 `http://127.0.0.1:5173`，生产构建本地预览使用 `4173`。按实际前端源配置 CORS，允许 `GET`、`POST`、`DELETE` 和 `Content-Type`、`Authorization` 请求头，并暴露 `X-Run-Id`。 [Fetch CORS 规范](https://fetch.spec.whatwg.org/#http-cors-protocol)
2. **项目和本地 PDF。** 解析工作目录、知识库路径和符号链接，限制实际目录在服务配置允许的范围内。PDF 解析时保留页序、原文段落、文件标识和文献元数据，按工作区和项目隔离检索索引，并支持文件变动后的更新。
3. **Agent 调度。** 规划者拆解研究问题，检索员找文献，分析员整理可比证据，撰写员生成综述，核查员核对主张和页码。证据缺失时把具体问题退回规划，并通过 `phase` 报告工作中的角色。
4. **续写和证据。** 用 `history` 与 `references` 作为上下文，按本轮 `question` 修改或补查。后端校验每个引用的原文和页码，证据不足的地方明确标注。修订时交付完整稿件，问答时可以保留现有稿件。
5. **运行边界。** 模型凭据和模型配置放在后端。处理无效目录、请求过大、并发、模型超时与断开连接。日志记录项目、对话 ID、阶段和错误码，按需要管理文献内容和模型输出的留存范围。

## 联调验收

1. 后端启动后执行 `curl -i http://localhost:35549/api/v1/health`，确认返回 v1 就绪响应。打开 Folio「设置」并点「测试连接」，同时验证浏览器的跨域配置。
2. 在 Folio 配置一个实际含 PDF 的知识库，输入一个研究问题。检查办公室的 Agent 状态、逐段显示的正文和可打开的引用。
3. 在同一对话请求补写一节，检查后端收到相同 `conversationId` 和上一版稿件。完成后确认右侧显示完整新版，旧版仍可导出。再发送一次只需回复的追问，确认版本号不变。
4. 模拟路径错误、流中途关闭和用户停止，确认前端提示失败或停止，并可重试。
5. 提供源 PDF 接口后，验证「打开源 PDF」定位到引用页，并从「预览综述」保存一份带参考文献的 PDF。

从公开站点访问本机后端时，Chrome 可能要求站点获准访问本地网络。联调可从本地 Vite 地址发起。 [Chrome 本地网络访问说明](https://developer.chrome.com/blog/local-network-access)
