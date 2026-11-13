import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import { Archive, ArchiveRestore, Building2, ChevronRight, FileText, PanelLeft } from 'lucide-react'
import { BackendRequestError, deleteBackendConversation, getBackendRun, maxKnowledgePaths, maxReferences, readBackendSettings, reviewRequest, saveBackendSettings, streamBackendReview, validateProject } from './backend'
import { Composer } from './Composer'
import { createDemoFollowUp, createDemoReview, lastTurn } from './demo'
import type { Evidence, ReviewRun } from './demo'
import { EvidenceInspector, Library, PagePreview } from './Evidence'
import type { InspectorTab } from './Evidence'
import { pickFolder } from './folderPicker'
import { FolderDialog } from './FolderDialog'
import { ResearchOffice } from './Office'
import { latestReportSection, ReportPanel, ReportPreview, reportVersions } from './ReportPreview'
import { readRecoverableRuns, readWorkspace, removeReview, saveRecoverableRuns, saveWorkspace } from './projects'
import type { ProjectConfig, RecoverableRun } from './projects'
import { reportLength, revealSections } from './response'
import { NewReview, Review, sectionAnchor } from './Review'
import { describeReviewFailure } from './reviewFailure'
import type { ReviewFailure } from './reviewFailure'
import { ProjectSettings, WorkspaceSettings } from './Settings'
import { DeleteReviewDialog, Sidebar } from './Sidebar'
import { useMediaQuery } from './useMediaQuery'
import { reviewFlows } from './workflow'
import type { AgentActivity } from './workflow'

type View = { kind: 'review'; id: string } | { kind: 'new' | 'library' }
type PendingRun = { projectId: string; review: ReviewRun } & (
  { kind: 'office'; phase: AgentActivity } | { kind: 'response'; visibleLength?: number } |
  { kind: 'connecting' } | { kind: 'failed'; error: ReviewFailure; checkRun?: boolean }
)
type Citation = { turn: number; index: number; fromReport?: boolean }
type RightPanel = 'office' | 'report' | 'closed'
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
  const [recoverableRuns, setRecoverableRuns] = useState(readRecoverableRuns)
  const [workspaceSaved, setWorkspaceSaved] = useState(true)
  const [recoverySaved, setRecoverySaved] = useState(true)
  const [runs, setRuns] = useState<PendingRun[]>([])
  const [view, setView] = useState<View>({ kind: 'new' })
  const [sidebarOpen, setSidebarOpen] = useState(sidebarInline)
  const [sidebarWidth, setSidebarWidth] = useState(236)
  const [panelOverride, setPanelOverride] = useState<{ scope: string; panel: RightPanel } | null>(null)
  const [projectForm, setProjectForm] = useState<{ kind: 'create' | 'edit'; id: string } | null>(null)
  const [knowledgePicker, setKnowledgePicker] = useState(false)
  const [pickingFolder, setPickingFolder] = useState(false)
  const [folderError, setFolderError] = useState<{ projectId: string; message: string } | null>(null)
  const [reviewToDelete, setReviewToDelete] = useState<ReviewRun | null>(null)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('citations')
  const [citation, setCitation] = useState<Citation | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [preview, setPreview] = useState<Evidence | null>(null)
  const [reportPreview, setReportPreview] = useState<ReviewRun | null>(null)
  const timers = useRef(new Map<string, number>())
  const backendRequests = useRef(new Map<string, AbortController>())
  const input = useRef<HTMLTextAreaElement>(null)
  const scrollPane = useRef<HTMLElement>(null)
  const sidebarToggle = useRef<HTMLButtonElement>(null)
  const officeToggle = useRef<HTMLButtonElement>(null)
  const reportToggle = useRef<HTMLButtonElement>(null)
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
  const versions = useMemo(() => savedReview ? reportVersions(savedReview) : [], [savedReview])
  const latestReport = versions.at(-1)
  const activeReview = activeRun?.review ?? savedReview
  const displayReview = activeRun?.kind === 'response' && activeRun.visibleLength !== undefined
    ? {
      ...activeRun.review,
      reply: activeRun.review.reply?.slice(0, activeRun.visibleLength),
      sections: activeRun.review.reply ? [] : revealSections(activeRun.review.sections, activeRun.visibleLength),
    }
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
  const availableConversations = useMemo(() => project.reviews.filter((review) => (
    review.id !== activeReview?.id && !project.archivedReviewIds?.includes(review.id) &&
    (!useBackend || review.source === 'backend' && review.backendUrl === backend.url)
  )), [project.reviews, project.archivedReviewIds, activeReview?.id, useBackend, backend.url])
  const backendNotice = activeReview?.source === 'backend' && activeReview.backendUrl !== backend.url
    ? activeReview.backendUrl ? `请连接此对话的后端 ${activeReview.backendUrl} 后继续。`
      : '此旧对话缺少后端地址。关联后，继续追问会将相关历史发送到当前后端。'
    : undefined
  const recoverable = recoverableRuns.find((run) => run.projectId === project.id && run.conversationId === activeReview?.id && run.backendUrl === backend.url)
  const panelScope = viewKey + '/' + (savedReview ? savedReview.history?.length ?? 0 : -1) + '/' + (busy ? 'working' : activeRun ? 'failed' : 'ready')
  const autoReport = latestReport && (activeRun?.kind !== 'failed' || sidebarInline)
  const panel = panelOverride?.scope === panelScope ? panelOverride.panel : busy ? 'office' : autoReport ? 'report' : 'closed'
  const showOffice = panel === 'office' && citation === null
  const showReport = panel === 'report' && latestReport !== undefined && citation === null
  const reportDrawer = showReport && !sidebarInline

  useEffect(() => {
    const saved = saveWorkspace(workspace)
    setWorkspaceSaved(saved)
    if (saved) setRecoverableRuns((previous) => {
      const remaining = previous.filter((entry) => !workspace.projects.find(({ id }) => id === entry.projectId)?.reviews
        .some((review) => review.id === entry.conversationId && review.runId === entry.runId))
      return remaining.length === previous.length ? previous : remaining
    })
  }, [workspace])

  useEffect(() => {
    setRecoverySaved(saveRecoverableRuns(recoverableRuns))
  }, [recoverableRuns])

  const recoverOnConnect = useEffectEvent(() => {
    for (const entry of recoverableRuns) {
      if (entry.backendUrl === backend.url) void recoverRun(entry)
    }
  })

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
    recoverOnConnect()
  }, [backend.url, backend.token])

  useEffect(() => {
    if (scrollPane.current) scrollPane.current.scrollTop = 0
  }, [viewKey])

  const navigate = useCallback((next: View) => {
    setView(next)
    setPanelOverride(null)
    setCitation(null)
    citationTrigger.current = null
    if (!sidebarInline) setSidebarOpen(false)
    if (next.kind === 'new') requestAnimationFrame(() => input.current?.focus())
    else if (sidebarDrawer) requestAnimationFrame(() => scrollPane.current?.focus())
  }, [sidebarInline, sidebarDrawer])

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

  const openReview = useCallback((id: string) => {
    navigate({ kind: 'review', id })
  }, [navigate])

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

  async function deleteReview(review: ReviewRun, localOnly: boolean) {
    const { id } = review
    if (review.source === 'backend' && !localOnly) {
      if (!review.backendUrl || review.backendUrl !== backend.url) throw new Error('请先连接此对话所属的后端。')
      try {
        await deleteBackendConversation(backend, project.id, id)
      } catch (failure) {
        if (failure instanceof BackendRequestError && [404, 405].includes(failure.status)) {
          throw new Error('此后端尚不支持删除记录。可以选择仅移除本标签页的对话。')
        }
        throw failure
      }
    }
    const timer = timers.current.get(id)
    if (timer !== undefined) window.clearTimeout(timer)
    timers.current.delete(id)
    backendRequests.current.get(id)?.abort()
    backendRequests.current.delete(id)
    setRuns((previous) => previous.filter((run) => run.review.id !== id))
    setRecoverableRuns((previous) => previous.filter((run) => run.projectId !== project.id || run.conversationId !== id))
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

  function openProjectForm(kind: 'create' | 'edit') {
    setProjectForm({ kind, id: kind === 'edit' ? project.id : crypto.randomUUID() })
  }

  function configureProject(config: ProjectConfig) {
    if (!projectForm) return
    if (projectForm.kind === 'edit') {
      setWorkspace((previous) => ({
        ...previous,
        projects: previous.projects.map((entry) => entry.id === projectForm.id ? { ...entry, ...config } : entry),
      }))
    } else {
      const created = { ...config, id: projectForm.id, reviews: [] }
      setWorkspace((previous) => ({ projects: [...previous.projects, created], activeProjectId: created.id }))
      navigate({ kind: 'new' })
    }
    setProjectForm(null)
  }

  async function addKnowledgeFolder(chosenPath?: string) {
    if (pickingFolder) return
    const projectId = project.id
    setFolderError(null)
    if (project.knowledgePaths.length >= maxKnowledgePaths) {
      setFolderError({ projectId, message: `每个项目最多配置 ${maxKnowledgePaths} 个知识库路径。` })
      return
    }
    if (!backend.useDemo && !chosenPath) {
      setKnowledgePicker(true)
      return
    }
    setPickingFolder(true)
    try {
      const path = chosenPath ?? await pickFolder('folio-knowledge')
      if (!path) return
      if (project.knowledgePaths.includes(path)) {
        setFolderError({ projectId, message: '已添加这个目录。' })
        return
      }
      const config = { name: project.name, folder: project.folder, knowledgePaths: [...project.knowledgePaths, path] }
      const validated = chosenPath ? await validateProject(backend, projectId, config) : config
      setWorkspace((previous) => ({
        ...previous,
        projects: previous.projects.map((entry) => (
          entry.id === projectId && entry.folder === project.folder && entry.knowledgePaths === project.knowledgePaths
            ? { ...entry, folder: validated.folder, knowledgePaths: validated.knowledgePaths } : entry
        )),
      }))
    } catch (failure) {
      setFolderError({ projectId, message: failure instanceof Error ? failure.message : '无法选择文件夹。' })
    } finally {
      setPickingFolder(false)
    }
  }

  function associateReview(id: string) {
    setWorkspace((previous) => ({ ...previous, projects: previous.projects.map((entry) => entry.id === project.id ? {
      ...entry, reviews: entry.reviews.map((review) => review.id === id && !review.backendUrl
        ? { ...review, backendUrl: backend.url } : review),
    } : entry) }))
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
    navigate({ kind: 'review', id: run.review.id })
    requestAnimationFrame(() => {
      if (run.review.history?.length) {
        document.getElementById('latest-turn')?.scrollIntoView({ block: 'start' })
        input.current?.focus({ preventScroll: true })
      } else document.getElementById('review-title')?.focus({ preventScroll: true })
    })
  }

  function streamDemoResponse(projectId: string, review: ReviewRun) {
    const length = review.reply?.length ?? reportLength(review.sections)
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
    if (review.backendUrl !== backend.url || backendRequests.current.has(review.id)) return
    const controller = new AbortController()
    backendRequests.current.set(review.id, controller)
    const projectId = project.id
    let current: ReviewRun = { ...review, sections: [], evidence: [], reply: undefined, runId: undefined }
    showRun({ projectId, review: current, kind: 'connecting' })

    try {
      const output = await streamBackendReview(backend, reviewRequest(project, review), controller.signal, (update) => {
        if (backendRequests.current.get(review.id) !== controller) return
        if (update.kind === 'phase') {
          updateRun({ projectId, review: current, kind: 'office', phase: update.phase })
        } else {
          current = { ...current, sections: update.sections, evidence: update.evidence, reply: update.reply }
          updateRun({ projectId, review: current, kind: 'response' })
        }
      }, (runId) => {
        if (backendRequests.current.get(review.id) !== controller) return
        current = { ...current, runId }
        setRecoverableRuns((previous) => [...previous.filter((run) => run.projectId !== projectId || run.conversationId !== review.id), {
          projectId, conversationId: review.id, runId, backendUrl: backend.url,
          title: review.title, question: review.question, referenceIds: review.referenceIds,
        }])
      }, review.history?.at(-1))
      controller.signal.throwIfAborted()
      if (backendRequests.current.get(review.id) === controller) completeRun(projectId, { ...review, ...output, runId: current.runId })
    } catch (failure) {
      if (backendRequests.current.get(review.id) !== controller) return
      const error = controller.signal.aborted ? describeReviewFailure('可以重试，或修改问题后重新提交。', 'RUN_STOPPED')
        : describeReviewFailure(failure)
      const checkRun = Boolean(current.runId) && !controller.signal.aborted &&
        !(failure instanceof BackendRequestError && failure.status === 200)
      updateRun({ projectId, review: current, kind: 'failed', error, checkRun })
    } finally {
      if (backendRequests.current.get(review.id) === controller) backendRequests.current.delete(review.id)
    }
  }

  async function recoverRun(entry: RecoverableRun) {
    const { projectId, conversationId, runId, backendUrl, title, question, referenceIds } = entry
    if (backendUrl !== backend.url || backendRequests.current.has(conversationId)) return
    const target = workspace.projects.find(({ id }) => id === projectId)
    if (!target) return
    const saved = target.reviews.find(({ id }) => id === conversationId)
    if (saved?.runId === runId || saved?.backendUrl && saved.backendUrl !== backendUrl) return
    const review: ReviewRun = {
      id: conversationId, title, question, referenceIds, backendUrl, runId, source: 'backend',
      history: saved ? [...(saved.history ?? []), lastTurn(saved)] : undefined, sections: [], evidence: [],
    }
    const controller = new AbortController()
    backendRequests.current.set(conversationId, controller)
    setRuns((previous) => [...previous.filter((run) => run.review.id !== conversationId), { projectId, review, kind: 'connecting' }])
    try {
      const result = await getBackendRun(backend, runId, projectId, conversationId, controller.signal)
      if (backendRequests.current.get(conversationId) !== controller) return
      if (result.status === 'completed') {
        completeRun(projectId, { ...review, ...result.output, reportUnchanged: saved ? result.output.reportUnchanged : undefined })
      } else if (result.status === 'failed') {
        updateRun({ projectId, review, kind: 'failed', error: describeReviewFailure(result.error) })
      } else {
        if (result.status === 'interrupted') setRecoverableRuns((previous) => previous.filter((run) => run.runId !== runId))
        const checkRun = result.status === 'running'
        const error = checkRun ? describeReviewFailure('稍后可检查任务结果。', 'RUN_PENDING')
          : describeReviewFailure('可以重试，或修改问题后重新提交。', 'RUN_INTERRUPTED')
        updateRun({ projectId, review, kind: 'failed', error, checkRun })
      }
    } catch (failure) {
      if (backendRequests.current.get(conversationId) !== controller) return
      const missing = failure instanceof BackendRequestError && failure.status === 404
      if (missing) {
        setRecoverableRuns((previous) => previous.filter((run) => run.runId !== runId))
      }
      const error = controller.signal.aborted ? describeReviewFailure('可以再次检查任务结果。', 'CHECK_STOPPED')
        : describeReviewFailure(failure instanceof Error ? failure : '暂时无法读取上次任务结果。')
      updateRun({ projectId, review, kind: 'failed', error, checkRun: !missing })
    } finally {
      if (backendRequests.current.get(conversationId) === controller) backendRequests.current.delete(conversationId)
    }
  }

  function submitQuestion() {
    const value = question.trim()
    if (!value || backendNotice || activeArchived || busy || (activeReview && timers.current.has(activeReview.id))) return
    const references = referenceIds.filter((id) => availableConversations.some((review) => review.id === id))
    clearDraft()
    if (useBackend) {
      void runBackend({
        id: activeReview?.id ?? crypto.randomUUID(),
        title: savedReview?.title ?? value,
        source: 'backend',
        backendUrl: backend.url,
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

  const showCitation = useCallback((turn: number, index: number, trigger: HTMLButtonElement, fromReport?: boolean) => {
    citationTrigger.current = trigger
    setCitation({ turn, index, fromReport })
    setInspectorTab('citations')
  }, [])

  function closeSidebar() {
    setSidebarOpen(false)
    requestAnimationFrame(() => sidebarToggle.current?.focus())
  }

  function togglePanel(next: 'office' | 'report') {
    setPanelOverride({ scope: panelScope, panel: panel === next && !citation ? 'closed' : next })
    setCitation(null)
    citationTrigger.current = null
  }

  function closePanel(current: 'office' | 'report') {
    setPanelOverride({ scope: panelScope, panel: 'closed' })
    const trigger = current === 'office' ? officeToggle : reportToggle
    trigger.current?.focus()
  }

  function closeInspector() {
    setCitation(null)
    requestAnimationFrame(() => {
      const trigger = citationTrigger.current
      if (trigger?.isConnected && !trigger.closest('[inert]')) trigger.focus({ preventScroll: true })
      else reportToggle.current?.focus()
    })
  }

  function jumpToSection(id: string) {
    if (!citation) return
    const inReport = citation.fromReport && citation.turn === latestReport?.turnIndex && panel === 'report'
    if (inspectorDrawer || inReport) setCitation(null)
    if (!inReport && inspectorDrawer && !sidebarInline && panel === 'report') {
      setPanelOverride({ scope: panelScope, panel: 'closed' })
    }
    requestAnimationFrame(() => {
      const heading = document.getElementById(inReport ? latestReportSection(id) : sectionAnchor(citation.turn, id))
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
      referenceLimit={useBackend ? maxReferences : undefined}
      disabledMessage={backendNotice}
      onAssociate={backendNotice && savedReview && !savedReview.backendUrl ? () => associateReview(savedReview.id) : undefined}
      onChange={(question) => updateDraft({ question, sample: false })}
      onReferences={(referenceIds) => updateDraft({ referenceIds })}
      onSubmit={submitQuestion}
      onLibrary={() => navigate({ kind: 'library' })}
      onStop={busy && activeReview?.source === 'backend' ? () => backendRequests.current.get(activeReview.id)?.abort() : undefined}
    />
  )

  return (
    <div className="app-window">
      {!sidebarDrawer && !inspectorDrawer && !reportDrawer && <a className="skip-link" href="#work-area">跳至工作区</a>}
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
            onCreateProject={() => openProjectForm('create')}
            onEditProject={() => openProjectForm('edit')}
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
            {latestReport && (
              <button ref={reportToggle} className="context-button report-entry" type="button" aria-expanded={showReport} aria-controls={panel === 'report' ? 'report-panel' : undefined} onClick={() => togglePanel('report')}>
                <FileText size={15} /> 综述
              </button>
            )}
            <button ref={officeToggle} className="context-button office-entry" type="button" aria-expanded={showOffice} aria-controls={showOffice ? 'office-panel' : undefined} onClick={() => togglePanel('office')}>
              <Building2 size={15} /> 办公室
            </button>
            {!useBackend && view.kind !== 'library' && <span className="demo-badge"><span /> 模拟数据</span>}
          </div>
        </header>
        {(!workspaceSaved || !recoverySaved) && <p className="workspace-storage-error" role="alert">浏览器未能保存工作区或任务记录。请先导出需要保留的综述，再刷新页面。</p>}

        <div className="workspace-body" data-office-open={showOffice} data-report-open={showReport}>
          <div className="workbench" inert={inspectorDrawer || reportDrawer}>
            <main className={view.kind === 'new' ? 'reader reader-start' : 'reader'} id="work-area" ref={scrollPane} tabIndex={-1}>
              {displayReview && (
                <Review
                  key={displayReview.id}
                  review={displayReview}
                  conversations={project.reviews}
                  runningPhase={activePhase}
                  responding={activeRun?.kind === 'response'}
                  connecting={activeRun?.kind === 'connecting'}
                  error={activeRun?.kind === 'failed' ? activeRun.error : undefined}
                  onRetry={activeRun?.kind === 'failed' && activeRun.error.retry && !activeArchived && !backendNotice
                    ? () => void runBackend(activeRun.review) : undefined}
                  onRecover={activeRun?.kind === 'failed' && activeRun.checkRun && recoverable ? () => void recoverRun(recoverable) : undefined}
                  onEditFailure={activeRun?.kind === 'failed' && !activeArchived && !backendNotice && activeRun.error.code !== 'RUN_PENDING' ? () => {
                    updateDraft({ question: activeRun.review.question, referenceIds: activeRun.review.referenceIds ?? [] })
                    input.current?.focus()
                  } : undefined}
                  onSettings={() => settingsDialog.current?.showModal()}
                  onConfigureProject={() => openProjectForm('edit')}
                  activeCitation={inspectorTab === 'citations' ? citation ?? undefined : undefined}
                  onCitation={showCitation}
                  onConversation={openReview}
                  reportVisible={showReport}
                  onPreviewReport={savedReview && latestReport ? () => setReportPreview(savedReview) : undefined}
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
              {view.kind === 'library' && <Library project={project} onConfigure={() => openProjectForm('edit')} onPreview={setPreview} />}
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
              onClose={() => closePanel('office')}
            />
          )}
          {panel === 'report' && savedReview && latestReport && (
            <>
              {reportDrawer && <button className="inspector-scrim" type="button" tabIndex={-1} aria-label="关闭综述面板" onClick={() => closePanel('report')} />}
              <ReportPanel
                review={savedReview}
                turn={latestReport.turn}
                version={versions.length}
                busy={busy}
                drawer={reportDrawer}
                hidden={citation !== null}
                onCitation={(index, trigger) => showCitation(latestReport.turnIndex, index, trigger, true)}
                onPreview={() => setReportPreview(savedReview)}
                onClose={() => closePanel('report')}
              />
            </>
          )}
          {citedTurn && citation && (
            <>
              <button className="inspector-scrim" type="button" tabIndex={-1} aria-label="关闭证据面板" onClick={closeInspector} />
              <EvidenceInspector
                review={citedTurn}
                backend={backend}
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
          id={projectForm.id}
          project={projectForm.kind === 'edit' ? project : undefined}
          otherFolders={workspace.projects.filter((entry) => entry.id !== projectForm.id).map((entry) => entry.folder)}
          backend={backend.useDemo ? undefined : backend}
          locked={projectForm.kind === 'edit' && (project.reviews.some((review) => review.backendUrl === backend.url) ||
            recoverableRuns.some((run) => run.projectId === project.id && run.backendUrl === backend.url))}
          onSave={configureProject}
          onClose={() => setProjectForm(null)}
        />
      )}
      {knowledgePicker && <FolderDialog backend={backend} initialPath={project.folder} onClose={() => setKnowledgePicker(false)}
        onSelect={(path) => { setKnowledgePicker(false); void addKnowledgeFolder(path) }}
        onManual={() => { setKnowledgePicker(false); openProjectForm('edit') }} />}
      {reviewToDelete && <DeleteReviewDialog review={reviewToDelete} onDelete={(localOnly) => deleteReview(reviewToDelete, localOnly)} onClose={() => setReviewToDelete(null)} />}
      {preview && <PagePreview evidence={preview} backend={backend} onClose={() => setPreview(null)} />}
      {reportPreview && <ReportPreview review={reportPreview} onClose={() => setReportPreview(null)} />}
    </div>
  )
}
