import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Download, FileText, Printer, X } from 'lucide-react'
import type { Evidence, ReviewRun, ReviewTurn } from './demo'
import { citationParts } from './response'
import './report-preview.css'

export function hasReport(turn: ReviewTurn) {
  return turn.sections.some(({ paragraphs }) => paragraphs.some((paragraph) => paragraph.trim()))
}

function reportReferences(turn: ReviewTurn) {
  const used = new Set<number>()
  for (const section of turn.sections) {
    for (const paragraph of section.paragraphs) {
      for (const part of citationParts(paragraph, turn.evidence.length)) {
        if (typeof part === 'number') used.add(part)
      }
    }
  }
  return turn.evidence.flatMap((evidence, index) => used.has(index + 1) ? [{ number: index + 1, evidence }] : [])
}

function referenceText({ paper, page }: Evidence) {
  const attribution = paper.year === null ? paper.author : paper.author + ' (' + paper.year + ')'
  return attribution + ' · ' + paper.title + ' · 第 ' + page + ' 页'
}

function markdownText(text: string) {
  return text.replace(/[\\*_[\]<>#]/g, '\\$&')
}

function fileTitle(title: string) {
  const safe = title.replace(/[<>:"/\\|?*\u0000-\u001F]/gu, ' ').trim()
  return Array.from(safe).slice(0, 72).join('').replace(/[ .]+$/, '') || '文献综述'
}

export function ReportPreview({ review, onClose }: { review: ReviewRun; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const reader = useRef<HTMLDivElement>(null)
  const turns = [...(review.history ?? []), review]
  const [version, setVersion] = useState(turns.length - 1)
  const selected = turns[version]
  const references = reportReferences(selected)
  const demo = review.source !== 'backend'
  const question = turns[0].question
  const filename = fileTitle(review.title) + (turns.length > 1 ? ' - 第 ' + (version + 1) + ' 轮' : '')

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  useEffect(() => {
    const previousTitle = document.title
    document.title = filename
    return () => { document.title = previousTitle }
  }, [filename])

  function downloadMarkdown() {
    const sections = selected.sections.map(({ heading, paragraphs }) => [
      '## ' + markdownText(heading.replace(/\s+/g, ' ')),
      ...paragraphs.map((paragraph) => citationParts(paragraph, selected.evidence.length)
        .map((part) => typeof part === 'number' ? '[' + part + ']' : markdownText(part)).join('')),
    ].join('\n\n'))
    const bibliography = references.map(({ number, evidence }) => '- [' + number + '] ' + markdownText(referenceText(evidence)))
    const markdown = [
      '# ' + markdownText(review.title.replace(/\s+/g, ' ')),
      demo ? '> 示例综述' : '',
      question !== review.title ? '研究问题 · ' + markdownText(question) : '',
      ...sections,
      bibliography.length ? '## 参考文献\n\n' + bibliography.join('\n') : '',
    ].filter(Boolean).join('\n\n') + '\n'

    const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = filename + '.md'
    dialog.current?.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return createPortal(
    <dialog ref={dialog} className="page-dialog report-preview" aria-labelledby="report-preview-title" onClose={onClose}>
      <header className="report-preview-toolbar">
        <span id="report-preview-title"><FileText size={16} /> 综述预览</span>
        <div className="report-preview-actions">
          {turns.length > 1 && (
            <select aria-label="综述版本" value={version} onChange={(event) => {
              setVersion(Number(event.target.value))
              if (reader.current) reader.current.scrollTop = 0
            }}>
              {turns.map((turn, index) => (
                <option key={index} value={index} disabled={!hasReport(turn)}>
                  {index === turns.length - 1 ? '最新版本 · ' : ''}第 {index + 1} 轮
                </option>
              ))}
            </select>
          )}
          <button type="button" className="context-button" onClick={downloadMarkdown}><Download size={14} /> 下载 Markdown</button>
          <button type="button" className="context-button report-print-button" title="打开打印预览，可另存为 PDF" onClick={() => window.print()}>
            <Printer size={14} /> 保存 PDF
          </button>
        </div>
        <button className="icon-button report-preview-close" type="button" aria-label="关闭综述预览" onClick={() => dialog.current?.close()}><X size={17} /></button>
      </header>
      <div className="report-preview-reader" ref={reader}>
        <article className="report-document" aria-labelledby="report-document-title">
          <header className="report-document-header">
            {demo && <p className="report-demo-label">示例综述</p>}
            <h1 id="report-document-title">{review.title}</h1>
            {question !== review.title && <p className="report-document-question">研究问题 · {question}</p>}
          </header>
          {selected.sections.map(({ id, heading, paragraphs }) => (
            <section className="report-document-section" key={id}>
              <h2>{heading}</h2>
              {paragraphs.map((paragraph, index) => (
                <p key={index}>{citationParts(paragraph, selected.evidence.length).map((part, partIndex) => (
                  typeof part === 'number' ? (
                    <a
                      key={partIndex}
                      className="report-citation"
                      href={'#report-reference-' + part}
                      aria-label={'参考文献 ' + part}
                      onClick={(event) => {
                        event.preventDefault()
                        const reference = document.getElementById('report-reference-' + part)
                        reference?.focus({ preventScroll: true })
                        reference?.scrollIntoView({ block: 'nearest' })
                      }}
                    >[{part}]</a>
                  ) : part
                ))}</p>
              ))}
            </section>
          ))}
          {references.length > 0 && (
            <section className="report-bibliography" aria-labelledby="report-bibliography-title">
              <h2 id="report-bibliography-title">参考文献</h2>
              <ol>
                {references.map(({ number, evidence }) => (
                  <li id={'report-reference-' + number} value={number} key={number} tabIndex={-1}>
                    <span>{referenceText(evidence)}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </article>
      </div>
    </dialog>,
    document.body,
  )
}
