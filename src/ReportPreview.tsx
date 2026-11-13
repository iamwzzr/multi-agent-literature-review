import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, Download, FileText, Printer, X } from 'lucide-react'
import { verificationLabels } from './demo'
import type { Evidence, ReviewRun, ReviewTurn } from './demo'
import { citationParts } from './response'
import './report-preview.css'

export function reportVersions(review: ReviewRun) {
  return [...(review.history ?? []), review].flatMap((turn, turnIndex) => (
    !turn.reportUnchanged && turn.sections.some(({ paragraphs }) => paragraphs.some((paragraph) => paragraph.trim()))
      ? [{ turn, turnIndex }]
      : []
  ))
}

export function latestReportSection(id: string) {
  return 'latest-report-section-' + id
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

function ReportDocument({ review, turn, prefix, references, onCitation }: {
  review: ReviewRun
  turn: ReviewTurn
  prefix: string
  references: ReturnType<typeof reportReferences>
  onCitation?: (index: number, trigger: HTMLButtonElement) => void
}) {
  const question = review.history?.[0]?.question ?? review.question
  const titleId = prefix + '-document-title'
  const bibliographyId = prefix + '-bibliography-title'
  return (
    <article className="report-document" aria-labelledby={titleId}>
      <header className="report-document-header">
        {review.source !== 'backend' && <p className="report-demo-label">示例综述</p>}
        <h1 id={titleId}>{review.title}</h1>
        {question !== review.title && <p className="report-document-question">研究问题 · {question}</p>}
        {!onCitation && turn.verification && <p className="report-document-question">核验状态 · {verificationLabels[turn.verification]}</p>}
      </header>
      {turn.sections.map(({ id, heading, paragraphs }) => (
        <section className="report-document-section" key={id}>
          <h2 id={onCitation ? latestReportSection(id) : undefined} tabIndex={onCitation ? -1 : undefined}>{heading}</h2>
          {paragraphs.map((paragraph, index) => (
            <p key={index}>{citationParts(paragraph, turn.evidence.length).map((part, partIndex) => {
              if (typeof part === 'string') return part
              if (onCitation) return (
                <button
                  key={partIndex}
                  className="report-citation"
                  type="button"
                  aria-label={'查看证据 ' + part}
                  onClick={(event) => onCitation(part - 1, event.currentTarget)}
                >[{part}]</button>
              )
              const referenceId = prefix + '-reference-' + part
              return (
                <a
                  key={partIndex}
                  className="report-citation"
                  href={'#' + referenceId}
                  aria-label={'参考文献 ' + part}
                  onClick={(event) => {
                    event.preventDefault()
                    const reference = document.getElementById(referenceId)
                    reference?.focus({ preventScroll: true })
                    reference?.scrollIntoView({ block: 'nearest' })
                  }}
                >[{part}]</a>
              )
            })}</p>
          ))}
        </section>
      ))}
      {references.length > 0 && (
        <section className="report-bibliography" aria-labelledby={bibliographyId}>
          <h2 id={bibliographyId}>参考文献</h2>
          <ol>
            {references.map(({ number, evidence }) => (
              <li id={prefix + '-reference-' + number} value={number} key={number} tabIndex={-1}>
                <span>{referenceText(evidence)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  )
}

export function ReportPanel({ review, turn, version, busy, drawer, hidden, onCitation, onPreview, onClose }: {
  review: ReviewRun
  turn: ReviewTurn
  version: number
  busy: boolean
  drawer: boolean
  hidden: boolean
  onCitation: (index: number, trigger: HTMLButtonElement) => void
  onPreview: () => void
  onClose: () => void
}) {
  const reader = useRef<HTMLDivElement>(null)
  const close = useRef<HTMLButtonElement>(null)
  const references = useMemo(() => reportReferences(turn), [turn])

  useEffect(() => {
    if (reader.current) reader.current.scrollTop = 0
  }, [review.id, version])

  useEffect(() => {
    if (drawer && !hidden) close.current?.focus()
  }, [drawer, hidden])

  return (
    <aside
      className="report-panel"
      id="report-panel"
      aria-labelledby="latest-report-heading"
      hidden={hidden}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <header className="inspector-header">
        <div>
          <h2 id="latest-report-heading">最新综述</h2>
          <p role="status">第 {version} 版{busy ? ' · 新版生成中' : ''}</p>
          {turn.verification && <p className="report-verification">{verificationLabels[turn.verification]}</p>}
        </div>
        <div className="report-panel-actions">
          <button className="context-button" type="button" aria-haspopup="dialog" onClick={onPreview}>
            预览与导出 <ArrowUpRight size={13} />
          </button>
          <button ref={close} className="icon-button inspector-close" type="button" aria-label="收起综述面板" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
      </header>
      <div className="report-panel-reader" ref={reader}>
        <ReportDocument review={review} turn={turn} prefix="latest-report" references={references} onCitation={onCitation} />
      </div>
    </aside>
  )
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
  const versions = useMemo(() => reportVersions(review), [review])
  const [version, setVersion] = useState(versions.length - 1)
  const selected = versions[version].turn
  const references = useMemo(() => reportReferences(selected), [selected])
  const demo = review.source !== 'backend'
  const question = review.history?.[0]?.question ?? review.question
  const filename = fileTitle(review.title) + (versions.length > 1 ? ' - 第 ' + (version + 1) + ' 版' : '')

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
      selected.verification ? '核验状态 · ' + verificationLabels[selected.verification] : '',
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
          {versions.length > 1 && (
            <select aria-label="综述版本" value={version} onChange={(event) => {
              setVersion(Number(event.target.value))
              if (reader.current) reader.current.scrollTop = 0
            }}>
              {versions.map(({ turnIndex }, index) => (
                <option key={turnIndex} value={index}>
                  {index === versions.length - 1 ? '最新版本 · ' : ''}第 {index + 1} 版
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
        <ReportDocument review={review} turn={selected} prefix="report" references={references} />
      </div>
    </dialog>,
    document.body,
  )
}
