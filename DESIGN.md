# 设计基线（用户提供 PDF 的文本提取）

此文件描述设计要求，不是实现或测试结果。

## 原 PDF 第 1 页

三 Agent 学术文献研究助手:设计说明
版本: v1
日期: 2026-11-12
阶段: 设计草案
实现与验证状态: 未实现、未运行、未测试。
本文规定拟实现行为。接又名称、字段、预算和流程均为设计约定。示例 ID 只用于解释协
议,不代表已存在的论文、证据或运行结果。
1. 目标与设计原则
系统围绕明确的研究问题,处理本地上传或联网发现的文献,建立原文证据,形成综述报
告,并检查报告中的事实、引用和推论。
设计原则:
1.固定使用 Researcher、Reporter、Reviewer 三个 Agent。
2.Agent 负责需要语义理解和判断的任务。
3.程序负责权限、身份状态、结构校验、路由、预算和版本。
4.事实性主张应能追溯到实际材料和原文位置。
5.无法确认的信息保持未知,不用推测填充。
6.停止执行、执行成功和审核通过分别表达。
7.所有实际能力与性能都需要在实现后验证。
2. 需求基线
编号 需求 设计完成条件
REQ-0
1 支持 local、online、hybrid 来源模式由程序执行;本地元数据联网单独控 制
REQ-0
2 在线论文强制身份核验 未核验在线候选不能作为正式引用
REQ-0
3 保存来源与原文定位 证据绑定实际内容、位置和版本
REQ-0
4 Researcher 输出结构化证据包含发现、原文依据、条件和缺又
REQ-0
5
Reporter 综合报告并反馈缺
又 主张关联证据,补证请求具体可执行

## 原 PDF 第 2 页

3. 总体架构与模块边界
三个 Agent 拟使用 LangChain create_agent 分别配置提示词、工具、运行上下文与结构
化输出。外层由普通 Python 编排,不另设调度 Agent。
LangChain 的 Agent 内部运行时与外层项目编排是不同层次。项目阶段、证据和报告应独立
保存;不能将 Agent 会话记忆视为整个项目状态。
技术接又参考资料见第 13 节。
4. 任务与来源政策
4.1 TaskSpec
REQ-0
6 Reviewer 回读原文核验 检查事实、引用、条件和推论范围
REQ-0
7 支持定向反馈与返工 证据问题与报告问题分别路由
REQ-0
8
保证 schema、ID 和版本一
致 无效引用被拒绝,审核绑定具体产物
REQ-0
9 控制预算、停止与失败 有限重试和返工,不把失败转换为通过
REQ-1
0 保存项目状态并隔离上下文项目进度不依赖一份共享聊天历史
REQ-1
1 提供可追溯交付物 报告、比较表、证据、来源及未解决项齐全
REQ-1
2 验收和实验如实记录 结果可复核,未执行项目保持未执行
模块 职责 是否使用独立 Agent
任务入又 收集问题、范围、文件和模式 否
Python 编排器执行阶段、处理路由、管理预算和版 本 否
Researcher 研究与证据提取 是
Reporter 综合、写作和覆盖缺又判断 是
Reviewer 原文核验和问题定位 是
文献接入服务搜索、身份查询、内容获取和解析 否
项目存储 论文、文档、证据、报告、审核和日 志 否
引用与导出服
务 校验引用,渲染书目信息和交付格式否

## 原 PDF 第 3 页

在线候选的身份核验不能通过关闭 allow_local_metadata_lookup 绕过。该开关只
影响上传文献。
4.2 模式规则
来源模式由程序注入。论文正文或模型输出不能修改该模式。
本地语料模式不等于系统完全离线;云端模型和 embedding 的使用是独立配置。
5. 论文身份与内容核验
5.1 核验对象
系统分别检查:
1.身份: 是否存在与候选相符的公开对象记录。
2.内容对应: 实际读取的文档是否属于该论文及版本。
3.语义支持: 原文是否支持报告主张。
字段 类型 要求
task_id string 程序生成
question string 必填,主研究问题
subquestions list 每项包含唯一 ID 和具体问题
source_mode enum local、online、hybrid
allow_local_metadata_look
up boolean默认 false,仅控制上传资料的元数据联网 核验
scope object 时间、领域、纳排条件、比较维度
uploaded_file_ids list[strin g] 没有上传时为空
output_requirements object 报告语言、结构、必要交付物
budget object 调用、时间、资料和反馈限制
模式 允许行为
local,元数据联网关
闭 只读取上传资料,不调用文献搜索或外部元数据服务
local,元数据联网开
启
可核验上传文献身份,不能因此自动搜索并纳入新论
文
online 搜索候选,强制核验身份,再获取与使用可用内容
hybrid 使用上传资料,并对缺又执行受控联网检索

## 原 PDF 第 4 页

前两项主要由工具和程序执行;第三项由 Reviewer 判断,并通过人工评测检验其准确性。
5.2 身份状态
在线材料只有达到 verified,才能取得正式在线引用资格。
未外部核验的上传稿可在来源政策允许时使用,但必须保留“用户提供、公开身份未外部核
实”的标识。身份未知不能自动写成“未发表”;发表状态也可能是未知。
5.3 核验流程
1.从实际搜索结果或上传文件中取得候选书目信息。
2.优先使用 DOI 或 arXiv ID 精确查询。
3.没有上述标识时,寻找出版机构、会议论文集或机构仓储中的明确对象页面。
4.比较标识符、标题、作者和版本信息。
5.保存查询来源、时间、原始返回及匹配结论。
6.由程序更新身份状态。
通过规则为:至少一条权威对象记录存在且身份相符。无需固定要求两个数据库同时收录。
匹配时允许大小写、排版、作者缩写及出版日期类型的合理差异。重大冲突不能用标题相似
度强行消除。
必须保留的边界:
• 单个接又查不到不证明论文不存在。
• 没有 DOI 不证明论文不存在。
• 真实 DOI 搭配另一篇论文的标题属于身份冲突。
• 普通搜索摘要只作为发现线索。
状态 含义
candidate已发现,未完成核验
verified有可追溯的权威记录,身份匹配且无未解决重大冲 突
unresolve
d 信息不足、未找到、服务失败或核验尚不能完成
conflict有明确的标识符、标题、作者等不一致证据

## 原 PDF 第 5 页

• 预印本与正式版需要记录实际版本,不能自动混合实验数据。
• 已确认身份不代表已经同行评审或研究结论可靠。
• 元数据对象类型还必须符合任务的纳入标准。
5.4 内容对应检查
保存文件哈希、取得来源、文档版本和解析版本。优先从文档头部识别标题、作者及本篇标
识,不能把参考文献中的 DOI 当成本篇 DOI。
内容检查结果至少区分:
•matched:与已核验论文记录对应。
•unresolved:信息不足,暂不能确认。
•mismatch:明确属于其他论文或版本。
•user_provided:作为用户提供文档使用,未确认其外部身份。
mismatch 内容不能为目标论文生成证据。解析失败也不能通过模型补写原文、页码或数
值。
只有摘要时,允许使用摘要明确提供的信息,并标记证据范围。不得推断摘要未包含的实验
细节。
6. Agent 契约
6.1 共同约定
所有调用结果包含:
status 只表示本轮执行情况。Reviewer 的审核判断通过单独的 verdict 表达。
程序生成并校验 ID、来源状态、版本和预算。Agent 无权自行覆盖这些字段。
字段 类 型 含义
task_i
d
strin
g 对应任务
statusenu m success、partial、failed
errorslist错误码、原因、是否可重试及相关对 象

## 原 PDF 第 6 页

6.2 Researcher
目标: 找到相关材料,提取可回查原文的事实、实验条件和限制。
输入: TaskSpec、已有论文和证据、查询记录、补证或纠错任务、剩余预算。
工具: 项目论文列表、受控论文搜索、内容获取、文献内检索、原文读取、证据登记。
输出:
paper_ids: list[string]
evidence_ids: list[string]
coverage_by_question: list
unresolved_gaps: list
issue_responses: list
status: success | partial | failed
errors: list
程序保存结果并形成证据快照后,交给 Reporter。
限制: 不得直接写入 verified;不得编造论文或摘录;不得把摘要当作全文;不得把无
结果写成领域内没有研究;不得自行修改研究范围。
停止条件: 完成指定检索与取证任务,或明确返回材料不足、部分完成、预算耗尽和执行
失败。无需为了凑齐论文数量持续搜索。
6.3 Reporter
目标: 按研究问题综合材料,生成报告、比较、结论和限制,并提出必要补证请求。
输入: TaskSpec、允许使用的证据、论文记录、报告历史、审核问题和剩余预算。
工具: 证据查询、论文记录读取、已有原文读取。开放式论文发现交给 Researcher。
输出:
report_content: string or structured sections
claims: list[Claim]
comparison_table: structured table
evidence_requests: list
limitations: list
issue_responses: list
status: success | partial | failed
errors: list
报告版本由程序保存时生成。草稿交 Reviewer;补证请求交 Researcher。
限制: 不得修改原文摘录;不得编造来源或引用 ID;不得把上传稿说成已核实出版物;不
得把推论或研究建议写成已证实事实。

## 原 PDF 第 7 页

停止条件: 草稿达到可审核状态后返回;发现必要缺又时提交具体请求。信息不足应形成
限制说明,不能以确定语气填充空白。
6.4 Reviewer
目标: 回读原文,检查事实、引用支持、实验可比性和结论范围。
输入: 指定报告版本、证据快照、主张清单、原文位置、身份核验记录和上一轮问题。
工具: 报告读取、证据读取、论文记录与核验日志读取、原文读取。
输出:
reviewed_report_version: integer
reviewed_evidence_snapshot_id: string
verdict: pass | revise | undetermined
claim_checks: list
issues: list[Issue]
unchecked_claim_ids: list[string]
status: success | partial | failed
errors: list
限制: 不得仅依据 Researcher 的摘要审核;不得直接覆盖证据或报告;不得提升论文身份
状态;不得因预算耗尽强制通过。
停止条件: 完成必要检查后返回。发现错误并返回 revise 属于成功执行审核;必要材料
缺失或检查未完成时返回 undetermined。
Reviewer 也可能判断错误。其他角色可以用原文回应问题,由 Reviewer 重新核对。
7. 数据与交接协议
7.1 核心记录
对象 必要字段
PaperRecor
d
paper_id、来源记录、标题、作者、年份、标识符、发表状态、
identity_status、核验记录
DocumentRe
cord
document_id、paper_id、来源、版本、内容哈希、解析版本、内容
范围、对应状态
EvidenceCa
rd
evidence_id、document_id、span_ids、原文、定位、发现、实
验条件、限制Claimclaim_id、正文陈述、类型、evidence_ids、适用范围
ReportDraf
t
report_id、report_version、evidence_snapshot_id、正
文、主张、比较表、限制ReviewResu
lt
审核版本、证据快照、判断、问题及未检查项

## 原 PDF 第 8 页

字段约定:
• ID:程序生成的非空字符串。
• 年份、作者或出版信息:无法确认时允许为空,不猜测。
• 原文位置:对象,可包含页码、章节、表格或文本范围。
• 实验条件:结构化对象,包含已报告的数据集、模型、指标、预算等;未报告项为
空。
• 主张类型:finding、synthesis、proposal。
• 证据范围:full_text、abstract、user_document。
• 仅有题录元数据时,不能生成实验结论证据。
7.2 审核问题
{
  "issue_id": "I003",
  "claim_id": "C007",
  "evidence_ids": ["E012"],
  "owner": "reporter",
  "severity": "blocking",
  "problem": "原文结论依赖特定数据集,报告省略了该条件。",
  "required_fix": "补充适用条件并收窄结论。",
  "status": "open"
}
owner 为 researcher 或 reporter。问题状态为 open、addressed、
resolved。执行修改后可标为 addressed,最终是否解决由后续审核记录确认。
7.3 版本规则
• 原始文件和已登记证据保留历史,修正不得静默覆盖。
• 修正证据产生新记录或新版本,并形成新的 evidence_snapshot_id。
• 正文、表格或引用发生实质变化时,递增 report_version。
• 审核结果只对所记录的报告和证据快照有效。
• 同一研究的不同文档版本分别保留。只有存在明确关联依据时才合并研究实体关系。
• Agent 不能通过自行填写一个 ID 创建可信来源。

## 原 PDF 第 9 页

8. 工具接又
以下是拟实现的项目接又,不是 LangChain 自带论文工具。
工具统一返回:
status: ok | empty | error
data: object or list
error: null or {code, message, retryable, attempts}
对批量工具,data 必须保留每一项的状态。调用完成不等于每篇候选都已通过。
•empty 只用于成功执行但没有相应结果。
•搜到候选但全部尚未核验时,应返回候选处理情况,不能伪装成没有搜到论文。
•工具只能访问当前项目允许的对象。
•record_evidence 从已有片段回填原文与位置,不能接受模型自行编造的摘录作
为原始材料。
9. 协作、状态与预算
9.1 项目状态
工具 输入 输出及限制
list_project_paper
s
当前项目上下文 项目内已登记论文及状态
search_verified_pa
pers
查询、筛选条件、结果上
限
已核验论文、待核验项、冲突项及
逐项原因lookup_uploaded_me
tadata 上传文档 ID 外部匹配记录;仅在本地元数据联 网允许时调用
fetch_paper_conten
t
已登记论文 ID 可用内容、对应检查结果和失败原
因search_document问题、文档范围 原文片段 ID、内容、位置及版本
read_original文档 ID、位置 原文和必要上下文
record_evidence原文片段 ID、提取发现、 实验条件 程序登记的证据 ID
query_evidence子问题、筛选条件 当前模式允许使用的证据
get_paper_record论文 ID 题录、来源、核验及内容状态
get_verification_l
og
论文 ID 核验依据、时间和错误记录
状态 含义
created任务已建立

## 原 PDF 第 10 页

“当前证据无法判断”可以是准确结论。是否完成任务取决于约定的输出要求,而不是每个问
题是否都有肯定答案。
没有任何可用材料时,不应生成貌似正常的文献综述,应返回资料不足及已有检索记录。
9.2 路由规则
9.3 初始预算提案
researchin
g 检索、阅读或补证
drafting生成或修改报告
reviewing核对当前版本
completed满足交付条件
partial有可用产物,但任务或最终审核未完 成
blocked需要补充资料、权限或范围决定
failed执行失败,未形成可用结果
cancelled用户取消
情况 路由
初步证据准备完成 Researcher → Reporter
Reporter 提出必要补证请求 Researcher → Reporter → Reviewer
Reviewer 发现证据缺失或提取错
误 Researcher → Reporter → Reviewer
Reviewer 发现表述或引用使用错
误 Reporter → Reviewer
两类问题并存 先补证,再改写,再审核
当前版本通过且程序校验通过 交付
达到上限仍有问题 返回 partial 或 blocked,保留未解决 项
配置 建议初 值
每任务文档上限 20
最大反馈批次 2
瞬态工具故障最大尝试数,包含首
次 3
单次 Agent 调用的模型调用上限 12

## 原 PDF 第 11 页

这些是控制参数提案,不代表已证明系统能在上述资源内处理完指定数量的论文。实现联调
后可以调整,但实验开始前必须冻结配置。
一轮反馈定义为:程序接受一批新的补证或修改问题,并启动一次返工。该批次内
Researcher、Reporter、Reviewer 的执行属于同一轮。新的回退请求消耗下一轮预算,不能借
用同一轮无限循环。
调用失败和 schema 修复也计入资源消耗。工具内部的额外请求、摘要和重排调用应记账,
不能从成本统计中消失。
超时、限流等可重试错误采用有限重试;权限或配置错误不得盲目重复调用。
9.4 最终交付检查
必须同时满足:
review.verdict == pass
review.reviewed_report_version ==
current_report.report_version
review.reviewed_evidence_snapshot_id ==
current_report.evidence_snapshot_id
blocking_issues == 0
all_references_allowed_by_source_policy == true
审核通过后不再调用 Reporter 增加事实。格式导出必须保持已经审核的正文与引用映射。
10. 上下文、配置与运行记录
每个 Agent 只获得当前任务所需的资料:
• Researcher:研究问题、已有材料、查询历史、待补问题。
• Reporter:证据、论文信息、报告要求、写作问题。
• Reviewer:当前稿件、主张、原文、来源记录和未解决问题。
项目 ID、来源政策、预算和权限由程序通过运行上下文提供。文献内容只能作为研究材
料,不能改变系统规则。
提示词、模型配置、输出 schema 和工具版本应记录版本。日志至少包含:
单次 Agent 调用的工具调用上限 30
整个任务模型调用上限 60
整个任务工具调用上限 150
整个任务运行时间上限 600 秒

## 原 PDF 第 12 页

run_id、task_id、阶段、Agent、工具
输入与输出对象ID、开始/结束时间
模型和提示词版本、调用状态
token和工具使用量、错误与重试
报告版本、证据快照、问题ID
日志避免保存明文凭证。原始文件、证据和报告按项目隔离。
11. 设计决策记录
13. 技术与方法参考
以下资料用于支持设计选型,不代表已经集成或运行:
1.LangChain Agents
2.LangChain Structured Output
3.LangChain Tools
4.LangChain Middleware
5.PaperQA:证据检索与来源关联参考。
6.dzhng/deep-research:迭代研究过程参考。
7.OpenScholar:反馈与补检索参考。
8.STORM:问题展开与报告组织参考。
9.GPT Researcher:研究与报告流程参考。
编号 决策 理由
ADR-0
1 三个角色,程序负责调度 形成清晰的研究、写作和审核责任
ADR-0
2
LangChain Agent+普通 Python 编
排 保持接又与路由容易理解
ADR-0
3 身份核验状态由程序管理 防止模型自报“已核实”
ADR-0
4 本地来源与在线来源采用明确政策兼容上传稿件,同时保证在线引用要 求
ADR-0
5 原文、证据、报告和审核绑定版本防止旧审核用于新内容
ADR-0
6 参考文献从登记记录渲染 降低自由生成题录造成的错误
ADR-0
7 有限反馈、有限工具循环 保证成本与终止条件可控制

## 原 PDF 第 13 页

10.Crossref REST API
11.arXiv API Manual
12.DataCite REST API
