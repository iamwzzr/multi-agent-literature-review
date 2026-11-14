import { AuditSummary } from './AuditSummary'
import { ComparisonTable, reportWarning } from './ReportPreview'
import { memo, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, AtSign, BadgeCheck, BookOpen, Check, ChevronDown, ChevronRight, CircleAlert, FileText, FlaskConical, FolderOpen, History, Info, ListChecks, MessageSquareText, NotebookPen, RotateCw, Settings, Workflow } from 'lucide-react'
import { testPrompts, verificationLabels } from './demo'
import type { ReviewRun, ReviewTurn } from './demo'
import type { ReviewFailure } from './reviewFailure'
import { citationParts, visibleParagraph } from './response'
import { agents, displayAgents, displayAgentStatus } from './workflow'
import type { AgentActivity } from './workflow'

const followUpSuggestions = [
  { label: '提炼要点', prompt: '把每一节精简成要点，保留原有章节和引用。', icon: ListChecks },
  { label: '补充局限', prompt: '补充一节研究局限和后续方向。', icon: NotebookPen },
  { label: '核查引用', prompt: '列出上一轮引用的文献、页码和原文依据。', icon: BadgeCheck },
]

export function sectionAnchor(turn: number, id: string) {
  return 'review-section-' + turn + '-' + id
}

function ConversationLinks({ turn, conversations, onConversation }: {
  turn: ReviewTurn
  conversations: ReviewRun[]
  onConversation: (id: string) => void
}) {
  const linked = conversations.filter(({ id }) => turn.referenceIds?.includes(id))
  if (!linked.length) return null

  return (
    <div className="linked-conversations review-links" role="group" aria-label="引用的对话">
      {linked.map(({ id, title }) => (
        <button type="button" key={id} aria-label={'打开引用对话 ' + title} title={title} onClick={() => onConversation(id)}>
          <AtSign size={13} /><span>{title}</span>
        </button>
      ))}
    </div>
  )
}

function ReportBody({ turn, index, responding, partial, hideSections, activeCitation, onCitation }: {
  turn: ReviewTurn
  index: number
  responding?: boolean
  partial?: boolean
  hideSections?: boolean
  activeCitation?: { turn: number; index: number }
  onCitation: (turn: number, index: number, trigger: HTMLButtonElement) => void
}) {
  if (hideSections && !responding && !turn.reply) return null
  return (
    <div className="review-text">
      {responding && (
        <p className="response-status" role="status">
          <span aria-hidden="true" /> {turn.reply ? '正在接收回复…' : turn.sections.length > 0 ? '正在接收综述片段…' : '等待首段响应…'}
        </p>
      )}
      {turn.reply && <p className="assistant-reply">{turn.reply}</p>}
      {!hideSections && turn.sections.map((section) => (
        <section className="review-section" key={section.id}>
          <h2 id={sectionAnchor(index, section.id)} tabIndex={-1}>{section.heading}</h2>
          {section.paragraphs.map((paragraph, paragraphIndex) => (
            <p key={paragraphIndex}>
              {citationParts(partial ? visibleParagraph(paragraph) : paragraph, turn.evidence.length).map((part, partIndex) => {
                if (typeof part === 'string') return part
                const citation = part - 1
                const selected = activeCitation?.turn === index && activeCitation.index === citation
                return (
                  <button
                    className="inline-citation"
                    type="button"
                    key={partIndex}
                    aria-label={'查看引用 ' + (citation + 1)}
                    aria-expanded={selected}
                    aria-controls={selected ? 'evidence-inspector' : undefined}
                    data-selected={selected}
                    onClick={(event) => onCitation(index, citation, event.currentTarget)}
                  >
                    {citation + 1}
                  </button>
                )
              })}
            </p>
          ))}
        </section>
      ))}
    </div>
  )
}

const PastTurn = memo(function PastTurn({ turn, index, conversations, activeCitation, onConversation, onCitation }: {
  turn: ReviewTurn
  index: number
  conversations: ReviewRun[]
  activeCitation?: { turn: number; index: number }
  onConversation: (id: string) => void
  onCitation: (turn: number, index: number, trigger: HTMLButtonElement) => void
}) {
  const [visited, setVisited] = useState(false)
  return (
    <details className="past-turn" onToggle={(event) => { if (event.currentTarget.open) setVisited(true) }}>
      <summary title={turn.question}>
        <History size={15} /><strong>第 {index + 1} 轮</strong><span>{turn.question}</span><ChevronRight size={14} />
      </summary>
      {visited && (
        <div className="past-turn-body">
          <div className="research-question"><span>你的消息</span><p>{turn.question}</p></div>
          <ConversationLinks turn={turn} conversations={conversations} onConversation={onConversation} />
          <ReportBody turn={turn} index={index} hideSections={turn.reportUnchanged} activeCitation={activeCitation} onCitation={onCitation} />
        </div>
      )}
    </details>
  )
})

export function Review({ review, conversations, runningPhase, responding, connecting, error, onRetry, onRecover, onEditFailure, onSettings, onConfigureProject, activeCitation, onCitation, onConversation, onSuggestion, onPreviewReport, reportVisible }: {
  review: ReviewRun
  conversations: ReviewRun[]
  runningPhase?: AgentActivity
  responding: boolean
  connecting: boolean
  error?: ReviewFailure
  onRetry?: () => void
  onRecover?: () => void
  onEditFailure?: () => void
  onSettings: () => void
  onConfigureProject: () => void
  activeCitation?: { turn: number; index: number }
  onCitation: (turn: number, index: number, trigger: HTMLButtonElement) => void
  onConversation: (id: string) => void
  onSuggestion?: (prompt: string) => void
  onPreviewReport?: () => void
  reportVisible: boolean
}) {
  const [workflowOpen, setWorkflowOpen] = useState(true)
  const history = review.history ?? []
  const followUp = history.length > 0
  const demo = review.source !== 'backend'
  const backendComplete = !demo && !runningPhase && !responding && !connecting && !error
  const needsReview = (review.taskStatus !== undefined && review.taskStatus !== 'completed') || review.verification === 'with_warnings' || review.verification === 'no_evidence'
  const failedAgent = error?.agent ? agents.find(({ id }) => id === error.agent) : undefined
  let workflowStatus = demo ? '流程示例' : '综述已完成'
  if (error) workflowStatus = error.informational ? error.title : '本轮未完成'
  else if (connecting) workflowStatus = '正在连接后端…'
  else if (runningPhase) workflowStatus = runningPhase.title
  else if (responding) workflowStatus = '流式响应中'
  else if (review.reportUnchanged) workflowStatus = '回复完成'
  else if (review.taskStatus === 'blocked') workflowStatus = '任务受阻'
  else if (review.taskStatus === 'partial') workflowStatus = '部分草稿 · 未通过最终审核'
  else if (review.verification) workflowStatus = verificationLabels[review.verification]
  else if (review.mockVerified) workflowStatus = followUp ? '模拟修订完成' : review.mockFlow === 'direct' ? '模拟核查通过' : '模拟复核完成'

  return (
    <article className="review-page reading-width" aria-labelledby="review-title">
      <header className="review-header">
        <div className="review-header-actions">
          <div className="eyebrow"><BookOpen size={14} /> 文献综述 {demo && <><span className="eyebrow-divider" /> 示例会话</>}</div>
          {onPreviewReport && !reportVisible && <button className="context-button" type="button" aria-haspopup="dialog" onClick={onPreviewReport}><FileText size={14} /> 预览综述</button>}
        </div>
        <h1 id="review-title" tabIndex={-1}>{review.title}</h1>
        {!followUp && review.question !== review.title && (
          <div className="research-question">
            <span>研究问题</span>
            <p>{review.question}</p>
          </div>
        )}
      </header>
      {followUp && (
        <>
          <div className="turn-history">
            {history.map((turn, index) => (
              <PastTurn key={index} turn={turn} index={index} conversations={conversations}
                activeCitation={activeCitation?.turn === index ? activeCitation : undefined} onCitation={onCitation} onConversation={onConversation} />
            ))}
          </div>
          <div className="research-question follow-up-question" id="latest-turn">
            <span><MessageSquareText size={14} /> 第 {history.length + 1} 轮 · 你的消息</span>
            <p>{review.question}</p>
          </div>
        </>
      )}
      <p role="status" className="report-warning">{reportWarning(review)}</p>
      <ComparisonTable turn={review} onCitation={(index,trigger)=>onCitation(history.length,index,trigger)}/>
      <AuditSummary turn={review}/>
      <ConversationLinks turn={review} conversations={conversations} onConversation={onConversation} />

      <section className="workflow" aria-label="Agent 协作流程">
        <button className="workflow-toggle" type="button" aria-expanded={workflowOpen} aria-controls="workflow-steps" onClick={() => setWorkflowOpen((open) => !open)}>
          <span className="workflow-icon"><Workflow size={17} /></span>
          <span className="workflow-label">Agent 协作流程<small>3 个 Agent · 程序协调</small></span>
          <span className="workflow-status" aria-live="polite">{backendComplete && needsReview ? <CircleAlert size={14} />
            : (review.mockVerified || backendComplete) && <Check size={14} />}{workflowStatus}</span>
          <ChevronDown className="workflow-chevron" size={15} />
        </button>
        <ol className="workflow-steps" id="workflow-steps" hidden={!workflowOpen}>
          {displayAgents.map((agent) => { const {id,name,task,icon:Icon} = agent; return (
            <li key={id} data-working={displayAgentStatus(agent, runningPhase) === 'working'} data-failed={error?.agent === id}>
              <Icon className="step-icon" size={15} />
              <span><strong>{name}</strong><small>{task}</small></span>
            </li>
          )})}
        </ol>
      </section>
      {error && (
        <div className="review-error" data-informational={error.informational}>
          <div className="review-error-summary" role={error.informational ? 'status' : 'alert'}>
            {error.informational ? <Info size={17} /> : <CircleAlert size={17} />}
            <div>
              <h2>{error.title}</h2>
              <p>{error.message}</p>
            </div>
          </div>
          {(failedAgent || error.providerStatus || review.runId || error.code && !error.informational) && (
            <div className="review-error-details">
              {failedAgent && <span>出错工位 · {failedAgent.name}</span>}
              {error.providerStatus && <span>模型服务 HTTP {error.providerStatus}</span>}
              {error.code && !error.informational && <code>{error.code}</code>}
              {review.runId && <span>任务 <code>{review.runId}</code></span>}
            </div>
          )}
          {onPreviewReport && <p className="review-error-note">上一份完成稿仍可查看和导出。</p>}
          <div className="review-error-actions">
            {onRecover && <button className="context-button" type="button" onClick={onRecover}><History size={14} /> 检查上次任务</button>}
            {onRetry && <button className="context-button" type="button" onClick={onRetry}><RotateCw size={14} /> 重试本轮</button>}
            {onEditFailure && <button className="context-button" type="button" onClick={onEditFailure}><NotebookPen size={14} /> 修改本轮</button>}
            {error.action === 'backend' && <button className="context-button" type="button" onClick={onSettings}><Settings size={14} /> 后端设置</button>}
            {error.action === 'project' && <button className="context-button" type="button" onClick={onConfigureProject}><FolderOpen size={14} /> 配置项目</button>}
          </div>
        </div>
      )}
      {!error && (!runningPhase || (!demo && (review.sections.length > 0 || review.reply))) && (
        <ReportBody
          turn={review}
          index={history.length}
          responding={responding}
          partial={!demo && !backendComplete}
          hideSections={reportVisible && !responding}
          activeCitation={activeCitation}
          onCitation={onCitation}
        />
      )}
      {onSuggestion && (
        <div className="follow-up-actions" role="group" aria-label="快捷追问">
          {followUpSuggestions.map(({ label, prompt, icon: Icon }) => (
            <button key={label} className="context-button" type="button" title={prompt} onClick={() => onSuggestion(prompt)}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}

export function NewReview({ children, question, onPrompt }: { children: ReactNode; question: string; onPrompt: (question: string) => void }) {
  return (
    <section className="new-review-page reading-width" aria-labelledby="new-title">
      <div className="new-review-intro">
        <h1 id="new-title">今天想研究什么？</h1>
        <p>从一个研究问题开始，整理文献、综述与引用证据。</p>
      </div>
      {children}
      <section className="test-samples" aria-labelledby="test-samples-title">
        <div className="test-samples-heading">
          <h2 id="test-samples-title"><FlaskConical size={14} /> 测试样例</h2>
          <span>点选后按 Enter 模拟运行</span>
        </div>
        <div className="prompt-suggestions">
          {testPrompts.map((sample) => (
            <button type="button" key={sample.id} title={sample.question} aria-pressed={question.trim() === sample.question} onClick={() => onPrompt(sample.question)}>
              <span><strong>{sample.label}</strong><small>{sample.detail}</small></span><ArrowUpRight size={14} />
            </button>
          ))}
        </div>
      </section>
    </section>
  )
}
