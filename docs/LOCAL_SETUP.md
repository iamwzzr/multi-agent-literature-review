# 本地开发与联调（Windows / Python 3.14）

## 启动

项目位于 `D:\AgentRe`，本地分支为 `backend/zhouxinhao/bootstrap`。

1. 用 VS Code 打开项目根目录。
2. 在根目录 `.env` 中填写模型配置，不要把密钥发到聊天或提交 Git。
3. 按 F5，选择 `Backend: FastAPI (Python 3.14)`。服务监听 `127.0.0.1:35549`。
4. 打开 http://localhost:35549/docs 或 http://localhost:35549/api/v1/health 。
5. 停止调试使用 Shift+F5；若 reload 子进程仍在运行，在该终端按 Ctrl+C。

也可在根目录 PowerShell 运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 35549
```

或者进入 `backend` 目录，执行 `..\.venv\Scripts\python.exe -m app`。
不要重复启动相同端口。

macOS 和 Linux 可在仓库根目录运行以下命令。

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 35549
```

## 模型配置

复制 `.env.example` 为 `.env`（仅首次；不要覆盖已有密钥），至少配置：

```dotenv
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_API_KEY=你在模型服务商处申请的API密钥
MODEL_NAME=你的账号实际可用的模型标识
```

适配器使用 `POST {MODEL_BASE_URL}/chat/completions`，需要文本 JSON 输出。
它不支持 Anthropic 原生 API 或仅支持 Responses 的端点。第三方兼容服务是否可用需按其协议验证。
服务商若只支持 `max_tokens`，设置 `MODEL_TOKEN_PARAMETER=max_tokens`。
若不支持 `response_format`，可尝试 `MODEL_JSON_MODE=false`，但返回内容仍必须符合 JSON schema，否则明确报错。
不会自动切换模型，也没有生产模拟模式。

健康检查只表示服务和协议就绪，不测试模型余额或权限；模型配置缺失时生成接口返回 503。
默认只发送检索命中的原文片段、相关元数据、研究问题和有限历史给配置的模型服务。
本地检索不等于全文离线处理。每次运行最多 24 次逻辑模型调用，每次至多 2 次 HTTP 尝试；
默认每次输出上限 4000 tokens，完整运行超时 900 秒，补查最多 2 轮。这些是次数/输出限制，不是精确费用上限。

## 前端联调

从 `frontend` 分支的工作区启动新版 Folio，从 `backend/zhouxinhao/bootstrap` 工作区启动后端。后端分支随附的前端快照可用于基础接口测试。

需要 Node.js 22.12 或更高的兼容版本。机器现有 `E:\nodejs` 为 Node 16，不能用来运行此项目的 Vite；
请在前端终端先执行 `node --version` 确认版本。

```powershell
npm ci
npm run dev
```

在前端「设置 → 后端连接」填写 `http://localhost:35549`，关闭演示模式，点击测试连接。
在「配置项目」中设置：

```text
工作目录：D:\AgentRe
知识库路径：data/papers
```

先删除前端示例项目里不适用于本机的 `~/Research/...` 路径，再设置实际路径。
将自备、可提取文字的 PDF 放进 `data/papers`。索引依据文件元数据识别变动，只为新增或变更的 PDF 重新计算摘要并更新记录。打开源 PDF 时会核对内容摘要。
空库或扫描 PDF 会明确显示证据缺口/OCR 提示，不会生成假研究结论。

需要访问仓库以外的论文目录时，在 `.env` 增加精确允许目录，例如：

```dotenv
ALLOWED_ROOTS=["D:/AgentRe","D:/ResearchPapers"]
```

工作目录与每个知识库路径都必须位于允许目录中。路径会展开 `~`、解析相对路径、检查实际链接目标。
同一个项目 ID 不能改绑其他工作目录；换工作目录请新建前端项目。

## 已实现的工作流

1. 本地 PDF 按页提取、分块，保存 PDF 页序；元数据没有出版年份时保持 `null`。
2. Coordinator 规划最多 3 个子任务，并产生检索词。
3. Researchers 分题检索及分析，保留原文摘录、研究发现、方法和限制。
4. Synthesizer 生成完整草稿，包括适用的跨论文比较和局限，不流出未核验草稿。
5. Reviewer 对每段进行语义核验；后端另外检查引用编号、摘录与原文的一致性。
6. 核验问题产生定向补查任务，再修订、复核，最多 2 轮。
7. 未获支持的段落不交付；剩余问题以待核查清单交付。输出引用重新连续编号。
8. 新一轮修订交付完整稿件。只有服务端保存的已通过稿件、浏览器当前稿件一致、
   源证据仍存在且重新核验通过时，引用审查才可返回 `reportUnchanged: true`。

检索目前是内存 BM25（英文词、中文双字），不是向量检索；适合第一版小型本地文献集。
每个研究子任务最多检索 6 个片段；最终证据最多 12 条，为补查预留 4 条。
摘要/段落检索无法证明完整研究覆盖；模型核验也不等同人工审稿，输出需人工检查。
扫描件 OCR、表格/公式/图像理解、更大规模索引和精确文献出版元数据补全尚未实现。

## 数据、状态与运行边界

- `data/runtime/workspace.sqlite3` 保存项目索引、任务、Agent 产物、草稿版本、核验报告及最终稿。
- `GET /api/v1/runs/{run_id}` 查看状态和审计记录。流响应 `X-Run-Id` 提供运行 ID，查询时可带 `projectId`、`conversationId` 和 `includeArtifacts=false`。
- `GET /api/v1/folders` 浏览允许的目录，`POST /api/v1/projects/validate` 校验项目路径。`DELETE /api/v1/projects/{project_id}/conversations/{conversation_id}` 删除对应报告和审计记录。
- 用户停止或断开连接时取消模型请求和 PDF 子进程；服务器重启后原运行中任务标记 `interrupted`，不自动恢复。
- 同一项目同时只能运行一个任务，默认最多并行处理两个不同项目。
- 默认仅接受回环连接。若通过 HTTPS 反向代理供单个所有者使用，在 `.env` 配置独立的随机 `ACCESS_TOKEN`，并在 Folio 的后端连接设置中填写它。服务按 `Authorization: Bearer …` 验证令牌。请使用单个 worker。
- `health`、流式协议、错误格式及 PDF 路由见 [`frontend` 分支的接口约定](https://github.com/iamwzzr/multi-agent-literature-review/blob/frontend/docs/backend-api.md)。
- 日志记录任务/项目/对话 ID、错误类型，不输出 API 密钥；论文摘录和模型产物保存在本地 SQLite。
- `.env`、PDF、运行数据库、虚拟环境、`node_modules`、`dist` 均不提交。

## 环境重建与验证

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm run build
```

如果 `py -3.14` 未识别本机安装，可用 Python 3.14 的 `python.exe` 完整路径创建虚拟环境。
测试使用临时合成 PDF 和测试文件内的模型替身/HTTP mock，不访问真实模型，不把测试数据放入用户论文目录。
另有真实 TCP 断连测试，验证取消后项目槽位释放。
真实模型验收：配置凭据和 3–5 篇论文，运行首次综述、补写一节、核查引用、停止生成、打开源 PDF。
没有凭据时，这组真实模型验收不能完成。


## 无需 F5 / 无需系统 Node PATH 的启动方法

本机已在 `.tools/node-v24.22.2-win-x64` 安装官方 Node.js 便携版（附带 npm），下载校验通过。
`.tools` 不进入 Git；其他电脑需要自行安装/准备 Node 22.12+，或准备相同的项目内便携版目录。
启动入口优先使用项目内便携版 Node；没有便携版时，使用系统 PATH 中的 Node 和 npm，并检查 Node >=22.12。
新增入口没有修改系统 PATH，普通终端直接输入 node/npm 仍可能找不到，请使用下面入口。
可以用 `.\frontend.cmd ci` 安装前端依赖，用 `.\frontend.cmd run build` 构建前端。

在项目根目录开两个终端，分别运行：

```powershell
.\start-backend.cmd
```

```powershell
.\start-frontend.cmd
```

或用鼠标点击 VS Code 顶部“终端 → 运行任务 → Development: start both”。
前端首次缺少 node_modules 时，脚本先安装依赖。
打开 http://127.0.0.1:5173 （前端），健康检查是 http://127.0.0.1:35549/api/v1/health 。
后端根路径 `/` 没有首页，显示 404 不代表启动失败。
任务在终端持续运行是正常现象；用 Ctrl+C 停止，或用 VS Code 任务终端的终止按钮。
如果端口被占用，请先停止已经启动的服务，不要重复运行。


## DeepSeek 配置示例

以下配置写入本机 `.env`，已有同名项请替换，不要重复添加：

```dotenv
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-flash
MODEL_API_KEY=填写自己的密钥
MODEL_JSON_MODE=true
MODEL_TOKEN_PARAMETER=max_tokens
MODEL_REASONING_EFFORT=none
MODEL_MAX_TOKENS=8000
MODEL_TIMEOUT_SECONDS=180
MAX_REVISION_ROUNDS=1
```

Windows reload 模式的 PDF 子进程兼容问题已修复，并有 Selector 事件循环、超时和取消清理回归测试。
模型 JSON 结构不合格时最多进行一次格式修正；重试后仍无效会报告失败。
