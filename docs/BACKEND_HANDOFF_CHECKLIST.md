# 后端首版完成清单（周芯豪）

日期：2026-11-11
分支：`backend/zhouxinhao/bootstrap`

本次在合并队友 frontend 分支后，完成 Python 3.14 后端业务、前后端联调和 Windows 启动工具。前端页面沿用队友的实现。

## 已完成

- [x] 对齐 Folio v1 接口：健康检查、NDJSON 流式综述、源论文 PDF，以及运行记录查询。
- [x] 本地 PDF 按页解析、文本分块及 BM25 关键词检索，保留论文标识、原文片段和 PDF 页序。
- [x] 项目索引隔离、允许目录校验，以及论文变更/删除后的索引更新。
- [x] 接入真实 DeepSeek API：本地环境配置、JSON 结构校验、超时、有限重试及一次格式修正。
- [x] 实现 Coordinator、Researchers、Synthesizer、Reviewer；前端对应显示规划、检索、分析、撰写、核验五类活动。
- [x] 核验失败生成定向补查任务，修订后再核验；支持配置修订上限和调用预算。
- [x] 核对摘录与原文、引用编号和页码；未获支持的段落不交付，未解决问题明确列出。
- [x] 支持历史上下文、完整修订稿，以及满足条件时保留原稿的引用审查回复。
- [x] SQLite 保存任务状态、分工、检索结果、研究发现、草稿版本、核验意见和最终稿。
- [x] 实现任务取消、断连清理、并发限制、请求大小限制；重启后将未完成任务标记为中断。
- [x] 修复 Windows reload 模式的 PDF 子进程问题；新增前后端启动脚本、VS Code 任务和开发指南。
- [x] 新增 23 项自动化测试，以及 GitHub Actions 后端检查配置（云端执行结果另看 Actions）。

## 本次自测结果

- 后端：23 passed，0 failed；有 1 条上游 TestClient/httpx 弃用提示，不影响当前测试。
- 依赖一致性、Python 语法检查及前端 TypeScript/Vite 构建：通过。
- 本地前端、健康检查、CORS 预检、源 PDF 接口：通过。
- 已完成一次两篇真实论文 + DeepSeek 的生成，得到 7 个章节、12 条证据，并完成定向补查流程。
- 推送前重新核对该报告的 12 条摘录，均存在于源 PDF 对应页；此次复查未新增模型调用。
- 报告状态为 with_warnings，仍有证据缺口。摘录/页码匹配不等于全部结论的学术准确性已经得到人工确认。

## 主要代码

- `backend/app/main.py`：HTTP 接口、流式响应、错误和并发控制。
- `backend/app/library.py`、`pdf_worker.py`：PDF 索引、页码、检索及源文件访问。
- `backend/app/model.py`、`config.py`：模型适配、配置及输出校验。
- `backend/app/workflow.py`：Agent 调度、定向反馈、核验和最终稿交付。
- `backend/app/store.py`：SQLite 共享工作区及运行产物。
- `backend/app/schemas.py`、`errors.py`：数据结构及业务错误格式。
- `backend/tests/`：业务、真实 TCP 断连、Windows 事件循环及解析进程清理测试。
- `start-backend.cmd`、`start-frontend.cmd`、`frontend.cmd`、`.vscode/`：启动和测试入口。

## 队友如何启动

1. 切到本分支，安装 Python 3.14 和 Node.js 22.12+（建议 Node 24）。
2. 在仓库根目录创建 `.venv`，安装 `backend/requirements.txt`。
3. 首次复制 `.env.example` 为 `.env`，按 `docs/LOCAL_SETUP.md` 填写自己的模型配置。
4. 自行把文字型 PDF 放进 `data/papers`。
5. 两个终端分别运行 `.\start-backend.cmd`、`.\start-frontend.cmd`；前端缺依赖时脚本自动安装。
6. 前端打开 `http://127.0.0.1:5173`，后端地址填 `http://127.0.0.1:35549`，关闭演示模式。
7. 项目工作目录填本机仓库绝对路径，知识库填 `data/papers`。不要沿用另一台电脑的绝对目录。

详细配置、测试命令和运行边界见 [本地开发指南](LOCAL_SETUP.md)。

## 尚未完成

- [ ] 更大论文集的人工准确性评估、失败案例分析及性能评估。
- [ ] OCR、表格/公式/图像理解、向量检索及文献元数据补全。
- [ ] 用户鉴权、公共多人部署、持久化任务队列和自动恢复。
- [ ] 逐项解决报告中的证据缺口；模型核验不能代替人工审阅。

密钥、PDF、运行数据库、虚拟环境、Node 便携工具和构建产物均不提交。共享的是代码和配置模板。
