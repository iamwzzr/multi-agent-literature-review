import { useEffect, useRef, useState } from 'react'
import { Building2, ChevronRight, PanelLeft } from 'lucide-react'
import { Composer } from './Composer'
import { createDemoReview } from './demo'
import type { Evidence, ReviewRun } from './demo'
import { EvidenceInspector, Library, PagePreview } from './Evidence'
import type { InspectorTab } from './Evidence'
import { ResearchOffice } from './Office'
import { readWorkspace, saveWorkspace } from './projects'
import type { ProjectConfig } from './projects'
import { NewReview, Review } from './Review'
import { AppearanceSettings, ProjectSettings } from './Settings'
import { Sidebar } from './Sidebar'
import { useMediaQuery } from './useMediaQuery'
import { reviewPhases } from './workflow'

type View = { kind: 'review'; id: string } | { kind: 'new' | 'library' | 'office' }
type PendingRun = { projectId: string; review: ReviewRun; phase: number }

export function App() {
  const sidebarInline = useMediaQuery('(width > 820px)')
  const inspectorInline = useMediaQuery('(width > 1120px)')
  const [workspace, setWorkspace] = useState(readWorkspace)
  const [runs, setRuns] = useState<PendingRun[]>([])
  const [view, setView] = useState<View>({ kind: 'new' })
  const [sidebarOpen, setSidebarOpen] = useState(sidebarInline)
  const [sidebarWidth, setSidebarWidth] = useState(236)
  const [projectForm, setProjectForm] = useState<'create' | 'edit' | null>(null)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('citations')
  const [citation, setCitation] = useState<number | null>(null)
  const [question, setQuestion] = useState('')
  const [referenceIds, setReferenceIds] = useState<string[]>([])
  const [preview, setPreview] = useState<Evidence | null>(null)
  const timers = useRef(new Set<number>())
  const input = useRef<HTMLTextAreaElement>(null)
  const scrollPane = useRef<HTMLElement>(null)
  const sidebarToggle = useRef<HTMLButtonElement>(null)
  const citationTrigger = useRef<HTMLButtonElement>(null)
  const settingsDialog = useRef<HTMLDialogElement>(null)

  const project = workspace.projects.find(({ id }) => id === workspace.activeProjectId) ?? workspace.projects[0]
  const projectRuns = runs.filter((run) => run.projectId === project.id)
  const activeRun = view.kind === 'review' ? projectRuns.find((run) => run.review.id === view.id) : undefined
  const officeRun = view.kind === 'office' ? projectRuns.at(-1) : undefined
  const activeReview = view.kind === 'review'
    ? activeRun?.review ?? project.reviews.find((review) => review.id === view.id)
    : undefined
  const linkedReviews = project.reviews.filter((review) => activeReview?.referenceIds?.includes(review.id))
  const title = activeReview?.title ?? (view.kind === 'library' ? '知识库' : view.kind === 'office' ? '研究办公室' : '新建综述')
  const sidebarDrawer = sidebarOpen && !sidebarInline
  const inspectorDrawer = citation !== null && !inspectorInline
  const viewKey = project.id + '/' + (activeReview?.id ?? view.kind)
  const showingRun = Boolean(activeRun)

  useEffect(() => {
    saveWorkspace(workspace)
  }, [workspace])

  useEffect(() => {
    const scheduled = timers.current
    return () => scheduled.forEach((timer) => window.clearTimeout(timer))
  }, [])

  useEffect(() => {
    if (scrollPane.current) scrollPane.current.scrollTop = 0
  }, [viewKey, showingRun])

  function navigate(next: View) {
    setView(next)
    setCitation(null)
    citationTrigger.current = null
    if (!sidebarInline) setSidebarOpen(false)
    if (next.kind === 'new') requestAnimationFrame(() => input.current?.focus())
    else if (sidebarDrawer) requestAnimationFrame(() => scrollPane.current?.focus())
  }

  function clearDraft() {
    setQuestion('')
    setReferenceIds([])
  }

  function newReview() {
    if (view.kind !== 'new') clearDraft()
    navigate({ kind: 'new' })
  }

  function openReview(id: string) {
    clearDraft()
    navigate({ kind: 'review', id })
  }

  function selectProject(id: string) {
    setWorkspace((previous) => ({ ...previous, activeProjectId: id }))
    clearDraft()
    navigate({ kind: 'new' })
  }

  function configureProject(config: ProjectConfig) {
    if (projectForm === 'edit') {
      setWorkspace((previous) => ({
        ...previous,
        projects: previous.projects.map((entry) => entry.id === project.id ? { ...entry, ...config } : entry),
      }))
    } else {
      const created = { ...config, id: crypto.randomUUID(), reviews: [] }
      setWorkspace((previous) => ({ projects: [...previous.projects, created], activeProjectId: created.id }))
      clearDraft()
      navigate({ kind: 'new' })
    }
    setProjectForm(null)
  }

  function submitQuestion() {
    const value = question.trim()
    if (!value) return
    const review = createDemoReview(value, referenceIds)
    const projectId = project.id

    setRuns((previous) => [...previous, { projectId, review, phase: 0 }])
    clearDraft()
    navigate({ kind: 'review', id: review.id })
    requestAnimationFrame(() => document.getElementById('review-title')?.focus({ preventScroll: true }))

    let elapsed = 0
    reviewPhases.forEach(({ duration }, index) => {
      elapsed += duration
      const nextPhase = index + 1
      const timer = window.setTimeout(() => {
        timers.current.delete(timer)
        if (nextPhase === reviewPhases.length) {
          setWorkspace((previous) => ({
            ...previous,
            projects: previous.projects.map((entry) => (
              entry.id === projectId ? { ...entry, reviews: [{ ...review, mockVerified: true }, ...entry.reviews] } : entry
            )),
          }))
          setRuns((previous) => previous.filter((run) => run.review.id !== review.id))
        } else {
          setRuns((previous) => previous.map((run) => run.review.id === review.id ? { ...run, phase: nextPhase } : run))
        }
      }, elapsed)
      timers.current.add(timer)
    })
  }

  function showCitation(index: number, trigger: HTMLButtonElement) {
    citationTrigger.current = trigger
    setCitation(index)
    setInspectorTab('citations')
  }

  function closeSidebar() {
    setSidebarOpen(false)
    requestAnimationFrame(() => sidebarToggle.current?.focus())
  }

  function closeInspector() {
    setCitation(null)
    requestAnimationFrame(() => citationTrigger.current?.focus({ preventScroll: true }))
  }

  function jumpToSection(id: string) {
    if (inspectorDrawer) setCitation(null)
    requestAnimationFrame(() => {
      const heading = document.getElementById(id)
      heading?.focus({ preventScroll: true })
      heading?.scrollIntoView({ block: 'start' })
    })
  }

  const composer = (
    <Composer
      key={viewKey}
      input={input}
      question={question}
      knowledgeCount={project.knowledgePaths.length}
      conversations={project.reviews.filter((review) => review.id !== activeReview?.id)}
      referenceIds={referenceIds}
      onChange={setQuestion}
      onReferences={setReferenceIds}
      onSubmit={submitQuestion}
      onLibrary={() => navigate({ kind: 'library' })}
    />
  )

  return (
    <div className="app-window">
      {!sidebarDrawer && !inspectorDrawer && <a className="skip-link" href="#work-area">跳至工作区</a>}
      {sidebarOpen && (
        <>
          <button className="sidebar-scrim" type="button" tabIndex={-1} aria-label="关闭侧边栏" onClick={closeSidebar} />
          <Sidebar
            projects={workspace.projects}
            projectId={project.id}
            reviews={[...projectRuns.map((run) => run.review), ...project.reviews]}
            runningIds={projectRuns.map((run) => run.review.id)}
            activeReviewId={activeReview?.id}
            view={view.kind}
            drawer={sidebarDrawer}
            width={sidebarWidth}
            onProject={selectProject}
            onReview={openReview}
            onNew={newReview}
            onLibrary={() => navigate({ kind: 'library' })}
            onCreateProject={() => setProjectForm('create')}
            onEditProject={() => setProjectForm('edit')}
            onSettings={() => settingsDialog.current?.showModal()}
            onClose={closeSidebar}
            onResize={setSidebarWidth}
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
              <span className="breadcrumb-root" title={project.folder}>{project.name}</span>
              <ChevronRight className="breadcrumb-separator" size={13} />
              <span className="breadcrumb-title" title={title}>{title}</span>
            </div>
          </div>
          <div className="toolbar-actions">
            <button className="context-button office-entry" type="button" aria-current={view.kind === 'office' ? 'page' : undefined} onClick={() => navigate({ kind: 'office' })}>
              <Building2 size={15} /> 办公室
            </button>
            <span className="demo-badge"><span /> 原型预览</span>
          </div>
        </header>

        <div className="workspace-body">
          <div className="workbench" inert={inspectorDrawer}>
            <main className={view.kind === 'new' ? 'reader reader-start' : 'reader'} id="work-area" ref={scrollPane} tabIndex={-1}>
              {activeReview && (
                <Review
                  key={activeReview.id}
                  review={activeReview}
                  linkedReviews={linkedReviews}
                  runningPhase={activeRun ? reviewPhases[activeRun.phase] : undefined}
                  activeCitation={inspectorTab === 'citations' ? citation ?? undefined : undefined}
                  onCitation={showCitation}
                  onConversation={openReview}
                />
              )}
              {view.kind === 'new' && (
                <NewReview onPrompt={(prompt) => {
                  setQuestion(prompt)
                  input.current?.focus()
                }}>
                  {composer}
                </NewReview>
              )}
              {view.kind === 'library' && <Library project={project} onConfigure={() => setProjectForm('edit')} onPreview={setPreview} />}
              {view.kind === 'office' && (
                <div className="office-route office-width">
                  <ResearchOffice
                    key={officeRun?.review.id ?? 'waiting'}
                    phase={officeRun ? reviewPhases[officeRun.phase] : undefined}
                    onOpenRun={officeRun ? () => openReview(officeRun.review.id) : undefined}
                  />
                </div>
              )}
            </main>
            {(activeReview || view.kind === 'office') && composer}
          </div>
          {activeReview && !activeRun && citation !== null && (
            <>
              <button className="inspector-scrim" type="button" tabIndex={-1} aria-label="关闭证据面板" onClick={closeInspector} />
              <EvidenceInspector
                review={activeReview}
                citation={citation}
                tab={inspectorTab}
                drawer={inspectorDrawer}
                onTab={setInspectorTab}
                onCitation={setCitation}
                onPreview={setPreview}
                onJump={jumpToSection}
                onClose={closeInspector}
              />
            </>
          )}
        </div>
      </div>
      <AppearanceSettings dialog={settingsDialog} />
      {projectForm && (
        <ProjectSettings
          project={projectForm === 'edit' ? project : undefined}
          otherFolders={workspace.projects.filter((entry) => projectForm === 'create' || entry.id !== project.id).map((entry) => entry.folder)}
          onSave={configureProject}
          onClose={() => setProjectForm(null)}
        />
      )}
      {preview && <PagePreview evidence={preview} onClose={() => setPreview(null)} />}
    </div>
  )
}
