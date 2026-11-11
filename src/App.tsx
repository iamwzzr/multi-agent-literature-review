import { useEffect, useRef, useState } from 'react'
import { Archive, ArchiveRestore, Building2, ChevronRight, PanelLeft } from 'lucide-react'
import { readBackendSettings, reviewRequest, saveBackendSettings, streamBackendReview } from './backend'
import { Composer } from './Composer'
import { createDemoFollowUp, createDemoReview, lastTurn } from './demo'
import type { Evidence, ReviewRun } from './demo'
import { EvidenceInspector, Library, PagePreview } from './Evidence'
import type { InspectorTab } from './Evidence'
import { pickFolder } from './folderPicker'
import { ResearchOffice } from './Office'
import { readWorkspace, removeReview, saveWorkspace } from './projects'
import type { ProjectConfig } from './projects'
import { reportLength, revealSections } from './response'
import { NewReview, Review, sectionAnchor } from './Review'
import { ProjectSettings, WorkspaceSettings } from './Settings'
import { DeleteReviewDialog, Sidebar } from './Sidebar'
import { useMediaQuery } from './useMediaQuery'
import { reviewFlows } from './workflow'
import type { AgentActivity } from './workflow'

type View = { kind: 'review'; id: string } | { kind: 'new' | 'library' }
type PendingRun = { projectId: string; review: ReviewRun } & (
  { kind: 'office'; phase: AgentActivity } | { kind: 'response'; visibleLength?: number } |
  { kind: 'connecting' } | { kind: 'failed'; message: string }
)
type Citation = { turn: number; index: number }
type Draft = { question: string; referenceIds: string[]; sample?: boolean }
const emptyDraft: Draft = { question: '', referenceIds: [] }

function runPhases(review: ReviewRun) {
  return reviewFlows[review.history?.length ? 'followUp' : review.mockFlow ?? 'revision']
}

function runPhase(run?: PendingRun) {
  if (run?.kind === 'office') return run.phase
}

export function App() {
  const sidebarInline = useMediaQuery('(width > 820px)')
  const inspectorInline = useMediaQuery('(width > 1120px)')
  const [backend, setBackend] = useState(readBackendSettings)
  const [workspace, setWorkspace] = useState(readWorkspace)
  const [runs, setRuns] = useState<PendingRun[]>([])
  const [view, setView] = useState<View>({ kind: 'new' })
  const [sidebarOpen, setSidebarOpen] = useState(sidebarInline)
  const [sidebarWidth, setSidebarWidth] = useState(236)
  const [officeOpen, setOfficeOpen] = useState(false)
  const [projectForm, setProjectForm] = useState<'create' | 'edit' | null>(null)
  const [pickingFolder, setPickingFolder] = useState(false)
  const [folderError, setFolderError] = useState<{ projectId: string; message: string } | null>(null)
  const [reviewToDelete, setReviewToDelete] = useState<ReviewRun | null>(null)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('citations')
  const [citation, setCitation] = useState<Citation | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [preview, setPreview] = useState<Evidence | null>(null)
  const timers = useRef(new Map<string, number>())
  const backendRequests = useRef(new Map<string, AbortController>())
  const input = useRef<HTMLTextAreaElement>(null)
  const scrollPane = useRef<HTMLElement>(null)
  const sidebarToggle = useRef<HTMLButtonElement>(null)
  const officeToggle = useRef<HTMLButtonElement>(null)
  const citationTrigger = useRef<HTMLButtonElement>(null)
  const settingsDialog = useRef<HTMLDialogElement>(null)

  const project = workspace.projects.find(({ id }) => id === workspace.activeProjectId) ?? workspace.projects[0]
  const projectRuns = runs.filter((run) => run.projectId === project.id)
  const liveProjectRuns = projectRuns.filter(({ kind }) => kind !== 'failed')
  const archivedIds = new Set(project.archivedReviewIds)
  const listedReviews = [
    ...projectRuns.map(({ review }) => review).filter((review) => !project.reviews.some(({ id }) => id === review.id)),
    ...project.reviews,
  ]
  const activeRun = view.kind === 'review' ? projectRuns.find((run) => run.review.id === view.id) : undefined
  const busy = activeRun !== undefined && activeRun.kind !== 'failed'
  const officeRun = busy ? activeRun : liveProjectRuns.at(-1)
  const activePhase = runPhase(activeRun)
  const savedReview = view.kind === 'review' ? project.reviews.find((review) => review.id === view.id) : undefined
  const activeReview = activeRun?.review ?? savedReview
  const displayReview = activeRun?.kind === 'response' && activeRun.visibleLength !== undefined
    ? { ...activeRun.review, sections: revealSections(activeRun.review.sections, activeRun.visibleLength) }
    : activeReview
  const latestTurn = activeReview?.history?.length ?? 0
  const citedTurn = citation && (citation.turn === latestTurn ? displayReview : displayReview?.history?.[citation.turn])
  const activeArchived = activeReview && archivedIds.has(activeReview.id)
  const title = activeReview?.title ?? (view.kind === 'library' ? '知识库' : '新建综述')
  const sidebarDrawer = sidebarOpen && !sidebarInline
  const inspectorDrawer = citation !== null && !inspectorInline
  const viewKey = project.id + '/' + (view.kind === 'review' ? view.id : view.kind)
  const { question, referenceIds, sample } = drafts[viewKey] ?? emptyDraft
  const useBackend = activeReview ? activeReview.source === 'backend' : !backend.useDemo && !sample
  const availableConversations = project.reviews.filter((review) => (
    review.id !== activeReview?.id && !archivedIds.has(review.id) && (!useBackend || review.source === 'backend')
  ))
  const showOffice = officeOpen && citation === null

  useEffect(() => {
    saveWorkspace(workspace)
  }, [workspace])

  useEffect(() => {
    const scheduled = timers.current
    const requests = backendRequests.current
    return () => {
      scheduled.forEach((timer) => window.clearTimeout(timer))
      scheduled.clear()
      requests.forEach((controller) => controller.abort())
      requests.clear()
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
    backendRequests.current.get(id)?.abort()
    backendRequests.current.delete(id)
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

  async function addKnowledgeFolder() {
    if (pickingFolder) return
    const projectId = project.id
    setPickingFolder(true)
    setFolderError(null)
    try {
      const name = await pickFolder('folio-knowledge')
      if (!name) return
      if (project.knowledgePaths.includes(name)) {
        setFolderError({ projectId, message: '已添加这个目录名。同名文件夹可以在项目配置里填写完整路径。' })
        return
      }
      setWorkspace((previous) => ({
        ...previous,
        projects: previous.projects.map((entry) => (
          entry.id === projectId && !entry.knowledgePaths.includes(name)
            ? { ...entry, knowledgePaths: [...entry.knowledgePaths, name] }
            : entry
        )),
      }))
    } catch (failure) {
      setFolderError({ projectId, message: failure instanceof Error ? failure.message : '无法选择文件夹。' })
    } finally {
      setPickingFolder(false)
    }
  }

  function schedule(id: string, callback: () => void, delay: number) {
    const timer = window.setTimeout(() => {
      timers.current.delete(id)
      callback()
    }, delay)
    timers.current.set(id, timer)
  }

  function completeRun(projectId: string, review: ReviewRun) {
    setWorkspace((previous) => ({
      ...previous,
      projects: previous.projects.map((entry) => {
        if (entry.id !== projectId) return entry
        const reviews = entry.reviews.some(({ id }) => id === review.id)
          ? entry.reviews.map((saved) => saved.id === review.id ? review : saved)
          : [review, ...entry.reviews]
        return { ...entry, reviews }
      }),
    }))
    setRuns((previous) => previous.filter((run) => run.review.id !== review.id))
  }

  function updateRun(next: PendingRun) {
    setRuns((previous) => previous.map((run) => run.review.id === next.review.id ? next : run))
  }

  function showRun(run: PendingRun) {
    setRuns((previous) => [...previous.filter((entry) => entry.review.id !== run.review.id), run])
    setOfficeOpen(true)
    navigate({ kind: 'review', id: run.review.id })
    requestAnimationFrame(() => {
      if (run.review.history?.length) {
        document.getElementById('latest-turn')?.scrollIntoView({ block: 'start' })
        input.current?.focus({ preventScroll: true })
      } else document.getElementById('review-title')?.focus({ preventScroll: true })
    })
  }

  function streamDemoResponse(projectId: string, review: ReviewRun) {
    const length = reportLength(review.sections)
    const chunkSize = Math.max(6, Math.ceil(length / 68))
    updateRun({ projectId, review, kind: 'response', visibleLength: 0 })

    function reveal(visibleLength: number) {
      if (visibleLength >= length) {
        completeRun(projectId, { ...review, mockVerified: true })
        return
      }

      updateRun({ projectId, review, kind: 'response', visibleLength })
      schedule(review.id, () => reveal(visibleLength + chunkSize), 90)
    }

    schedule(review.id, () => reveal(chunkSize), 600)
  }

  function runDemo(review: ReviewRun) {
    const projectId = project.id
    const phases = runPhases(review)
    showRun({ projectId, review, kind: 'office', phase: phases[0] })

    function advance(phase: number) {
      if (phase === phases.length) {
        streamDemoResponse(projectId, review)
        return
      }
      if (phase > 0) updateRun({ projectId, review, kind: 'office', phase: phases[phase] })
      schedule(review.id, () => advance(phase + 1), phases[phase].duration)
    }
    advance(0)
  }

  async function runBackend(review: ReviewRun) {
    if (backendRequests.current.has(review.id)) return
    const controller = new AbortController()
    backendRequests.current.set(review.id, controller)
    const projectId = project.id
    let current: ReviewRun = { ...review, sections: [], evidence: [] }
    showRun({ projectId, review: current, kind: 'connecting' })

    try {
      const output = await streamBackendReview(backend.url, reviewRequest(project, review), controller.signal, (update) => {
        if (backendRequests.current.get(review.id) !== controller) return
        if (update.kind === 'phase') {
          updateRun({ projectId, review: current, kind: 'office', phase: update.phase })
        } else {
          current = { ...current, sections: update.sections, evidence: update.evidence }
          updateRun({ projectId, review: current, kind: 'response' })
        }
      })
      controller.signal.throwIfAborted()
      if (backendRequests.current.get(review.id) === controller) completeRun(projectId, { ...review, ...output })
    } catch (failure) {
      if (backendRequests.current.get(review.id) !== controller) return
      const message = controller.signal.aborted ? '已停止生成。' : failure instanceof Error ? failure.message : '后端请求失败。'
      updateRun({ projectId, review: current, kind: 'failed', message })
    } finally {
      if (backendRequests.current.get(review.id) === controller) backendRequests.current.delete(review.id)
    }
  }

  function submitQuestion() {
    const value = question.trim()
    if (!value || activeArchived || busy || (activeReview && timers.current.has(activeReview.id))) return
    const references = referenceIds.filter((id) => availableConversations.some((review) => review.id === id))
    clearDraft()
    if (useBackend) {
      void runBackend({
        id: activeReview?.id ?? crypto.randomUUID(),
        title: savedReview?.title ?? value,
        source: 'backend',
        question: value,
        referenceIds: references,
        history: savedReview ? [...(savedReview.history ?? []), lastTurn(savedReview)] : undefined,
        sections: [],
        evidence: [],
      })
    } else {
      runDemo(savedReview ? createDemoFollowUp(savedReview, value, references) : createDemoReview(value, references))
    }
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
      busy={busy}
      demo={!useBackend}
      knowledgeCount={project.knowledgePaths.length}
      conversations={availableConversations}
      referenceIds={referenceIds}
      onChange={(question) => updateDraft({ question, sample: false })}
      onReferences={(referenceIds) => updateDraft({ referenceIds })}
      onSubmit={submitQuestion}
      onLibrary={() => navigate({ kind: 'library' })}
      onStop={busy && activeReview?.source === 'backend' ? () => backendRequests.current.get(activeReview.id)?.abort() : undefined}
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
            runningIds={liveProjectRuns.map((run) => run.review.id)}
            activeReviewId={activeReview?.id}
            view={view.kind}
            drawer={sidebarDrawer}
            width={sidebarWidth}
            onProject={selectProject}
            onReview={openReview}
            onArchive={archiveReview}
            onDelete={setReviewToDelete}
            onNew={() => navigate({ kind: 'new' })}
            onNewConversation={() => {
              clearDraft(project.id + '/new')
              navigate({ kind: 'new' })
            }}
            onLibrary={() => navigate({ kind: 'library' })}
            pickingFolder={pickingFolder}
            folderError={folderError?.projectId === project.id ? folderError.message : undefined}
            onAddKnowledge={() => void addKnowledgeFolder()}
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
            {!useBackend && view.kind !== 'library' && <span className="demo-badge"><span /> 模拟数据</span>}
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
                  connecting={activeRun?.kind === 'connecting'}
                  error={activeRun?.kind === 'failed' ? activeRun.message : undefined}
                  onRetry={activeRun?.kind === 'failed' && !activeArchived ? () => void runBackend(activeRun.review) : undefined}
                  onSettings={() => settingsDialog.current?.showModal()}
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
                  updateDraft({ question: prompt, sample: true })
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
      <WorkspaceSettings dialog={settingsDialog} backend={backend} onBackendSave={(settings) => {
        setBackend(settings)
        saveBackendSettings(settings)
      }} />
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
