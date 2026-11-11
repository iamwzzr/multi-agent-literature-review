# Folio 后端联调与接口设计

## 联调入口

Folio 默认访问 `http://localhost:35549`。本机开发时请让后端监听回环地址的 `35549` 端口。前端「设置 → 后端连接」可以保存其他服务地址，支持 HTTP、HTTPS 和反向代理的路径前缀。填写服务根地址或代理前缀，前端会拼接 `/api/v1`。

本版前端负责项目配置、对话历史和界面状态。每次生成把当前项目和对话上下文发给后端。后端负责本地文献索引、Agent 协作、模型调用、核查和返回结果。浏览器在当前标签页保存完成的对话。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 检查服务是否就绪以及是否支持 Folio v1 |
| `POST` | `/api/v1/reviews/stream` | 新建或续写综述，流式返回进度、报告和证据 |

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
| `history` | 按时间顺序排列的已完成轮次。每轮包含 `question`、`sections` 和 `evidence`。首轮为空数组。 |
| `references` | 通过 `@` 选中的同项目后端对话。每项包含 `conversationId`、`title` 和 `turn`，其中 `turn` 是该对话最新一轮的 `question`、`sections` 和 `evidence`。 |

`sections` 的元素形如 `{"id":"findings","heading":"主要发现","paragraphs":["正文[[1]]"]}`。`evidence` 是下面 `evidence` 事件中的 `item` 数组。每轮独立编号，历史和引用对话属于上下文，当前轮的证据由后端重新核对。

浏览器的文件夹选择器只返回目录名。选在项目目录下的知识库可用这个名字作为相对路径。目录在其他位置时，请在「配置项目」填写后端机器上的完整路径。 [浏览器文件系统规范](https://fs.spec.whatwg.org/#dom-filesystemhandle-name)

### 流式响应

成功开始时返回 `200` 和 `Content-Type: application/x-ndjson; charset=utf-8`。每个事件占一行 UTF-8 JSON 并以换行结束。发送后及时刷新缓冲区，长时间等待期间可发送空行保活。反向代理应关闭该路由的响应缓冲。

| `type` | 额外字段 | 规则 |
| --- | --- | --- |
| `phase` | `title`、`summary`、`working`、`done`，可选 `feedback`、`taskDetails` | `working`、`done` 是 Agent ID 数组。`feedback: true` 显示退回补查。`taskDetails` 以 Agent ID 为键、当前任务说明为值。 |
| `evidence` | `index`、`item` | `index` 从 1 连续递增。在正文出现对应 `[[n]]` 前发送。 |
| `section` | `id`、`heading` | 声明章节。同一轮中 `id` 唯一，章节按声明顺序显示。 |
| `delta` | `sectionId`、`paragraph`、`text` | 向已声明章节追加纯文本。`paragraph` 从 0 连续递增。同一段落可收到多次追加。 |
| `done` | 无 | 成功的最后一行。至少有一段正文，正文内每个 `[[n]]` 都有对应证据。随后关闭响应。 |
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

### 错误与取消

写出流响应前，使用合适的非 `2xx` 状态和如下错误体。流已开始时，使用 `error` 事件。前端只把收到 `done` 的轮次写入对话历史，重试会重新发送本轮请求。

```json
{"error":{"code":"INVALID_KNOWLEDGE_PATH","message":"知识库目录 papers 不存在，请检查项目配置。"}}
```

可以用 `400` 表示请求格式错误，`422` 表示项目目录或知识库配置不可用，`503` 表示模型或服务暂时不可用。错误文案应帮助用户修复问题。用户点击「停止生成」或删除生成中的对话时，浏览器会中止 HTTP 请求，后端应在连接断开时停止对应任务并释放资源。

## 后端开发任务

1. **服务和联调。** 实现健康检查和流式路由，监听 `35549`。前端开发源包括 `http://localhost:5173` 和 `http://127.0.0.1:5173`，生产构建本地预览使用 `4173`。按实际前端源配置 CORS，处理 `OPTIONS`、`GET`、`POST` 和 `Content-Type` 请求头。响应与错误都返回正确的跨域头。 [Fetch CORS 规范](https://fetch.spec.whatwg.org/#http-cors-protocol)
2. **项目和本地 PDF。** 解析工作目录、知识库路径和符号链接，限制实际目录在服务配置允许的范围内。PDF 解析时保留页序、原文段落、文件标识和文献元数据，按工作区和项目隔离检索索引，并支持文件变动后的更新。
3. **Agent 调度。** 规划者拆解研究问题，检索员找文献，分析员整理可比证据，撰写员生成综述，核查员核对主张和页码。证据缺失时把具体问题退回规划，并通过 `phase` 报告工作中的角色。
4. **续写和证据。** 用 `history` 与 `references` 作为上下文，按本轮 `question` 修改或补查。后端校验每个引用的原文和页码，证据不足的地方明确标注。按协议发送 `evidence`、`section`、`delta` 和 `done`。
5. **运行边界。** 模型凭据和模型配置放在后端。处理无效目录、请求过大、并发、模型超时与断开连接。日志记录项目、对话 ID、阶段和错误码，按需要管理文献内容和模型输出的留存范围。

## 联调验收

1. 后端启动后执行 `curl -i http://localhost:35549/api/v1/health`，确认返回 v1 就绪响应。打开 Folio「设置」并点「测试连接」，同时验证浏览器的跨域配置。
2. 在 Folio 配置一个实际含 PDF 的知识库，输入一个研究问题。检查办公室的 Agent 状态、逐段显示的正文和可打开的引用。
3. 在同一对话追问一次，检查后端收到相同 `conversationId` 和前一轮 `history`。打开旧回复，核对旧引用仍能定位。
4. 模拟路径错误、流中途关闭和用户停止，确认前端提示失败或停止，并可重试。

从公开站点访问本机后端时，Chrome 可能要求站点获准访问本地网络。联调可从本地 Vite 地址发起。 [Chrome 本地网络访问说明](https://developer.chrome.com/blog/local-network-access)
