# V1 前端实现与验收记录

基于 frontend 分支，按 docs/FRONTEND_V1_HANDOFF.md 对接。文档实际拼写为 FRONTEND，不是 FRONTED。

## 已实现
- 本地、联网（arXiv）、混合互斥选择；默认本地；online 清空知识库目录与上传 ID。可选 online_query。
- 原始 application/pdf 上传、访问令牌、文件选择/拖放、上传中/成功/失败、30 MB/20 文件限制；上传期间禁用提交；按项目及后端保存文件 ID 与名称。
- three_agent 架构与固定 research_budget；生成/上传使用 v2，健康检查/运行恢复/PDF 使用 v1。
- 三个模型 Agent：Researcher 合并 search/analysis，Reporter 对应 writing，Reviewer 对应 verification；planner 仅显示为程序协调，保留传输协议 ID。
- 保留 taskStatus 与 verification；运行恢复保留审核、未解决问题、比较表、用量、报告/证据版本。顶层 completed 不替代 task_status。
- 比较表列及适用条件、未知/未报告值、数字引用点击；参考文献包含仅在比较表中出现的引用。
- 预览/Markdown/打印 PDF 保留草稿、阻断、版本不一致警示、比较记录、来源说明。后端在正文 unresolved 章节提供的停止原因仍保留。

## 验证
- npm run build：通过。
- node tests/frontend-contract.mjs：通过，覆盖来源请求、带令牌的原始上传、比较引用、null、比较表独有引用、状态/版本警示、三 Agent 状态归并、跨后端上传隔离及 blocked 结果恢复。
- 后端分支现有测试：68 通过；1 项 TCP 断连测试因其子进程覆盖 PYTHONPATH，找不到临时安装的 uvicorn 而失败。未修改后端源代码。

## 待团队联调
真实模型服务地址/凭据尚待提供；真实论文完整生成、本地/联网/混合补证、取消、PDF 页码与最终人工质量验收尚未完成。前端测试使用接口替身，不等于真实模型验收。

上传接口无服务器列表/删除能力，当前只保存浏览器已上传记录。模型配置保留在后端，不在页面输入模型密钥。
