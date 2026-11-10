import { useEffect, useRef, useState } from 'react'
import {
  BookOpen,
  ChevronRight,
  LibraryBig,
  MessageSquareText,
  PanelLeft,
  PanelRight,
  Plus,
  X,
} from 'lucide-react'
import { createDemoReview, demoEvidence, demoReviews } from './demo'
import type { Evidence, ReviewRun } from './demo'
import { EvidenceInspector, Library, PagePreview } from './Evidence'
import type { InspectorTab } from './Evidence'
import { Composer, NewReview, Review } from './Review'

type View = { kind: 'review'; id: string } | { kind: 'new' } | { kind: 'library' }

const folioIcon = `${import.meta.env.BASE_URL}folio.svg`

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches)

  useEffect(() => {
    const media = matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [query])

  return matches
}

export function App() {
  const sidebarInline = useMediaQuery('(width > 820px)')
  const inspectorInline = useMediaQuery('(width > 1120px)')
  const [reviews, setReviews] = useState(demoReviews)
  const [view, setView] = useState<View>({ kind: 'review', id: demoReviews[0].id })
  const [sidebarOpen, setSidebarOpen] = useState(sidebarInline)
  const [inspectorOpen, setInspectorOpen] = useState(inspectorInline)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('citations')
  const [citation, setCitation] = useState(0)
  const [question, setQuestion] = useState('')
  const [preview, setPreview] = useState<Evidence | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const scrollPane = useRef<HTMLElement>(null)
  const sidebarToggle = useRef<HTMLButtonElement>(null)
  const inspectorToggle = useRef<HTMLButtonElement>(null)

  const activeReview = view.kind === 'review' ? reviews.find((review) => review.id === view.id) : undefined
  const title = activeReview?.title ?? (view.kind === 'library' ? '文献库' : '新建综述')
  const showInspector = inspectorOpen && Boolean(activeReview)
  const sidebarDrawer = sidebarOpen && !sidebarInline
  const inspectorDrawer = showInspector && !inspectorInline
  const viewKey = activeReview?.id ?? view.kind

  useEffect(() => {
    if (scrollPane.current) scrollPane.current.scrollTop = 0
  }, [viewKey])

  function navigate(next: View) {
    setView(next)
    setCitation(0)
    setInspectorTab('citations')
    if (!sidebarInline) setSidebarOpen(false)
    if (!inspectorInline) setInspectorOpen(false)
    if (sidebarDrawer && next.kind !== 'new') requestAnimationFrame(() => scrollPane.current?.focus())
  }

  function newReview() {
    setQuestion('')
    navigate({ kind: 'new' })
    requestAnimationFrame(() => input.current?.focus())
  }

  function submitQuestion() {
    const value = question.trim()
    if (!value) return
    const review = createDemoReview(value)
    setReviews((previous) => [review, ...previous])
    navigate({ kind: 'review', id: review.id })
    setQuestion('')
  }

  function showCitation(index: number) {
    setCitation(index)
    setInspectorTab('citations')
    setInspectorOpen(true)
  }

  function closeSidebar() {
    setSidebarOpen(false)
    requestAnimationFrame(() => sidebarToggle.current?.focus())
  }

  function closeInspector() {
    setInspectorOpen(false)
    inspectorToggle.current?.focus()
  }

  function jumpToSection(id: string) {
    if (inspectorDrawer) setInspectorOpen(false)
    requestAnimationFrame(() => {
      const heading = document.getElementById(id)
      heading?.focus({ preventScroll: true })
      heading?.scrollIntoView({ block: 'start' })
    })
  }

  return (
    <div className="app-window">
      {!sidebarDrawer && !inspectorDrawer && <a className="skip-link" href="#work-area">跳至工作区</a>}
      {sidebarOpen && (
        <>
          <button className="sidebar-scrim" type="button" tabIndex={-1} aria-label="关闭侧边栏" onClick={closeSidebar} />
          <Sidebar
            view={view}
            reviews={reviews}
            drawer={sidebarDrawer}
            onNavigate={navigate}
            onNew={newReview}
            onClose={closeSidebar}
          />
        </>
      )}
      <div className="workspace" inert={sidebarDrawer}>
        <header className="toolbar">
          <div className="toolbar-leading">
            <button
              ref={sidebarToggle}
              className="icon-button sidebar-toggle"
              type="button"
              aria-label="侧边栏"
              title="显示或隐藏侧边栏"
              aria-expanded={sidebarOpen}
              aria-controls={sidebarOpen ? 'workspace-sidebar' : undefined}
              onClick={() => setSidebarOpen((open) => !open)}
            >
              <PanelLeft size={18} />
            </button>
            <div className="breadcrumbs">
              <span className="breadcrumb-root">研究工作台</span>
              <ChevronRight className="breadcrumb-separator" size={13} />
              <span className="breadcrumb-title" title={title}>{title}</span>
            </div>
          </div>
          <div className="toolbar-trailing">
            <span className="demo-badge"><span /> 原型预览</span>
            {activeReview && (
              <button
                ref={inspectorToggle}
                className="toolbar-button"
                type="button"
                aria-label="证据面板"
                title="显示或隐藏证据面板"
                aria-expanded={showInspector}
                aria-controls={showInspector ? 'evidence-inspector' : undefined}
                onClick={() => setInspectorOpen((open) => !open)}
              >
                <PanelRight size={16} />
                <span>证据</span>
              </button>
            )}
          </div>
        </header>

        <div className="workspace-body">
          <div className="workbench" inert={inspectorDrawer}>
            <main className="reader" id="work-area" ref={scrollPane} tabIndex={-1}>
              {activeReview && (
                <Review
                  key={activeReview.id}
                  review={activeReview}
                  activeCitation={showInspector && inspectorTab === 'citations' ? citation : undefined}
                  onCitation={showCitation}
                />
              )}
              {view.kind === 'new' && (
                <NewReview onPrompt={(prompt) => {
                  setQuestion(prompt)
                  input.current?.focus()
                }} />
              )}
              {view.kind === 'library' && <Library onPreview={setPreview} />}
            </main>
            {view.kind !== 'library' && (
              <Composer
                input={input}
                question={question}
                onChange={setQuestion}
                onSubmit={submitQuestion}
                onLibrary={() => navigate({ kind: 'library' })}
              />
            )}
          </div>
          {showInspector && activeReview && (
            <>
              <button className="inspector-scrim" type="button" tabIndex={-1} aria-label="关闭证据面板" onClick={closeInspector} />
              <EvidenceInspector
                review={activeReview}
                citation={citation}
                tab={inspectorTab}
                drawer={inspectorDrawer}
                onTab={setInspectorTab}
                onCitation={showCitation}
                onPreview={setPreview}
                onJump={jumpToSection}
                onClose={closeInspector}
              />
            </>
          )}
        </div>
      </div>
      {preview && <PagePreview evidence={preview} onClose={() => setPreview(null)} />}
    </div>
  )
}

function Sidebar({ view, reviews, drawer, onNavigate, onNew, onClose }: {
  view: View
  reviews: ReviewRun[]
  drawer: boolean
  onNavigate: (view: View) => void
  onNew: () => void
  onClose: () => void
}) {
  const close = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (drawer) close.current?.focus()
  }, [drawer])

  return (
    <aside
      className="sidebar"
      id="workspace-sidebar"
      aria-label="工作区侧边栏"
      onKeyDown={(event) => {
        if (drawer && event.key === 'Escape') onClose()
      }}
    >
      <div className="brand">
        <img src={folioIcon} width="40" height="40" alt="" />
        <div>
          <span className="brand-name">Folio</span>
          <span className="brand-caption">文献综述工作台</span>
        </div>
        <button ref={close} className="icon-button sidebar-close" type="button" aria-label="收起侧边栏" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <nav className="sidebar-navigation" aria-label="工作区导航">
        <button className="new-review-button" type="button" onClick={onNew} aria-current={view.kind === 'new' ? 'page' : undefined}>
          <Plus size={17} /> 新建综述
        </button>
        <button className="sidebar-row library-button" type="button" onClick={() => onNavigate({ kind: 'library' })} aria-current={view.kind === 'library' ? 'page' : undefined}>
          <LibraryBig size={17} /> <span>文献库</span> <span className="sidebar-count">{demoEvidence.length}</span>
        </button>
        <h2 className="sidebar-heading">最近综述</h2>
        <ul className="review-history">
          {reviews.map((review) => (
            <li key={review.id}>
              <button
                className="sidebar-row history-row"
                type="button"
                title={review.title}
                aria-current={view.kind === 'review' && view.id === review.id ? 'page' : undefined}
                onClick={() => onNavigate({ kind: 'review', id: review.id })}
              >
                <MessageSquareText size={16} />
                <span>{review.title}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <span className="collection-icon"><BookOpen size={16} /></span>
        <div>
          <strong>本地文献工作区</strong>
          <small>{demoEvidence.length} 篇示例论文</small>
        </div>
      </div>
    </aside>
  )
}
