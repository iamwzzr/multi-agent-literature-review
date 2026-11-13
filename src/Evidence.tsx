import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, BookOpen, ChevronRight, FileText, Folder, Link2, List, Quote, SlidersHorizontal, X } from 'lucide-react'
import { fetchSourcePdf, pdfBackendUrl } from './backend'
import type { BackendSettings } from './backend'
import type { Evidence, Paper, ReviewTurn } from './demo'
import type { Project } from './projects'

export type InspectorTab = 'citations' | 'outline'

function paperAttribution({ author, year }: Paper) {
  return year === null ? author : author + ' · ' + year
}

function SourcePdfLink({ evidence, backend }: { evidence: Evidence; backend: BackendSettings }) {
  const [pdf, setPdf] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)
  const blob = useRef<string | null>(null)

  useEffect(() => () => {
    request.current?.abort()
    if (blob.current) URL.revokeObjectURL(blob.current)
  }, [])

  const { pdfUrl, page } = evidence
  if (!pdfUrl || !pdfBackendUrl(pdfUrl)) return null
  if (pdfBackendUrl(pdfUrl) !== backend.url) return <p>连接此引用所属的后端后可查看源 PDF。</p>
  if (backend.token) {
    async function openPdf() {
      if (!pdfUrl || request.current) return
      const controller = new AbortController()
      request.current = controller
      setLoading(true)
      setError('')
      try {
        const file = await fetchSourcePdf(backend, pdfUrl, controller.signal)
        if (controller.signal.aborted) return
        blob.current = URL.createObjectURL(file)
        setPdf(blob.current + '#page=' + page)
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : '无法读取源 PDF。')
      } finally {
        request.current = null
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    return pdf ? (
      <>
        <iframe className="source-pdf-viewer" src={pdf} title={`源 PDF · 第 ${page} 页`} />
        <a className="preview-button source-pdf-link" href={pdf} target="_blank" rel="noopener noreferrer">在新标签页打开 <ArrowUpRight size={14} /></a>
      </>
    ) : (
      <>
        <button className="preview-button source-pdf-link" type="button" disabled={loading} onClick={() => void openPdf()}>
          <FileText size={15} /> {loading ? '读取 PDF…' : `打开源 PDF · 第 ${page} 页`}
        </button>
        {error && <p role="alert">{error}</p>}
      </>
    )
  }
  return (
    <a className="preview-button source-pdf-link" href={pdfUrl} target="_blank" rel="noopener noreferrer">
      <FileText size={15} /> 打开源 PDF · 第 {page} 页 <ArrowUpRight className="preview-arrow" size={14} />
    </a>
  )
}

export function EvidenceInspector({ review, backend, citation, tab, drawer, onTab, onCitation, onPreview, onJump, onClose }: {
  review: ReviewTurn
  backend: BackendSettings
  citation: number
  tab: InspectorTab
  drawer: boolean
  onTab: (tab: InspectorTab) => void
  onCitation: (index: number) => void
  onPreview: (evidence: Evidence) => void
  onJump: (id: string) => void
  onClose: () => void
}) {
  const evidence = review.evidence[citation]
  const close = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (drawer) close.current?.focus()
  }, [drawer])

  return (
    <aside
      className="inspector"
      id="evidence-inspector"
      aria-labelledby="inspector-title"
      onKeyDown={(event) => {
        if (drawer && event.key === 'Escape') onClose()
      }}
    >
      <div className="inspector-header">
        <div>
          <h2 id="inspector-title">证据面板</h2>
          <p>核对引用与原文</p>
        </div>
        <button ref={close} className="icon-button inspector-close" type="button" aria-label="收起证据面板" onClick={onClose}>
          <X size={15} />
        </button>
      </div>
      <div className="segmented" role="group" aria-label="证据面板视图">
        <button type="button" aria-pressed={tab === 'citations'} onClick={() => onTab('citations')}>
          <Link2 size={14} /> 引用 <span>{review.evidence.length}</span>
        </button>
        <button type="button" aria-pressed={tab === 'outline'} onClick={() => onTab('outline')}>
          <List size={15} /> 提纲
        </button>
      </div>

      {tab === 'citations' ? (
        <div className="inspector-content">
          <section className="excerpt-card" aria-label="选中的引用">
            <div className="excerpt-top">
              <span className="citation-tag"><Link2 size={13} /> 引用 {String(citation + 1).padStart(2, '0')}</span>
              <span className="page-tag">第 {evidence.page} 页</span>
            </div>
            <h3 lang={evidence.source ? undefined : 'en'}>{evidence.paper.title}</h3>
            <p className="paper-meta">{paperAttribution(evidence.paper)}{!evidence.source && ' · 示例文献'}</p>
            <blockquote className="excerpt-quote">
              <Quote size={15} aria-hidden="true" />
              <p>{evidence.excerpt}</p>
            </blockquote>
            <button className="preview-button" type="button" onClick={() => onPreview(evidence)}>
              <FileText size={15} /> {evidence.source ? '查看原文摘录' : '查看示例页'} <ArrowUpRight className="preview-arrow" size={14} />
            </button>
            <SourcePdfLink key={evidence.pdfUrl} evidence={evidence} backend={backend} />
          </section>

          <section className="citation-index" aria-labelledby="citation-index-title">
            <div className="inspector-section-heading">
              <h3 id="citation-index-title">引用索引</h3>
              <span>{review.evidence.length} 条</span>
            </div>
            <ol className="citation-list">
              {review.evidence.map(({ paper, page, source }, index) => (
                <li key={index}>
                  <button
                    className="citation-row"
                    type="button"
                    title={paper.title}
                    aria-pressed={citation === index}
                    onClick={() => onCitation(index)}
                  >
                    <span className="citation-number">{String(index + 1).padStart(2, '0')}</span>
                    <span className="citation-info">
                      <strong lang={source ? undefined : 'en'}>{paper.title}</strong>
                      <small>{paper.author} · 第 {page} 页</small>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        </div>
      ) : (
        <div className="inspector-content">
          <div className="inspector-section-heading"><h3>报告章节</h3></div>
          <ol className="outline-list">
            {review.sections.map((section, index) => (
              <li key={section.id}>
                <button className="outline-row" type="button" onClick={() => onJump(section.id)}>
                  <span className="citation-number">{String(index + 1).padStart(2, '0')}</span>
                  {section.heading}
                  <ChevronRight className="outline-arrow" size={15} />
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </aside>
  )
}

export function Library({ project, onConfigure, onPreview }: {
  project: Project
  onConfigure: () => void
  onPreview: (evidence: Evidence) => void
}) {
  const evidenceList = new Map(project.reviews.flatMap((review) => review.evidence.map((evidence) => (
    [(evidence.source ?? 'demo') + ':' + evidence.paper.id, evidence] as const
  ))))

  return (
    <section className="library-page reading-width" aria-labelledby="library-title">
      <div className="eyebrow"><BookOpen size={14} /> {project.name}</div>
      <h1 id="library-title">项目知识库</h1>
      <p className="library-description">工作目录 · {project.folder}</p>
      <section className="library-section" aria-labelledby="library-path-title">
        <div className="library-section-heading">
          <h2 id="library-path-title">知识库路径</h2>
          <button type="button" className="context-button" onClick={onConfigure}><SlidersHorizontal size={14} /> 配置路径</button>
        </div>
        {project.knowledgePaths.length > 0 ? (
          <ul className="library-path-list">
            {project.knowledgePaths.map((path) => <li key={path}><Folder size={16} /><span>{path}</span></li>)}
          </ul>
        ) : <p>为这个项目添加一个或多个知识库路径。</p>}
      </section>
      <section className="library-section" aria-labelledby="library-papers-title">
        <div className="library-section-heading"><h2 id="library-papers-title">引用文献</h2></div>
        {evidenceList.size > 0 ? (
          <ul className="library-list">
            {[...evidenceList].map(([key, evidence]) => (
              <li key={key}>
                <button className="library-paper" type="button" onClick={() => onPreview(evidence)}>
                  <span className="paper-icon"><FileText size={20} /></span>
                  <span className="library-paper-info">
                    <strong lang={evidence.source ? undefined : 'en'}>{evidence.paper.title}</strong>
                    <small>{paperAttribution(evidence.paper)} · {evidence.paper.pages} 页{!evidence.source && ' · 示例'}</small>
                    <span>{evidence.paper.summary}</span>
                  </span>
                  <ArrowUpRight size={16} />
                </button>
              </li>
            ))}
          </ul>
        ) : <p>完成综述后，引用的文献会显示在这里。</p>}
      </section>
    </section>
  )
}

export function PagePreview({ evidence, backend, onClose }: { evidence: Evidence; backend: BackendSettings; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  return (
    <dialog className="page-dialog" ref={dialog} onClose={onClose} aria-labelledby="page-preview-title">
      <div className="dialog-toolbar">
        <span><FileText size={16} /> {evidence.source ? '原文摘录' : '示例原文'} · 第 {evidence.page} 页</span>
        <button className="icon-button" type="button" aria-label={evidence.source ? '关闭原文摘录' : '关闭示例页'} onClick={() => dialog.current?.close()}>
          <X size={17} />
        </button>
      </div>
      <div className="preview-paper">
        {!evidence.source && <div className="eyebrow">示例文献</div>}
        <h2 id="page-preview-title" lang={evidence.source ? undefined : 'en'}>{evidence.paper.title}</h2>
        <p className="paper-meta">{paperAttribution(evidence.paper)}</p>
        <p>{evidence.context}</p>
        <blockquote><mark>{evidence.excerpt}</mark></blockquote>
        <SourcePdfLink key={evidence.pdfUrl} evidence={evidence} backend={backend} />
        <div className="paper-page-number">{evidence.page} / {evidence.paper.pages}</div>
      </div>
    </dialog>
  )
}
