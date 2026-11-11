import { useEffect, useRef, useState } from 'react'
import { Archive, ArchiveRestore, Building2, ChevronRight, PanelLeft } from 'lucide-react'
import { Composer } from './Composer'
import { createDemoFollowUp, createDemoReview } from './demo'
import type { Evidence, ReviewRun } from './demo'
import { EvidenceInspector, Library, PagePreview } from './Evidence'
import type { InspectorTab } from './Evidence'
import { ResearchOffice } from './Office'
import { readWorkspace, removeReview, saveWorkspace } from './projects'
import type { ProjectConfig } from './projects'
import { reportLength, revealSections } from './response'
import { NewReview, Review, sectionAnchor } from './Review'
import { AppearanceSettings, ProjectSettings } from './Settings'
import { DeleteReviewDialog, Sidebar } from './Sidebar'
import { useMediaQuery } from './useMediaQuery'
import { reviewFlows } from './workflow'

type View = { kind: 'review'; id: string } | { kind: 'new' | 'library' }
type PendingRun = { projectId: string; review: ReviewRun } & (
  { kind: 'office'; phase: number } | { kind: 'response'; visibleLength: number }
)
type Citation = { turn: number; index: number }
type Draft = { question: string; referenceIds: string[] }
const emptyDraft: Draft = { question: '', referenceIds: [] }

function runPhases(review: ReviewRun) {
  return reviewFlows[review.history?.length ? 'followUp' : review.mockFlow ?? 'revision']
}

function runPhase(run?: PendingRun) {
  if (run?.kind === 'office') return runPhases(run.review)[run.phase]
}

export function App() {
  const sidebarInline = useMediaQuery('(width > 820px)')
  const inspectorInline = useMediaQuery('(width > 1120px)')
  const [workspace, setWorkspace] = useState(readWorkspace)
  const [runs, setRuns] = useState<PendingRun[]>([])
  const [view, setView] = useState<View>({ kind: 'new' })
  const [sidebarOpen, setSidebarOpen] = useState(sidebarInline)
  const [sidebarWidth, setSidebarWidth] = useState(236)
  const [officeOpen, setOfficeOpen] = useState(false)
  const [projectForm, setProjectForm] = useState<'create' | 'edit' | null>(null)
  const [reviewToDelete, setReviewToDelete] = useState<ReviewRun | null>(null)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('citations')
  const [citation, setCitation] = useState<Citation | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [preview, setPreview] = useState<Evidence | null>(null)
  const timers = useRef(new Map<string, number>())
  const input = useRef<HTMLTextAreaElement>(null)
  const scrollPane = useRef<HTMLElement>(null)
  const sidebarToggle = useRef<HTMLButtonElement>(null)
  const officeToggle = useRef<HTMLButtonElement>(null)
  const citationTrigger = useRef<HTMLButtonElement>(null)
  const settingsDialog = useRef<HTMLDialogElement>(null)

  const project = workspace.projects.find(({ id }) => id === workspace.activeProjectId) ?? workspace.projects[0]
  const projectRuns = runs.filter((run) => run.projectId === project.id)
  const archivedIds = new Set(project.archivedReviewIds)
  const listedReviews = [
    ...projectRuns.map(({ review }) => review).filter((review) => !project.reviews.some(({ id }) => id === review.id)),
    ...project.reviews,
  ]
  const activeRun = view.kind === 'review' ? projectRuns.find((run) => run.review.id === view.id) : undefined
  const officeRun = activeRun ?? projectRuns.at(-1)
  const activePhase = runPhase(activeRun)
  const activeReview = view.kind === 'review'
    ? activeRun?.review ?? project.reviews.find((review) => review.id === view.id)
    : undefined
  const displayReview = activeRun?.kind === 'response' && activeReview
    ? { ...activeReview, sections: revealSections(activeReview.sections, activeRun.visibleLength) }
    : activeReview
  const latestTurn = activeReview?.history?.length ?? 0
  const citedTurn = citation && (citation.turn === latestTurn ? displayReview : displayReview?.history?.[citation.turn])
  const activeArchived = activeReview && archivedIds.has(activeReview.id)
  const title = activeReview?.title ?? (view.kind === 'library' ? '知识库' : '新建综述')
  const sidebarDrawer = sidebarOpen && !sidebarInline
  const inspectorDrawer = citation !== null && !inspectorInline
  const viewKey = project.id + '/' + (view.kind === 'review' ? view.id : view.kind)
  const { question, referenceIds } = drafts[viewKey] ?? emptyDraft
  const showOffice = officeOpen && citation === null

  useEffect(() => {
    saveWorkspace(workspace)
  }, [workspace])

  useEffect(() => {
    const scheduled = timers.current
    return () => {
      scheduled.forEach((timer) => window.clearTimeout(timer))
      scheduled.clear()
    }
  }, [])

  useEffect(() => {
    if (scrollPane.current) scrollPane.current.scrollTop = 0
  }, [viewKey])

  function navigate(next: View) {
    setView(next)
    setCitation(null)
    citationTrigger.current = null
    if (!sidebarInline) setSidebarOpen(false)
    if (next.kind === 'new') requestAnimationFrame(() => input.current?.focus())
    else if (sidebarDrawer) requestAnimationFrame(() => scrollPane.current?.focus())
  }

  function updateDraft(changes: Partial<Draft>) {
    setDrafts((previous) => ({
      ...previous,
      [viewKey]: { ...(previous[viewKey] ?? emptyDraft), ...changes },
    }))
  }

  function clearDraft(key = viewKey) {
    setDrafts((previous) => {
      if (!previous[key]) return previous
      const remaining = { ...previous }
      delete remaining[key]
      return remaining
    })
  }

  function openReview(id: string) {
    if (projectRuns.some((run) => run.review.id === id && run.kind === 'office')) setOfficeOpen(true)
    navigate({ kind: 'review', id })
  }

  function archiveReview(id: string, archive: boolean) {
    setWorkspace((previous) => ({
      ...previous,
      projects: previous.projects.map((entry) => {
        if (entry.id !== project.id) return entry
        const archived = new Set(entry.archivedReviewIds)
        if (archive) archived.add(id)
        else archived.delete(id)
        return { ...entry, archivedReviewIds: [...archived] }
      }),
    }))
  }

  function deleteReview(id: string) {
    const timer = timers.current.get(id)
    if (timer !== undefined) window.clearTimeout(timer)
    timers.current.delete(id)
    setRuns((previous) => previous.filter((run) => run.review.id !== id))
    setWorkspace((previous) => ({
      ...previous,
      projects: previous.projects.map((entry) => entry.id === project.id ? removeReview(entry, id) : entry),
    }))
    setReviewToDelete(null)
    clearDraft(project.id + '/' + id)
    if (view.kind === 'review' && view.id === id) navigate({ kind: 'new' })
    else requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('.new-review-button')?.focus())
  }

  function selectProject(id: string) {
    setWorkspace((previous) => ({ ...previous, activeProjectId: id }))
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
      navigate({ kind: 'new' })
    }
    setProjectForm(null)
  }

  function schedule(id: string, callback: () => void, delay: number) {
    const timer = window.setTimeout(() => {
      timers.current.delete(id)
      callback()
    }, delay)
    timers.current.set(id, timer)
  }

  function streamResponse(projectId: string, review: ReviewRun) {
    const length = reportLength(review.sections)
    const chunkSize = Math.max(6, Math.ceil(length / 68))
    setRuns((previous) => previous.map((run) => (
      run.review.id === review.id ? { projectId, review, kind: 'response', visibleLength: 0 } : run
    )))

    function reveal(visibleLength: number) {
      if (visibleLength >= length) {
        setWorkspace((previous) => ({
          ...previous,
          projects: previous.projects.map((entry) => {
            if (entry.id !== projectId) return entry
            const completed = { ...review, mockVerified: true } as const
            const reviews = entry.reviews.some(({ id }) => id === review.id)
              ? entry.reviews.map((saved) => saved.id === review.id ? completed : saved)
              : [completed, ...entry.reviews]
            return { ...entry, reviews }
          }),
        }))
        setRuns((previous) => previous.filter((run) => run.review.id !== review.id))
        return
      }

      setRuns((previous) => previous.map((run) => (
        run.review.id === review.id && run.kind === 'response' ? { ...run, visibleLength } : run
      )))
      schedule(review.id, () => reveal(visibleLength + chunkSize), 90)
    }

    schedule(review.id, () => reveal(chunkSize), 600)
  }

  function submitQuestion() {
    const value = question.trim()
    if (!value || activeArchived || activeRun || (activeReview && timers.current.has(activeReview.id))) return
    const references = referenceIds.filter((id) => project.reviews.some((review) => review.id === id && !archivedIds.has(id)))
    const review = activeReview ? createDemoFollowUp(activeReview, value, references) : createDemoReview(value, references)
    const projectId = project.id
    const phases = runPhases(review)

    setRuns((previous) => [...previous, { projectId, review, kind: 'office', phase: 0 }])
    setOfficeOpen(true)
    clearDraft()
    navigate({ kind: 'review', id: review.id })
    requestAnimationFrame(() => {
      if (activeReview) {
        document.getElementById('latest-turn')?.scrollIntoView({ block: 'start' })
        input.current?.focus({ preventScroll: true })
      } else document.getElementById('review-title')?.focus({ preventScroll: true })
    })

    function advance(phase: number) {
      if (phase === phases.length) {
        streamResponse(projectId, review)
        return
      }
      if (phase > 0) setRuns((previous) => previous.map((run) => (
        run.review.id === review.id && run.kind === 'office' ? { ...run, phase } : run
      )))
      schedule(review.id, () => advance(phase + 1), phases[phase].duration)
    }
    advance(0)
  }

  function showCitation(turn: number, index: number, trigger: HTMLButtonElement) {
    citationTrigger.current = trigger
    setCitation({ turn, index })
    setInspectorTab('citations')
  }

  function closeSidebar() {
    setSidebarOpen(false)
    requestAnimationFrame(() => sidebarToggle.current?.focus())
  }

  function toggleOffice() {
    setOfficeOpen(!showOffice)
    if (!showOffice) {
      setCitation(null)
      citationTrigger.current = null
    }
  }

  function closeOffice() {
    setOfficeOpen(false)
    officeToggle.current?.focus()
  }

  function closeInspector() {
    setCitation(null)
    requestAnimationFrame(() => citationTrigger.current?.focus({ preventScroll: true }))
  }

  function jumpToSection(id: string) {
    if (!citation) return
    if (inspectorDrawer) setCitation(null)
    requestAnimationFrame(() => {
      const heading = document.getElementById(sectionAnchor(citation.turn, id))
      heading?.closest('details')?.setAttribute('open', '')
      heading?.focus({ preventScroll: true })
      heading?.scrollIntoView({ block: 'start' })
    })
  }

  const composer = (
    <Composer
      key={viewKey}
      input={input}
      question={question}
      followUp={Boolean(activeReview)}
      busy={Boolean(activeRun)}
      knowledgeCount={project.knowledgePaths.length}
      conversations={project.reviews.filter((review) => review.id !== activeReview?.id && !archivedIds.has(review.id))}
      referenceIds={referenceIds}
      onChange={(question) => updateDraft({ question })}
      onReferences={(referenceIds) => updateDraft({ referenceIds })}
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
            reviews={listedReviews}
            archivedIds={archivedIds}
            runningIds={projectRuns.map((run) => run.review.id)}
            activeReviewId={activeReview?.id}
            view={view.kind}
            drawer={sidebarDrawer}
            width={sidebarWidth}
            onProject={selectProject}
            onReview={openReview}
            onArchive={archiveReview}
            onDelete={setReviewToDelete}
            onNew={() => navigate({ kind: 'new' })}
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
            <button ref={officeToggle} className="context-button office-entry" type="button" aria-expanded={showOffice} aria-controls={showOffice ? 'office-panel' : undefined} onClick={toggleOffice}>
              <Building2 size={15} /> 办公室
            </button>
            <span className="demo-badge"><span /> 原型预览</span>
          </div>
        </header>

        <div className="workspace-body" data-office-open={showOffice}>
          <div className="workbench" inert={inspectorDrawer}>
            <main className={view.kind === 'new' ? 'reader reader-start' : 'reader'} id="work-area" ref={scrollPane} tabIndex={-1}>
              {displayReview && (
                <Review
                  key={displayReview.id}
                  review={displayReview}
                  conversations={project.reviews}
                  runningPhase={activePhase}
                  responding={activeRun?.kind === 'response'}
                  activeCitation={inspectorTab === 'citations' ? citation ?? undefined : undefined}
                  onCitation={showCitation}
                  onConversation={openReview}
                  onSuggestion={activeRun || activeArchived || question.trim() ? undefined : (prompt) => {
                    updateDraft({ question: prompt })
                    input.current?.focus()
                  }}
                />
              )}
              {view.kind === 'new' && (
                <NewReview question={question} onPrompt={(prompt) => {
                  updateDraft({ question: prompt })
                  input.current?.focus()
                }}>
                  {composer}
                </NewReview>
              )}
              {view.kind === 'library' && <Library project={project} onConfigure={() => setProjectForm('edit')} onPreview={setPreview} />}
            </main>
            {activeReview && (activeArchived ? (
              <div className="composer-dock">
                <div className="archived-banner reading-width">
                  <span><Archive size={15} /> 对话已归档</span>
                  <button className="context-button" type="button" onClick={() => {
                    archiveReview(activeReview.id, false)
                    requestAnimationFrame(() => input.current?.focus())
                  }}><ArchiveRestore size={15} /> 恢复并继续</button>
                </div>
              </div>
            ) : composer)}
          </div>
          {showOffice && (
            <ResearchOffice
              key={project.id}
              phase={runPhase(officeRun)}
              onOpenRun={officeRun && officeRun !== activeRun ? () => openReview(officeRun.review.id) : undefined}
              onClose={closeOffice}
            />
          )}
          {citedTurn && citation && (
            <>
              <button className="inspector-scrim" type="button" tabIndex={-1} aria-label="关闭证据面板" onClick={closeInspector} />
              <EvidenceInspector
                review={citedTurn}
                citation={citation.index}
                tab={inspectorTab}
                drawer={inspectorDrawer}
                onTab={setInspectorTab}
                onCitation={(index) => setCitation({ ...citation, index })}
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
      {reviewToDelete && <DeleteReviewDialog review={reviewToDelete} onDelete={() => deleteReview(reviewToDelete.id)} onClose={() => setReviewToDelete(null)} />}
      {preview && <PagePreview evidence={preview} onClose={() => setPreview(null)} />}
    </div>
  )
}
