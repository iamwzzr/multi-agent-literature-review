import { useState } from 'react'
import type { KeyboardEvent, RefObject } from 'react'
import { ArrowUp, AtSign, BookOpen, Hourglass, MessageSquareText, Square, X } from 'lucide-react'
import type { ReviewRun } from './demo'

type Mention = { start: number; end: number; query: string; index: number }

export function Composer({ input, question, followUp, busy, demo, knowledgeCount, conversations, referenceIds, referenceLimit, disabledMessage, onAssociate, onChange, onReferences, onSubmit, onLibrary, onStop }: {
  input: RefObject<HTMLTextAreaElement | null>
  question: string
  followUp: boolean
  busy: boolean
  demo: boolean
  knowledgeCount: number
  conversations: ReviewRun[]
  referenceIds: string[]
  referenceLimit?: number
  disabledMessage?: string
  onAssociate?: () => void
  onChange: (value: string) => void
  onReferences: (ids: string[]) => void
  onSubmit: () => void
  onLibrary: () => void
  onStop?: () => void
}) {
  const [mention, setMention] = useState<Mention | null>(null)
  const linked = conversations.filter((review) => referenceIds.includes(review.id))
  const atReferenceLimit = referenceLimit !== undefined && linked.length >= referenceLimit
  const options = mention && !atReferenceLimit ? conversations.filter((review) => (
    !referenceIds.includes(review.id) && review.title.toLowerCase().includes(mention.query.toLowerCase())
  )) : []
  const selectedIndex = Math.min(mention?.index ?? 0, options.length - 1)
  const sendLabel = busy ? '正在生成回复' : followUp ? '发送追问' : demo ? '运行示例综述' : '生成综述'

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
    if (!mention || atReferenceLimit) return
    onReferences([...linked.map(({ id }) => id), review.id])
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
          if (busy || disabledMessage || !question.trim()) return
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
            ) : <p>{atReferenceLimit ? `本轮最多引用 ${referenceLimit} 个对话。` : '当前项目没有匹配的对话。'}</p>}
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
        <label htmlFor="research-prompt" className="sr-only">{followUp ? '追问或修改要求' : '研究问题'}</label>
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
          placeholder={followUp ? '继续提问，或告诉 Folio 想改哪里…' : '输入一个研究问题…'}
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
            {onStop ? (
              <button className="send-button" type="button" aria-label="停止生成" title="停止生成" onClick={onStop}><Square size={13} fill="currentColor" /></button>
            ) : (
              <button className="send-button" type="submit" aria-label={sendLabel} aria-keyshortcuts="Enter" title={sendLabel} disabled={busy || Boolean(disabledMessage) || !question.trim()}>
                {busy ? <Hourglass size={16} /> : <ArrowUp size={19} strokeWidth={2} />}
              </button>
            )}
          </div>
        </div>
      </form>
      {disabledMessage ? (
        <div className="composer-caption reading-width">
          <span role="status">{disabledMessage}</span>
          {onAssociate && <button className="context-button" type="button" onClick={onAssociate}>关联当前后端</button>}
        </div>
      ) : <p className="composer-caption reading-width">{busy ? '正在生成回复，可以先写下一条消息' : 'Enter 发送 · Shift + Enter 换行 · @ 引用对话'}</p>}
    </div>
  )
}
