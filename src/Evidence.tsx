import { useEffect, useRef } from 'react'
import { ArrowUpRight, BookOpen, ChevronRight, FileText, Folder, Link2, List, Quote, SlidersHorizontal, X } from 'lucide-react'
import type { Evidence, ReviewRun } from './demo'
import type { Project } from './projects'

export type InspectorTab = 'citations' | 'outline'

export function EvidenceInspector({ review, citation, tab, drawer, onTab, onCitation, onPreview, onJump, onClose }: {
  review: ReviewRun
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
            <h3 lang="en">{evidence.paper.title}</h3>
            <p className="paper-meta">{evidence.paper.author} · {evidence.paper.year} · 示例文献</p>
            <blockquote className="excerpt-quote">
              <Quote size={15} aria-hidden="true" />
              <p>{evidence.excerpt}</p>
            </blockquote>
            <button className="preview-button" type="button" onClick={() => onPreview(evidence)}>
              <FileText size={15} /> 查看示例页 <ArrowUpRight className="preview-arrow" size={14} />
            </button>
          </section>

          <section className="citation-index" aria-labelledby="citation-index-title">
            <div className="inspector-section-heading">
              <h3 id="citation-index-title">引用索引</h3>
              <span>{review.evidence.length} 条</span>
            </div>
            <ol className="citation-list">
              {review.evidence.map(({ paper, page }, index) => (
                <li key={paper.id}>
                  <button
                    className="citation-row"
                    type="button"
                    title={paper.title}
                    aria-pressed={citation === index}
                    onClick={() => onCitation(index)}
                  >
                    <span className="citation-number">{String(index + 1).padStart(2, '0')}</span>
                    <span className="citation-info">
                      <strong lang="en">{paper.title}</strong>
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
  const evidenceList = [...new Map(project.reviews.flatMap((review) => review.evidence.map((evidence) => [evidence.paper.id, evidence] as const))).values()]

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
        <div className="library-section-heading"><h2 id="library-papers-title">示例文献</h2></div>
        {evidenceList.length > 0 ? (
          <ul className="library-list">
            {evidenceList.map((evidence) => (
              <li key={evidence.paper.id}>
                <button className="library-paper" type="button" onClick={() => onPreview(evidence)}>
                  <span className="paper-icon"><FileText size={20} /></span>
                  <span className="library-paper-info">
                    <strong lang="en">{evidence.paper.title}</strong>
                    <small>{evidence.paper.author} · {evidence.paper.year} · {evidence.paper.pages} 页</small>
                    <span>{evidence.paper.summary}</span>
                  </span>
                  <ArrowUpRight size={16} />
                </button>
              </li>
            ))}
          </ul>
        ) : <p>运行一篇示例综述后，它使用的示例文献会显示在这里。</p>}
      </section>
    </section>
  )
}

export function PagePreview({ evidence, onClose }: { evidence: Evidence; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  return (
    <dialog className="page-dialog" ref={dialog} onClose={onClose} aria-labelledby="page-preview-title">
      <div className="dialog-toolbar">
        <span><FileText size={16} /> 示例原文 · 第 {evidence.page} 页</span>
        <button className="icon-button" type="button" aria-label="关闭示例页" onClick={() => dialog.current?.close()}>
          <X size={17} />
        </button>
      </div>
      <div className="preview-paper">
        <div className="eyebrow">示例文献</div>
        <h2 id="page-preview-title" lang="en">{evidence.paper.title}</h2>
        <p className="paper-meta">{evidence.paper.author} · {evidence.paper.year}</p>
        <p>{evidence.context}</p>
        <blockquote><mark>{evidence.excerpt}</mark></blockquote>
        <div className="paper-page-number">{evidence.page} / {evidence.paper.pages}</div>
      </div>
    </dialog>
  )
}
