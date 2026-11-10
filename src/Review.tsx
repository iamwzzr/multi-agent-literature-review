import { useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowUpRight, AtSign, BookOpen, Check, ChevronDown, FlaskConical, Workflow } from 'lucide-react'
import { testPrompts } from './demo'
import type { ReviewRun } from './demo'
import { ResearchOffice } from './Office'
import { agents } from './workflow'
import type { RunPhase } from './workflow'

export function Review({ review, linkedReviews, runningPhase, responding, activeCitation, onCitation, onConversation }: {
  review: ReviewRun
  linkedReviews: ReviewRun[]
  runningPhase?: RunPhase
  responding: boolean
  activeCitation?: number
  onCitation: (index: number, trigger: HTMLButtonElement) => void
  onConversation: (id: string) => void
}) {
  const [workflowOpen, setWorkflowOpen] = useState(true)
  let workflowStatus = '流程示例'
  if (responding) workflowStatus = '流式响应中'
  else if (review.mockVerified) workflowStatus = review.mockFlow === 'direct' ? '模拟核查通过' : '模拟复核完成'

  return (
    <article className={runningPhase ? 'review-page office-run-page office-width' : 'review-page reading-width'} aria-labelledby="review-title">
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

      {runningPhase ? <ResearchOffice phase={runningPhase} /> : (
        <>
          <section className="workflow" aria-label="Agent 协作流程">
            <button className="workflow-toggle" type="button" aria-expanded={workflowOpen} aria-controls="workflow-steps" onClick={() => setWorkflowOpen((open) => !open)}>
              <span className="workflow-icon"><Workflow size={17} /></span>
              <span className="workflow-label">Agent 协作流程<small>{agents.length} 个角色</small></span>
              <span className="workflow-status">{review.mockVerified && <Check size={14} />}{workflowStatus}</span>
              <ChevronDown className="workflow-chevron" size={15} />
            </button>
            <ol className="workflow-steps" id="workflow-steps" hidden={!workflowOpen}>
              {agents.map(({ id, name, task, icon: Icon }) => (
                <li key={id}>
                  <Icon className="step-icon" size={15} />
                  <span><strong>{name}</strong><small>{task}</small></span>
                </li>
              ))}
            </ol>
          </section>
          <div className="review-text">
            {responding && (
              <p className="response-status" role="status">
                <span aria-hidden="true" /> {review.sections.length > 0 ? '正在接收综述片段…' : '等待首段响应…'}
              </p>
            )}
            {review.sections.map((section) => (
              <section className="review-section" key={section.id}>
                <h2 id={section.id} tabIndex={-1}>{section.heading}</h2>
                {section.paragraphs.map((paragraph, paragraphIndex) => (
                  <p key={paragraphIndex}>
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
        </>
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
          <span>点选后按 Enter 运行</span>
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
