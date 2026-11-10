import { useState } from 'react'
import type { KeyboardEvent, RefObject } from 'react'
import { ArrowUp, AtSign, BookOpen, MessageSquareText, X } from 'lucide-react'
import type { ReviewRun } from './demo'

type Mention = { start: number; end: number; query: string; index: number }

export function Composer({ input, question, knowledgeCount, conversations, referenceIds, onChange, onReferences, onSubmit, onLibrary }: {
  input: RefObject<HTMLTextAreaElement | null>
  question: string
  knowledgeCount: number
  conversations: ReviewRun[]
  referenceIds: string[]
  onChange: (value: string) => void
  onReferences: (ids: string[]) => void
  onSubmit: () => void
  onLibrary: () => void
}) {
  const [mention, setMention] = useState<Mention | null>(null)
  const linked = conversations.filter((review) => referenceIds.includes(review.id))
  const options = mention ? conversations.filter((review) => (
    !referenceIds.includes(review.id) && review.title.toLowerCase().includes(mention.query.toLowerCase())
  )) : []
  const selectedIndex = Math.min(mention?.index ?? 0, options.length - 1)

  function trackMention(field: HTMLTextAreaElement) {
    const end = field.selectionStart
    const match = /@([^\s@]*)$/.exec(field.value.slice(0, end))
    if (!match) {
      setMention(null)
      return
    }
    const start = end - match[0].length
    const query = match[1]
    setMention((previous) => previous?.start === start && previous.end === end && previous.query === query
      ? previous
      : { start, end, query, index: 0 })
  }

  function focusAt(position: number) {
    const field = input.current
    requestAnimationFrame(() => {
      if (field !== input.current) return
      field?.focus()
      field?.setSelectionRange(position, position)
    })
  }

  function insertMention() {
    const field = input.current
    if (!field) return
    const { selectionStart: start, selectionEnd: end } = field
    if (question.length - (end - start) >= field.maxLength) return
    onChange(`${question.slice(0, start)}@${question.slice(end)}`)
    setMention({ start, end: start + 1, query: '', index: 0 })
    focusAt(start + 1)
  }

  function attach(review: ReviewRun) {
    if (!mention) return
    onReferences([...referenceIds, review.id])
    onChange(`${question.slice(0, mention.start)}${question.slice(mention.end)}`)
    setMention(null)
    focusAt(mention.start)
  }

  function handleKeys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.nativeEvent.isComposing) return
    if (mention && options.length > 0 && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault()
      const direction = event.key === 'ArrowUp' ? -1 : 1
      setMention({ ...mention, index: (selectedIndex + direction + options.length) % options.length })
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (mention && !event.metaKey && !event.ctrlKey) {
        if (options[selectedIndex]) attach(options[selectedIndex])
      } else event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <div className="composer-dock">
      <form
        className="composer reading-width"
        onSubmit={(event) => {
          event.preventDefault()
          setMention(null)
          onSubmit()
        }}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setMention(null)
        }}
        onKeyDown={(event) => {
          if (mention && event.key === 'Escape') {
            event.stopPropagation()
            setMention(null)
            input.current?.focus()
          }
        }}
      >
        {mention && (
          <div className="mention-panel" id="conversation-mentions" role="group" aria-label="当前项目的可引用对话">
            <strong>引用当前项目的对话</strong>
            {options.length > 0 ? (
              <ul>
                {options.map((review, index) => (
                  <li key={review.id}>
                    <button type="button" data-highlighted={selectedIndex === index} onMouseDown={(event) => event.preventDefault()} onClick={() => attach(review)}>
                      <MessageSquareText size={15} /><span>{review.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : <p>当前项目没有匹配的对话。</p>}
          </div>
        )}
        {linked.length > 0 && (
          <div className="linked-conversations" role="group" aria-label="已引用的对话">
            {linked.map((review) => (
              <button key={review.id} type="button" aria-label={`移除引用 ${review.title}`} title={review.title} onClick={() => onReferences(referenceIds.filter((id) => id !== review.id))}>
                <AtSign size={13} /><span>{review.title}</span><X size={12} />
              </button>
            ))}
          </div>
        )}
        <label htmlFor="research-prompt" className="sr-only">研究问题</label>
        <textarea
          ref={input}
          id="research-prompt"
          value={question}
          rows={2}
          maxLength={400}
          onChange={(event) => {
            onChange(event.target.value)
            trackMention(event.target)
          }}
          onSelect={(event) => trackMention(event.currentTarget)}
          onKeyDown={handleKeys}
          placeholder="输入一个研究问题…"
        />
        <div className="composer-controls">
          <div className="composer-context">
            <button type="button" className="context-button" onClick={onLibrary}>
              <BookOpen size={14} /> 知识库 <span>{knowledgeCount} 个路径</span>
            </button>
            <button type="button" className="context-button mention-button" aria-label="引用对话" aria-expanded={Boolean(mention)} aria-controls={mention ? 'conversation-mentions' : undefined} title="引用当前项目中的对话" onClick={insertMention}>
              <AtSign size={14} /> <span>引用对话</span>
            </button>
          </div>
          <div className="composer-submit">
            <span className="shortcut" aria-hidden="true"><kbd>↵</kbd></span>
            <button className="send-button" type="submit" aria-label="运行示例综述" aria-keyshortcuts="Enter" title="运行示例综述" disabled={!question.trim()}>
              <ArrowUp size={19} strokeWidth={2} />
            </button>
          </div>
        </div>
      </form>
      <p className="composer-caption reading-width">输入 @ 可引用当前项目的其他对话</p>
    </div>
  )
}
