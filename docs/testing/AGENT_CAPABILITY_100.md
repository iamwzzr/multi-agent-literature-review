# 100 篇论文库与 Agent 能力测试

## 论文库和运行入口

该论文库由 100 篇公开全文组成，共 2,092 个 PDF 页。论文覆盖 RAG 方法 25 篇、检索 22 篇、问答基准 20 篇、引用与评估 20 篇、研究 Agent 13 篇，包含原有 7 篇固定版本。清单记录题名、作者、版本、来源 URL、页数和文件 SHA-256。运行复建脚本会从 arXiv 下载论文并将 PDF 存入 `data/papers-100/`。 [固定版本清单](corpus-100.json) · [arXiv 元数据接口](https://info.arxiv.org/help/api/user-manual.html)

首次运行时，在项目根目录用项目的 Python 环境复建论文库，再启动测试：

```sh
.venv/bin/python backend/tools/prepare_corpus_100.py --download
.venv/bin/python backend/tools/test_corpus_100.py
```

复建同时生成与文件哈希绑定的题录，下载文件与清单不一致时会报告错误。单独运行 `prepare_corpus_100.py` 可校验已有文件。Windows 使用 `.venv\Scripts\python.exe`。沿用 [本机启动说明](../LOCAL_SETUP.md) 配置前后端，在 Folio 的项目设置里选择实际工作目录，并将知识库路径填为 `data/papers-100`。已有的环境配置需要允许至少 100 篇和 2,092 页。项目示例配置为 `MAX_PAPERS=100` 和 `MAX_TOTAL_PAGES=4000`。

目录内的 PDF 先建页级索引。超过本轮精读预算时，BM25 根据研究问题和已提供的子问题在全库排序，挑选候选原文。三 Agent 随后在候选范围内检索和核查。上传文档在预算紧张时优先进入候选，混合模式在有空间时留出一个补充线上资料的槽位。运行日志中的 `local_library_selection` 记录索引数量、实际精读候选及预算。单次精读上限为 40 篇，本测试固定为 10 篇。

## 固定题目

| 用例 | 测什么 | 通过时应观察到的结果 |
| --- | --- | --- |
| L01 | 精读与原文页码 | 分清 RAG-Sequence 和 RAG-Token 的边缘化，引用 Lewis 等人的定义。 |
| L02 | 三篇机制比较 | 区分原始 RAG、Self-RAG 和 FLAREdirect 的触发条件，三种机制各有对应原文。 |
| L03 | 新增论文的综合 | 说明 MuSiQue 的题目构造与 MultiHop-RAG 的新闻知识库及支撑证据。 |
| L04 | 指标与引用核验 | 区分 ALCE 引文覆盖和 RAGChecker 检索主张覆盖，解释两种指标的评价对象。 |
| L05 | 同缩写论文辨别 | 独立引用两篇 CRAG 论文，归属检索评估器与评测基准。 |
| L06 | 证据不足与适用范围 | 判断原论文能否支持统一条件下的人民币成本，指出资料缺口并保留未知值。 |
| L07 | 深处文献的召回和原文复核 | 查到 WebThinker，解释其两个模块，结论能回到对应原文。 |

[题目、标准要点和原文页](agent-capability-cases.json) 使用 PDF 从第一页开始计数。标准要点、目标论文和页码供评价使用，Agent 请求只包含研究问题、开放的子问题和预算。每题在同一完整 100 篇库中运行。

## 三 Agent 评分

| 环节 | 观察项 | 分数 |
| --- | --- | --- |
| Researcher | 引用目标论文，找到合适的原文页，正确提取适用条件。 | 0–3 |
| Reporter | 覆盖题目要求，区分不同研究和实验条件，保留未知值。 | 0–4 |
| Reviewer | 回读原文，确认关键主张与引用对应，发现问题时要求修订或保留待确认状态。 | 0–3 |

对照每题的 `expected` 和 `must_not` 评分。每项可按完整、部分、缺失给分。关键主张造假、错论文或捏造金额时，该题判失败并记录原因。L06 接受理由明确的证据不足，按能否识别缺口、回应原问题及避免猜测评分。若首轮草稿可靠，无须产生返工记录。记录模型调用、工具次数、用量、耗时、审核状态，以及有无返工。相同语义可以由另一原文页支持，人工回读后可补认该引用，机器的固定页分数仍保留。

## 运行与解读

离线测试使用实际 PDF 和生产检索器，核对 11 个标准证据页，输出大库候选覆盖、前六条证据页覆盖和版本绑定的 HTTP 测试。HTTP 测试使用预定输出的 Agent，检索与引用取自真实文件。每次执行写入 `data/manual-test-results/corpus-100-offline.json`。 [离线测试结果](corpus-100-offline-result.json)

本机索引了 100 篇、2,092 页、6,814 个片段。六道有指定来源的题目共有 11 个目标文献项。仅用题干时，10 个进入前 10 篇候选，加入固定子问题时，11 个进入候选。未限定候选的全库前 6 条片段，按题干命中 2/11 个指定页，按固定英文检索词命中 4/11。原文页仍需由 Researcher 进一步定位。HTTP 层成功取回文件名顺序第 99 篇的 WebThinker，引用第 4 页并校验 PDF 哈希，该用例的人工标准页为第 2 页。

真实模型测试通过本机后端发起。先选 L01、L06 做快速检查，命令含 `--live` 时会调用已配置的模型：

```sh
.venv/bin/python backend/tools/test_corpus_live.py --live --suite corpus-100 --cases L01,L06
.venv/bin/python backend/tools/test_corpus_live.py --live --suite corpus-100
```

每题上限 24 次模型响应、100 次工具调用、300 秒和一批反馈。脚本保存运行 ID、引用页和结构检查到 `data/manual-test-results/corpus-100-live-*/`。真实模型的语义评分需要人工回查，查看每题的 `task_status`、审核结论和人工评分。与上一版做对照时使用同一模型、题目和预算。
