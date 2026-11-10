import { useState } from 'react'
import type { RefObject } from 'react'
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  FilePenLine,
  ListTree,
  Search,
  ShieldCheck,
  Workflow,
} from 'lucide-react'
import { demoEvidence, demoReviews } from './demo'
import type { ReviewRun } from './demo'

const roles = [
  { name: '协调员', task: '拆解研究问题', icon: ListTree },
  { name: '研究员', task: '检索文献证据', icon: Search },
  { name: '撰写员', task: '综合研究发现', icon: FilePenLine },
  { name: '审阅员', task: '核对主张与引用', icon: ShieldCheck },
]

export function Review({ review, activeCitation, onCitation }: {
  review: ReviewRun
  activeCitation?: number
  onCitation: (index: number) => void
}) {
  const [workflowOpen, setWorkflowOpen] = useState(true)

  return (
    <article className="review-page reading-width" aria-labelledby="review-title">
      <header className="review-header">
        <div className="eyebrow"><BookOpen size={14} /> 文献综述 <span className="eyebrow-divider" /> 示例报告</div>
        <h1 id="review-title">{review.title}</h1>
        <div className="research-question">
          <span>研究问题</span>
          <p>{review.question}</p>
        </div>
      </header>

      <section className="workflow" aria-label="Agent 协作流程">
        <button
          className="workflow-toggle"
          type="button"
          aria-expanded={workflowOpen}
          aria-controls="workflow-steps"
          onClick={() => setWorkflowOpen((open) => !open)}
        >
          <span className="workflow-icon"><Workflow size={17} /></span>
          <span className="workflow-label">Agent 协作流程<small>4 个角色</small></span>
          <span className="workflow-status"><Check size={14} /> 已完成</span>
          <ChevronDown className="workflow-chevron" size={15} />
        </button>
        <ol className="workflow-steps" id="workflow-steps" hidden={!workflowOpen}>
          {roles.map(({ name, task, icon: Icon }) => (
            <li key={name}>
              <Icon className="step-icon" size={15} />
              <span><strong>{name}</strong><small>{task}</small></span>
            </li>
          ))}
        </ol>
      </section>

      <div className="review-text">
        {review.sections.map((section) => (
          <section className="review-section" key={section.id}>
            <h2 id={section.id} tabIndex={-1}>{section.heading}</h2>
            {section.paragraphs.map((paragraph) => (
              <p key={paragraph}>
                {paragraph.split(/(\[\[\d+\]\])/).map((part, index) => {
                  const match = /^\[\[(\d+)\]\]$/.exec(part)
                  const citation = match ? Number(match[1]) - 1 : -1
                  return review.evidence[citation] ? (
                    <button
                      className="inline-citation"
                      type="button"
                      key={index}
                      aria-label={`查看引用 ${citation + 1}`}
                      data-selected={activeCitation === citation}
                      onClick={() => onCitation(citation)}
                    >
                      {citation + 1}
                    </button>
                  ) : part
                })}
              </p>
            ))}
          </section>
        ))}
      </div>
    </article>
  )
}

export function NewReview({ onPrompt }: { onPrompt: (question: string) => void }) {
  return (
    <section className="new-review-page reading-width" aria-labelledby="new-title">
      <span className="new-review-icon"><BookOpen size={28} strokeWidth={1.5} /></span>
      <div className="eyebrow">新的研究会话</div>
      <h1 id="new-title">从一个研究问题开始</h1>
      <p>提出你想梳理的问题，查看 Agent 的协作流程和带页码的引用。</p>
      <div className="prompt-suggestions" aria-label="示例研究问题">
        {demoReviews.map((review) => (
          <button type="button" key={review.id} onClick={() => onPrompt(review.question)}>
            <span>{review.question}</span><ArrowUpRight size={15} />
          </button>
        ))}
      </div>
    </section>
  )
}

const shortcutModifier = /Mac/.test(navigator.userAgent) ? '⌘' : 'Ctrl'

export function Composer({ input, question, onChange, onSubmit, onLibrary }: {
  input: RefObject<HTMLTextAreaElement | null>
  question: string
  onChange: (value: string) => void
  onSubmit: () => void
  onLibrary: () => void
}) {
  return (
    <div className="composer-dock">
      <form className="composer reading-width" onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}>
        <label htmlFor="research-prompt" className="sr-only">研究问题</label>
        <textarea
          ref={input}
          id="research-prompt"
          value={question}
          rows={2}
          maxLength={400}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder="输入一个研究问题…"
        />
        <div className="composer-controls">
          <button type="button" className="context-button" onClick={onLibrary}>
            <BookOpen size={14} /> 示例文献库 <span>{demoEvidence.length} 篇</span>
          </button>
          <div className="composer-submit">
            <span className="shortcut" aria-hidden="true"><kbd>{shortcutModifier}</kbd><kbd>↵</kbd></span>
            <button
              className="send-button"
              type="submit"
              aria-label="运行示例综述"
              aria-keyshortcuts="Meta+Enter Control+Enter"
              title="运行示例综述"
              disabled={!question.trim()}
            >
              <ArrowUp size={19} strokeWidth={2} />
            </button>
          </div>
        </div>
      </form>
      <p className="composer-caption reading-width">使用示例文献演示研究流程</p>
    </div>
  )
}
