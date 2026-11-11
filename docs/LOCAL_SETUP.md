# 本地开发环境（Windows / Python 3.14）

## 已配置

- 本地分支：`backend/zhouxinhao/bootstrap`（尚未提交或推送）
- 虚拟环境：项目根目录 `.venv`
- 后端代码：`backend/app`
- 本地论文：`data/papers`，PDF 不提交 Git
- 运行数据：`data/runtime`，不提交 Git
- 模型配置：根目录 `.env`，密钥不提交 Git

## VS Code 启动

打开项目根目录，按 F5，选择 `Backend: FastAPI (Python 3.14)`。
停止调试用 Shift+F5。若需要停止 reload 子进程，在该终端按 Ctrl+C。
或者使用菜单“终端 → 运行任务 → Backend: start”。不要重复启动占用同一端口。

浏览器打开 http://127.0.0.1:8000/health 或 http://127.0.0.1:8000/docs 。

## 终端启动（在项目根目录）

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

## 队友重建环境

安装标准 CPython 3.14，创建 `.venv`。如果 `py -3.14` 不可用，使用 python.exe 的完整路径。

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

`requirements.in` 记录直接依赖，`requirements.txt` 记录此次环境实际安装版本。
依赖升级后需验证并重新生成 requirements.txt。

## 当前实现边界

现在仅有可启动的 FastAPI 骨架和 /health，不包含论文检索、任务队列或 Agent 实现。
未配置真实模型和密钥，未进行模型 API 调用。
Python 扩展的自动终端激活暂不启用，避免依赖 PowerShell 脚本执行策略；F5 使用明确的虚拟环境路径。

## 下一步

1. 确认前端实际端口并修改 .env 中 FRONTEND_ORIGIN。
2. PDF 按页解析，保存 paper_id、page_number、text；扫描 PDF 后续另做 OCR。
3. 实现本地检索，返回带论文和页码的证据。
4. 约定任务、证据卡片、草稿版本、信息请求、核验结果的数据结构。
5. 实现创建任务/查询任务接口及 SQLite 持久化。
6. 接入 Coordinator、Researchers、Synthesizer、Reviewer，并实现定向补充任务和有限修订。
7. 最终结果使用核验对应的草稿版本，并列出未解决问题。
