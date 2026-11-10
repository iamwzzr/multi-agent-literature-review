import { useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, AtSign, BookOpen, Check, ChevronDown, Workflow } from 'lucide-react'
import { agents } from './Agents'
import { demoReviews } from './demo'
import type { ReviewRun } from './demo'

export function Review({ review, linkedReviews, runningStep, activeCitation, onCitation, onConversation }: {
  review: ReviewRun
  linkedReviews: ReviewRun[]
  runningStep?: number
  activeCitation?: number
  onCitation: (index: number, trigger: HTMLButtonElement) => void
  onConversation: (id: string) => void
}) {
  const [workflowOpen, setWorkflowOpen] = useState(true)
  const running = runningStep !== undefined

  return (
    <article className="review-page reading-width" aria-labelledby="review-title">
      <header className="review-header">
        <div className="eyebrow"><BookOpen size={14} /> 文献综述 <span className="eyebrow-divider" /> 示例会话</div>
        <h1 id="review-title" tabIndex={-1}>{review.title}</h1>
        {review.question !== review.title && (
          <div className="research-question">
            <span>研究问题</span>
            <p>{review.question}</p>
          </div>
        )}
        {linkedReviews.length > 0 && (
          <div className="linked-conversations review-links" role="group" aria-label="引用的对话">
            {linkedReviews.map((linked) => (
              <button type="button" key={linked.id} aria-label={'打开引用对话 ' + linked.title} title={linked.title} onClick={() => onConversation(linked.id)}>
                <AtSign size={13} /><span>{linked.title}</span>
              </button>
            ))}
          </div>
        )}
      </header>

      <section className="workflow" aria-label="Agent 协作流程">
        <button className="workflow-toggle" type="button" aria-expanded={workflowOpen} aria-controls="workflow-steps" onClick={() => setWorkflowOpen((open) => !open)}>
          <span className="workflow-icon"><Workflow size={17} /></span>
          <span className="workflow-label">Agent 协作流程<small>4 个角色</small></span>
          <span className="workflow-status">{running ? '模拟运行中' : <><Check size={14} /> 已完成</>}</span>
          <ChevronDown className="workflow-chevron" size={15} />
        </button>
        <ol className="workflow-steps" id="workflow-steps" hidden={!workflowOpen}>
          {agents.map(({ id, name, task, icon: Icon }, index) => (
            <li key={id} aria-current={runningStep === index ? 'step' : undefined}>
              <Icon className="step-icon" size={15} />
              <span><strong>{name}</strong><small>{task}</small></span>
            </li>
          ))}
        </ol>
      </section>

      {running ? <p className="run-placeholder">示例综述会在四个 Agent 完成工作后显示。</p> : (
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
                        aria-label={'查看引用 ' + (citation + 1)}
                        aria-expanded={activeCitation === citation}
                        aria-controls={activeCitation === citation ? 'evidence-inspector' : undefined}
                        data-selected={activeCitation === citation}
                        onClick={(event) => onCitation(citation, event.currentTarget)}
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
      )}
    </article>
  )
}

export function NewReview({ children, onPrompt }: { children: ReactNode; onPrompt: (question: string) => void }) {
  return (
    <section className="new-review-page reading-width" aria-labelledby="new-title">
      <div className="new-review-intro">
        <h1 id="new-title">今天想研究什么？</h1>
        <p>从一个研究问题开始，整理文献、综述与引用证据。</p>
      </div>
      {children}
      <div className="prompt-suggestions" role="group" aria-label="示例研究问题">
        {demoReviews.map((review) => (
          <button type="button" key={review.id} title={review.question} onClick={() => onPrompt(review.question)}>
            <span>{review.title}</span><ArrowUpRight size={13} />
          </button>
        ))}
      </div>
    </section>
  )
}
