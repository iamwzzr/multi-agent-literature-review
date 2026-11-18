# SkillHub 调研与原文定位第一轮优化

日期：2026-11-18。只修改后端；没有安装第三方技能、运行第三方脚本、引入新依赖或改变前端。

## 技能调研

检索了公开 SkillHub 目录和原作者仓库。“Skill Hub”存在多个同名项目，本次实际核查的是 NVlabs/Skill2Env 的 SkillHub 条目及下列原作者公开文件，不能代表所有技能市场。

- [alterlab-literature-review](https://github.com/NVlabs/Skill2Env/blob/main/SkillHub/skills/alterlab-literature-review/SKILL.md)：可借鉴筛选流程、证据表与综述完整性检查。其范围比本项目第一版更广，不能安装后就声称实现正式系统综述。
- [research-summarizer](https://github.com/NVlabs/Skill2Env/blob/main/SkillHub/skills/product-team/research-summarizer/SKILL.md)：可借鉴结构化摘要与多来源比较；它本身不能替代检索和精确定位。
- [Anthropic PDF](https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md)：提供解析、布局、表格及 OCR 工具思路；需要评估具体解析器在项目语料和 Python 3.14 上的效果。
- [research-evidence](https://github.com/sidiangongyuan/codex-skills-library/blob/main/skills/research-evidence/SKILL.md)：可借鉴身份、引用与主张支持的分层核验和覆盖限制说明。

这些是开发/Agent 的工作流程资料，不能通过安装到开发工具就自动赋予 FastAPI 项目新能力。本轮只借鉴思路，核心定位代码自行实现，没有复制或执行技能仓库脚本。第三方条目可能依赖自己的工具和运行环境，不能直接注入项目生产提示词。

## 代码中确认的不足

1. 证据 location 只有 page，没有稳定的片段起止位置。
2. 按 1600 字符切片，可能引用远大于实际主张所需的文字。
3. 原文回读用 find 取第一个匹配；重复文本不能精确消歧。
4. 空格/换行折叠后的位置没有映射回原始提取文本。
5. 检索以 BM25 和有限中英文别名为主；精确字符定位与语义召回是两个独立问题。

## 本轮已实现

- 块级记录规范化页面文本的 start/end，修复切片边缘空格偏移。
- EvidenceDraft 和 record_evidence 可选 quote，允许登记更短的连续原文；默认 null 保持完整片段兼容。
- 短引文必须真实、唯一地出现在所选片段中，不允许改写或模糊匹配冒充精确证据；注册由程序回填位置。
- 保存 page/start/end/basis；审核回读使用位置验证，不再盲目采用首次匹配。
- 无位置的历史引文若重复出现，返回 ambiguous 而非强行声称唯一定位。
- 新接口重新读取实际 PDF、验证哈希、提供规范化位置、原始提取文本字符位置、提取文本行号以及 exact/prefix/suffix。
- 新证据流事件增加 evidenceId 和 location；旧前端忽略额外字段也能继续工作。新增可选字段不会破坏旧报告的重复核验。

## 定位接口

GET /api/v2/projects/{project_id}/evidence/{evidence_id}/location

沿用后端访问令牌和项目隔离。evidence_id 从新报告 evidence 项的 evidenceId 或运行审计对象取得。它是对象关联 ID，不是正文展示引用编号。

响应包含 status=matched/ambiguous/missing/mismatch、document_id、content_hash、parser_version、PDF 页序号和 candidates。

每个 candidate 的 start/end 是 normalize 后页面的 0 基半开区间，basis=normalized-page-text-v1；raw_start/raw_end 是该解析器原始页面文本的字符区间；line_start/line_end 是提取文本行号，不等同于 PDF 版面行号；selector 包含 exact/prefix/suffix。page 是 1 基 PDF 页序号，不是论文印刷页码。

原文文件变化返回 409；其他项目对象不可读取。旧证据没有 start 时允许重新匹配，但有多个候选不得视为唯一定位。原文解析次序错误时，这些位置只准确绑定解析文本，不能宣称版面阅读顺序正确。

supports_pdf_coordinates=false：当前未实现 PDF bbox/quad 高亮。前端可以据此显示更准确的文本位置，但尚不能直接在画布上框出句子；本次没有修改前端。

## 验证范围

- 新增测试：换行和空格映射、重复文本消歧、拒绝虚构引文、片段边界、短引文注册、定位接口、项目隔离、原文变化拦截。
- 实际论文：Self-RAG 30 页 95 个片段，RAG 19 页 64 个片段；共 49 页 159 个锚点的原文字符映射全部一致。
- 实际结果保存在本机 data/manual-test-results/precision-anchor-check.json，不提交 PDF 或原文摘录。
- 本轮没有运行付费模型任务，没有测量检索召回率或报告质量提升，不能从字符定位成功推断这些指标提高。

## 后续优先级

1. PDF 坐标与高亮：解析器输出词/字符 bbox，保留阅读顺序和坐标映射；先用双栏、页眉脚、跨行断词、重复段落等固定样例评测，再接前端 PDF 高亮。需先评估解析器准确性、许可证和依赖兼容性。
2. 检索召回：在现有 BM25 上与跨语言 embedding、融合排序和重排做对照，测 Recall@k、正确论文/页码命中及代价，不以安装一个 RAG 技能代替实现。
3. 证据语义：人工标注“主张—原文句—条件—页码”，测试正确定位但不支持主张的反例，继续区分身份核实与结论支持。
4. 表格与扫描件：保留表头、单位、脚注及解析置信度；OCR 作为可选能力，不能把 OCR 结果当作无误原文。
5. 完整性：资料缺口覆盖、比较条件一致性、模型/工具预算和缓存命中统计；沿用有上限返工，不扩大到无限补证。

不自动推送本轮代码，也不静默改写旧报告或已审核证据。

## 最终回归结果

最终完整后端回归：121 passed，13 个既有 LangSmith 弃用警告，无失败。新增 7 项定位测试。旧报告核验的可选字段兼容问题已修复。新增接口、短引文与重复文本行为已通过自动化测试；49 页 159 个真实片段通过离线字符映射校验。未执行付费模型生成或 PDF 画布高亮视觉验收。

## 后续更新

本文件为先前阶段记录。100 篇库下载、后端修复和最终 147 项回归及真实模型结果见 [后续验收报告](CORPUS_100_BACKEND_UPGRADE_2026-11-18.md)，不要把本文件中的旧资料缺口或旧测试数当成当前最终状态。
