# 固定论文库与测试入口

主题：检索增强生成（RAG）的检索机制与证据可靠性。

本目录的清单、测试问题和脚本可供团队共享。PDF、原文摘录、SQLite、真实运行日志和 `.env` 只保存在本地，已由 `.gitignore` 排除。不要把 `.env`、运行目录或整个项目直接打包发到公共仓库。

## 资料库

完整库在 `data/papers/`，7 篇均为 arXiv 上固定版本的原始论文；下载入口、完整作者、初次提交日期、版本、字节数和 SHA-256 见 `corpus.json`。

| 名称 | 固定版本 | 用途 |
|---|---|---|
| RAG | 2005.11401v4 | 基础检索与生成、Sequence/Token 区别；固定集 |
| Self-RAG | 2310.11511v1 | 按需检索、反思、训练与推理区别；固定集 |
| FLARE | 2305.06983v2 | 生成过程中主动检索；固定集 |
| DPR | 2004.04906v3 | 密集检索背景 |
| FiD | 2007.01282v2 | 多段证据融合 |
| IRCoT | 2212.10509v2 | 多步推理与检索交替 |
| CRAG | 2401.15884v3 | 检索质量评估与纠错 |

文件名年份采用首次 arXiv 提交年份，不等同正式发表年份。测试固定到上述预印本版本，勿静默替换为新版本或会议版。公开可下载不自动意味着允许任意重新分发，需以源页面许可为准。

固定集单独放在 `data/test-corpus/fixed/`，避免把完整库与固定集一起递归索引，重复计算相同文档。运行单篇测试时脚本会在 `data/test-corpus/cases/Gxx/` 准备该题需要的文件。

## 安装与重现

项目原定运行环境为 Python 3.14；本次测试的实际环境与结果记录在 `TEST_REPORT.md`，不能把其他 Python 版本的通过结果当成已经测试过 3.14。

在项目根目录执行；Windows 将 `.venv/bin/python` 替换成 `.venv\Scripts\python.exe`。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python backend/tools/prepare_test_corpus.py --download
.venv/bin/python backend/tools/prepare_test_corpus.py --write-metadata
.venv/bin/python -m pytest backend/tests -q --junitxml=data/manual-test-results/pytest.xml
.venv/bin/python backend/tools/test_corpus_offline.py
```

`prepare_test_corpus.py` 依赖系统 curl。它从固定版本 arXiv 页面取元数据，并下载对应 PDF；现有 PDF 不覆盖。SHA-256 与文件一致不等于全文语义正确。

`--write-metadata` 根据已取得的清单生成与 PDF SHA-256 绑定的 `.metadata.json`。后端只在哈希一致时使用其中题名、作者和年份；仍标为用户提供题录，不能因此获得外部身份 verified。题录修改会使索引刷新。上传单个 PDF 不会自动携带该 sidecar，缺少信息时继续保留未知。

2026-11-14 的修复后行为及分轮复测见 [FIX_REPORT.md](FIX_REPORT.md)。原始 [TEST_REPORT.md](TEST_REPORT.md) 保留为修复前基线。中文查询目前采用有限的研究术语对照与英文查询提示，不是通用翻译或多语言向量检索；比较检索采用文献多样性和可选文档范围。

`test_corpus_offline.py` 使用真正的后端子进程解析器、BM25 索引和 HTTP 路由，检查 PDF 与元数据对应、证据页、引用编号、原始 PDF、上传隔离、空库、无文字 PDF、预算和定向返工。HTTP 流程中的模型角色是明确标记的替身，不对真实模型能力评分。结果保存在 `data/manual-test-results/corpus-offline/results.json`。

检索探针 R01–R06 的语料只有固定三篇、top-k=6，直接测试 BM25 首轮召回；它不代表 Agent 后续使用工具后的最终召回率，也不是整个领域的召回率。探针未通过要保留为发现，不能删题或扩大页码范围来制造通过。

不调用模型的 arXiv 官方服务探针：

```sh
.venv/bin/python backend/tools/probe_academic_sources.py
```

该脚本单独验证真实候选发现、身份查询与 PDF 对应检查；结果在 `data/manual-test-results/academic-source-probe/results.json`。服务集成成功不能等同完整在线综述通过。

## 真实模型测试

在本地 `.env` 配置 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`；模型接口可以接收选定的论文片段。启动后端：

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 35549
```

另一个终端先运行 G01，再运行其余固定题：

```sh
.venv/bin/python backend/tools/test_corpus_live.py --live --cases G01
.venv/bin/python backend/tools/test_corpus_live.py --live --cases G02,G03,G04,G05,G06,G07
```

会产生真实 API 费用。默认每题最多 24 次模型调用、100 次工具调用、300 秒、1 批反馈；实际可能更早结束。失败的调用与格式修复同样计入后端预算。修改预算、模型或提示词后应作为新的实验记录，不覆盖旧结果。

本机曾需要使用 `/etc/ssl/cert.pem` 作为系统 CA；遇到相同证书错误时可用 `SSL_CERT_FILE=/etc/ssl/cert.pem` 启动后端。不要禁用 TLS 校验。

真实结果在 `data/manual-test-results/fixed-live-时间/`：每题 JSON 包含请求、流事件、运行与审计；Markdown 为阅读版，summary.json 汇总执行状态、审核状态、用量和耗时。脚本校验引用与原文页、文件哈希、审核版本和本地模式来源政策。

`execution=passed` 只表示执行及结构检查通过；`task_status=completed` 与 `verification=passed` 才表示后端交付门禁通过。两者都不能代替独立内容核查。

## 内容核查标准

`cases.json` 包含七道固定问题、预期关键点、禁止错误和 PDF 页序号。所有页码从 PDF 第一页开始计数，不按论文印刷页码推断。

逐题记录以下四项，尚未检查时保持 pending：

1. 关键点覆盖：预期点是否回答；未回答不能按正确计。
2. 事实支持：逐条主张回读引用原文，是否支持整条结论及范围。
3. 引用定位：文件、版本、PDF 页序号、摘录是否一致。
4. 边界：是否混淆模型/数据集/指标、编造未报告成本或作普遍排名。

G01–G03 检验机制，G04 检验跨论文覆盖，G05 检验可比性，G06 检验缺失信息，G07 检验不相关材料。G06/G07 的合格结果可以是明确的资料不足；不得要求为凑齐答案而编造正向结论。

在陈述测试结果时区分：自动回归、真实 PDF/替身接口、真实模型运行、独立语义核查、实际浏览器操作。尚未操作的网页、未运行的在线/混合题和未做的单模型对照不能写成已通过。
