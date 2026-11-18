import { verificationLabels } from './demo'
import type { Evidence, ReviewRun, ReviewSection, ReviewTurn } from './demo'
import type { Project, ProjectConfig } from './projects'
import { agents } from './workflow'
import type { AgentActivity, AgentId } from './workflow'

export const defaultBackendUrl = 'http://localhost:35549'
const settingsKey = 'folio.backend'
const apiPrefix = '/api/v1'
const streamType = 'application/x-ndjson'
const agentIds = new Set<string>(agents.map(({ id }) => id))
const maxRequestBytes = 2_000_000
const maxStreamBytes = 4 * 1024 * 1024
const maxStreamLine = 256 * 1024
const streamIdleMs = 30_000
export const maxReferences = 10
export const maxKnowledgePaths = 20

export type BackendSettings = { url: string; useDemo: boolean; token?: string }
type EvidenceItem = Omit<Evidence, 'source' | 'pdfUrl'>
type ReviewOutput = Pick<ReviewTurn, 'sections' | 'evidence' | 'reply' | 'reportUnchanged' | 'verification' | 'taskStatus' | 'audit'>
type ContextTurn = Omit<ReviewOutput, 'evidence' | 'verification' | 'taskStatus' | 'audit'> & { question: string; evidence: EvidenceItem[] }
type ProjectRequest = { id: string; name: string; workingDirectory: string; knowledgePaths: string[] }
type ReviewRequest = {
  architecture: string
  source_mode: string
  allow_local_metadata_lookup: boolean
  uploaded_file_ids: string[]
  online_query?: string
  research_budget: Record<string, number>
  conversationId: string
  project: ProjectRequest
  question: string
  history: ContextTurn[]
  references: { conversationId: string; title: string; turn: ContextTurn }[]
}
type ReviewUpdate = { kind: 'phase'; phase: AgentActivity } | ({ kind: 'report' } & ReviewOutput)

type BackendErrorDetails = { code?: string; agent?: AgentId; providerStatus?: number; retryable?: boolean }

export class BackendRequestError extends Error {
  constructor(message: string, readonly status: number, readonly details: BackendErrorDetails = {}) {
    super(message)
  }
}

export function normalizeBackendUrl(input: string) {
  const value = input.trim() || defaultBackendUrl
  const url = URL.canParse(value) ? new URL(value) : null
  if (!url || !/^https?:\/\//i.test(value) || url.username || url.password || url.search || url.hash) {
    throw new Error('请输入 HTTP 或 HTTPS 服务地址，地址中请勿包含账号、密码、查询参数或锚点。')
  }
  if (url.protocol === 'http:' && url.hostname !== 'localhost' && url.hostname !== '[::1]' && !/^127(?:\.\d{1,3}){3}$/.test(url.hostname)) {
    throw new Error('远程后端地址必须使用 HTTPS。')
  }
  return url.origin + url.pathname.replace(/\/+$/, '')
}

export function readBackendSettings(): BackendSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(settingsKey) ?? '{}')
    const url = normalizeBackendUrl(typeof saved?.url === 'string' ? saved.url : '')
    let token: string | undefined
    try {
      const access = JSON.parse(sessionStorage.getItem(settingsKey + '.access') ?? '{}')
      if (access?.url === url && typeof access.token === 'string') token = access.token
    } catch {
      // The current tab can still connect after entering its token again.
    }
    return {
      url,
      useDemo: saved?.useDemo === true,
      token,
    }
  } catch {
    return { url: defaultBackendUrl, useDemo: false }
  }
}

export function saveBackendSettings(settings: BackendSettings) {
  try {
    localStorage.setItem(settingsKey, JSON.stringify({ url: settings.url, useDemo: settings.useDemo }))
  } catch {
    // Settings remain available in the current page.
  }
  try {
    const accessKey = settingsKey + '.access'
    if (settings.token) sessionStorage.setItem(accessKey, JSON.stringify({ url: settings.url, token: settings.token }))
    else sessionStorage.removeItem(accessKey)
  } catch {
    // The token remains in memory for this page.
  }
}

export function pdfBackendUrl(value: string) {
  try {
    const pdf = new URL(value)
    const endpoint = apiPrefix + '/papers/pdf'
    if (!pdf.pathname.endsWith(endpoint) || pdf.username || pdf.password ||
        !pdf.searchParams.has('projectId') || !pdf.searchParams.has('paperId')) return
    return normalizeBackendUrl(pdf.origin + pdf.pathname.slice(0, -endpoint.length))
  } catch {
    return undefined
  }
}

function toContext({ question, sections, evidence, reply, reportUnchanged }: ReviewTurn, includeDraft: boolean, includeEvidence = includeDraft): ContextTurn {
  return {
    question,
    sections: includeDraft ? sections : [],
    evidence: includeEvidence ? evidence.map(({ paper, page, excerpt, context }) => ({ paper, page, excerpt, context })) : [],
    reply,
    reportUnchanged,
  }
}

function projectRequest(id: string, { name, folder, knowledgePaths }: ProjectConfig): ProjectRequest {
  return { id, name, workingDirectory: folder, knowledgePaths }
}

export function reviewRequest(project: Project, review: ReviewRun): ReviewRequest {
  const history = (review.history ?? []).slice(-3)
  const references = project.reviews.filter(({ id, source, backendUrl }) => (
    source === 'backend' && backendUrl === review.backendUrl && review.referenceIds?.includes(id) && !project.archivedReviewIds?.includes(id)
  ))
  if (references.length > maxReferences || project.knowledgePaths.length > maxKnowledgePaths) {
    throw new Error(`每轮最多引用 ${maxReferences} 个对话，每个项目最多配置 ${maxKnowledgePaths} 个知识库路径。`)
  }
  const sources = readSources(project.id, review.backendUrl)
  return {
    architecture: 'three_agent', source_mode: sources.mode,
    allow_local_metadata_lookup: false,
    uploaded_file_ids: sources.mode === 'online' ? [] : sources.files.map(f => f.id),
    online_query: sources.query || undefined,
    research_budget: { documents: 10, feedback_batches: 1, model_calls: 60, tool_calls: 150, seconds: 600 },
    conversationId: review.id,
    project: { ...projectRequest(project.id, project), knowledgePaths: sources.mode === 'online' ? [] : project.knowledgePaths },
    question: review.question,
    history: history.map((turn, index) => toContext(turn, index === history.length - 1)),
    references: references.map((reference) => ({
      conversationId: reference.id, title: Array.from(reference.title).slice(0, 300).join(''),
      turn: toContext(reference, true, false),
    })),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && Boolean(value.trim())
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function isAgentId(value: unknown): value is AgentId {
  return typeof value === 'string' && agentIds.has(value)
}

function isAgentList(value: unknown): value is AgentId[] {
  return Array.isArray(value) && value.every(isAgentId)
}

function readBackendError(value: unknown, status: number, fallback: string, fallbackCode?: string) {
  const details = isRecord(value) ? value : {}
  return new BackendRequestError(isText(details.message) ? details.message : fallback, status, {
    code: isText(details.code) ? details.code : fallbackCode,
    agent: isAgentId(details.agent) ? details.agent : undefined,
    providerStatus: isPositiveInteger(details.providerStatus) && details.providerStatus >= 300 && details.providerStatus <= 599
      ? details.providerStatus : undefined,
    retryable: typeof details.retryable === 'boolean' ? details.retryable : undefined,
  })
}

function isPhase(event: Record<string, unknown>): event is AgentActivity & Record<string, unknown> {
  const { title, summary, working, done, feedback, taskDetails } = event
  return isText(title) && typeof summary === 'string' &&
    isAgentList(working) && isAgentList(done) &&
    (feedback === undefined || typeof feedback === 'boolean') &&
    (taskDetails === undefined || (isRecord(taskDetails) && Object.entries(taskDetails)
      .every(([id, text]) => isAgentId(id) && typeof text === 'string')))
}

function isEvidence(item: unknown): item is EvidenceItem {
  if (!isRecord(item) || !isRecord(item.paper)) return false
  const { paper, page, excerpt, context } = item
  return isText(paper.id) && isText(paper.title) && isText(paper.author) &&
    (paper.year === null || isPositiveInteger(paper.year)) &&
    isPositiveInteger(paper.pages) && typeof paper.summary === 'string' &&
    (paper.pdfAvailable === undefined || typeof paper.pdfAvailable === 'boolean') &&
    isPositiveInteger(page) && page <= paper.pages && isText(excerpt) && typeof context === 'string'
}

async function backendFetch({ url, token }: BackendSettings, endpoint: string, init: RequestInit) {
  let response: Response
  const headers = new Headers(init.headers)
  if (token) {
    try {
      headers.set('Authorization', 'Bearer ' + token)
    } catch {
      throw new BackendRequestError('请核对后端连接设置中的访问令牌。', 0, { code: 'AUTH_REQUIRED', retryable: false })
    }
  }
  try {
    response = await fetch(url + ((endpoint.endsWith('/uploads') || endpoint === '/reviews/stream') ? '/api/v2' : apiPrefix) + endpoint, {
      ...init,
      headers,
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
    })
  } catch (failure) {
    if (init.signal?.aborted) throw failure
    throw new BackendRequestError('请确认后端已启动，并检查服务地址、访问令牌和跨域配置。', 0, { code: 'BACKEND_UNREACHABLE' })
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    throw readBackendError(isRecord(payload) ? payload.error : undefined, response.status, '后端返回 HTTP ' + response.status + '。')
  }
  return response
}

export async function checkBackend(backend: BackendSettings, signal: AbortSignal) {
  const timeout = AbortSignal.timeout(5000)
  try {
    const response = await backendFetch(backend, '/health', {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.any([signal, timeout]),
    })
    const data: unknown = await response.json().catch(() => null)
    if (timeout.aborted) throw timeout.reason
    if (!isRecord(data) || data.status !== 'ok' || data.apiVersion !== 'v1') {
      throw new Error('服务已响应，但未返回 Folio v1 的健康检查结果。')
    }
  } catch (failure) {
    if (timeout.aborted) throw new Error('连接测试超时。请确认后端服务已启动。')
    throw failure
  }
}

function invalidStream() {
  return new BackendRequestError('请确认后端支持 Folio v1，并检查代理是否完整转发了响应。', 0, { code: 'INVALID_STREAM' })
}

function isVerification(value: unknown): value is NonNullable<ReviewTurn['verification']> {
  return typeof value === 'string' && Object.hasOwn(verificationLabels, value)
}

function reportEvidence(item: EvidenceItem, url: string, projectId: string): Evidence {
  const { paper, page } = item
  let pdfUrl: string | undefined
  if (paper.pdfAvailable) {
    const pdf = new URL(url + apiPrefix + '/papers/pdf')
    pdf.search = new URLSearchParams({ projectId, paperId: paper.id }).toString()
    pdf.hash = 'page=' + page
    pdfUrl = pdf.href
  }
  return { ...item, source: 'backend', pdfUrl }
}

function validReport(sections: ReviewSection[], evidenceCount: number) {
  const paragraphs = sections.flatMap((section) => section.paragraphs)
  return paragraphs.some(isText) && !paragraphs.some((text) => Array.from(text.matchAll(/\[\[(\d+)\]\]/g), ([, index]) => Number(index))
    .some((index) => index < 1 || index > evidenceCount))
}

export type FolderListing = {
  current: string | null
  parent: string | null
  folders: { name: string; path: string }[]
  truncated: boolean
}

export async function fetchFolders(backend: BackendSettings, path: string | null, signal: AbortSignal): Promise<FolderListing> {
  const endpoint = '/folders' + (path ? '?' + new URLSearchParams({ path }).toString() : '')
  const response = await backendFetch(backend, endpoint, { signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]) })
  const data = await response.json()
  if (!Array.isArray(data?.folders) || !(data.current === null || isText(data.current)) ||
      !(data.parent === null || isText(data.parent)) || !data.folders.every((entry: unknown) => (
        isRecord(entry) && isText(entry.name) && isText(entry.path)
      ))) throw new Error('后端返回的目录列表无效。')
  return data
}

export async function validateProject(backend: BackendSettings, id: string, config: ProjectConfig, signal?: AbortSignal): Promise<ProjectConfig> {
  const timeout = AbortSignal.timeout(8000)
  const response = await backendFetch(backend, '/projects/validate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(projectRequest(id, config)),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })
  const data = await response.json()
  if (!isText(data?.workingDirectory) || !Array.isArray(data.knowledgePaths) || !data.knowledgePaths.every(isText)) {
    throw new Error('后端返回的项目路径无效。')
  }
  return { name: config.name, folder: data.workingDirectory, knowledgePaths: data.knowledgePaths }
}

export async function deleteBackendConversation(backend: BackendSettings, projectId: string, conversationId: string) {
  const response = await backendFetch(backend, '/projects/' + encodeURIComponent(projectId) + '/conversations/' + encodeURIComponent(conversationId), {
    method: 'DELETE', signal: AbortSignal.timeout(8000),
  })
  if (response.status !== 204) throw new Error('后端未确认删除服务端记录。')
}

export async function getBackendRun(backend: BackendSettings, runId: string, projectId: string, conversationId: string, signal: AbortSignal) {
  const search = new URLSearchParams({ projectId, conversationId, includeArtifacts: 'false' })
  const response = await backendFetch(backend, '/runs/' + encodeURIComponent(runId) + '?' + search, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
  })
  const data: unknown = await response.json()
  if (!isRecord(data) || data.id !== runId || data.project_id !== projectId || data.conversation_id !== conversationId) throw invalidStream()
  if (data.status === 'running') return { status: 'running' } as const
  if (data.status === 'failed') {
    const error = readBackendError(data.error, 200, '上次任务执行失败，可根据错误码检查后端日志。',
      isText(data.error_code) ? data.error_code : undefined)
    return { status: 'failed', error } as const
  }
  if (data.status !== 'completed') return { status: 'interrupted' } as const
  const report = data.report
  if (!isRecord(report) || !Array.isArray(report.sections) || !Array.isArray(report.evidence) ||
      !report.evidence.every(isEvidence) || !report.sections.every((section): section is ReviewSection => (
        isRecord(section) && isText(section.id) && isText(section.heading) && Array.isArray(section.paragraphs) &&
        section.paragraphs.every((paragraph) => typeof paragraph === 'string')
      )) || !validReport(report.sections, report.evidence.length)) throw invalidStream()
  const output: ReviewOutput = {
    taskStatus: typeof report.task_status === 'string' ? report.task_status : undefined,
    audit: report,
    sections: report.sections, evidence: report.evidence.map((item) => reportEvidence(item, backend.url, projectId)),
    reply: typeof report.reply === 'string' ? report.reply : undefined,
    reportUnchanged: report.reportUnchanged === true ? true : undefined,
    verification: isVerification(report.verification) ? report.verification : undefined,
  }
  return { status: 'completed', output } as const
}

export async function fetchSourcePdf(backend: BackendSettings, pdfUrl: string, signal: AbortSignal) {
  if (pdfBackendUrl(pdfUrl) !== backend.url) throw new Error('请连接这条引用所属的后端。')
  const response = await backendFetch(backend, '/papers/pdf' + new URL(pdfUrl).search, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
  })
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/pdf') {
    await response.body?.cancel().catch(() => undefined)
    throw new Error('后端未返回可预览的 PDF。')
  }
  return response.blob()
}

export async function streamBackendReview(
  backend: BackendSettings,
  request: ReviewRequest,
  signal: AbortSignal,
  onUpdate: (update: ReviewUpdate) => void,
  onRun: (id: string) => void,
  previousReport?: ReviewTurn,
): Promise<ReviewOutput> {
  let awaitRunId = ''
  const originalOnRun = onRun
  onRun = (id) => { awaitRunId = id; originalOnRun(id) }
  const body = JSON.stringify(request)
  if (new TextEncoder().encode(body).length > maxRequestBytes) {
    throw new BackendRequestError('请减少引用的对话，或缩小本轮研究范围。', 413, { code: 'REQUEST_TOO_LARGE' })
  }

  let sections: ReviewSection[] = []
  let evidence: Evidence[] = []
  let reply: string | undefined
  let reportUnchanged: true | undefined
  let verification: ReviewTurn['verification']
  let taskStatus: string | undefined
  let completed = false
  let frame: number | undefined

  function publishReport() {
    if (frame !== undefined) return
    frame = requestAnimationFrame(() => {
      frame = undefined
      onUpdate({ kind: 'report', sections: sections.map((section) => ({ ...section, paragraphs: [...section.paragraphs] })),
        evidence: [...evidence], reply })
    })
  }

  function consumeLine(line: string) {
    if (!line.trim()) return
    let event: unknown
    try {
      event = JSON.parse(line)
    } catch {
      throw invalidStream()
    }
    if (!isRecord(event)) throw invalidStream()
    switch (event.type) {
      case 'phase':
        if (!isPhase(event)) throw invalidStream()
        onUpdate({ kind: 'phase', phase: event })
        return
      case 'reply':
        if (typeof event.text !== 'string') throw invalidStream()
        reply = (reply ?? '') + event.text
        break
      case 'evidence': {
        if (event.index !== evidence.length + 1 || !isEvidence(event.item)) throw invalidStream()
        evidence.push(reportEvidence(event.item, backend.url, request.project.id))
        if (sections.length === 0) return
        break
      }
      case 'section':
        if (!isText(event.id) || !isText(event.heading) || sections.some(({ id }) => id === event.id)) throw invalidStream()
        sections.push({ id: event.id, heading: event.heading, paragraphs: [] })
        break
      case 'delta': {
        const { sectionId, paragraph, text } = event
        const section = sections.find(({ id }) => id === sectionId)
        if (!section || typeof text !== 'string' || typeof paragraph !== 'number' ||
          !Number.isInteger(paragraph) || paragraph < 0 || paragraph > section.paragraphs.length) throw invalidStream()
        section.paragraphs[paragraph] = (section.paragraphs[paragraph] ?? '') + text
        break
      }
      case 'done': {
        if (typeof event.runId === 'string') onRun(event.runId)
        taskStatus = typeof event.taskStatus === 'string' ? event.taskStatus : undefined
        if (event.verification !== undefined && !isVerification(event.verification)) throw invalidStream()
        verification = event.verification as ReviewTurn['verification']
        if (event.reportUnchanged === true) {
          if (!isText(reply) || !previousReport?.sections.length || sections.length || evidence.length) throw invalidStream()
          sections = previousReport.sections
          evidence = previousReport.evidence
          verification ??= previousReport.verification
          reportUnchanged = true
          completed = true
          return
        }
        if (event.reportUnchanged !== undefined) throw invalidStream()
        if (!validReport(sections, evidence.length)) throw invalidStream()
        completed = true
        return
      }
      case 'error':
        if (!isText(event.code) || !isText(event.message)) throw invalidStream()
        throw readBackendError(event, 200, '后端执行失败。')
      default:
        throw invalidStream()
    }
    publishReport()
  }

  const idle = new AbortController()
  const requestSignal = AbortSignal.any([signal, idle.signal])
  let timeout: number | undefined
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  function resetIdle() {
    window.clearTimeout(timeout)
    timeout = window.setTimeout(() => idle.abort(), streamIdleMs)
  }

  resetIdle()
  try {
    const response = await backendFetch(backend, '/reviews/stream', {
      method: 'POST', headers: { Accept: streamType, 'Content-Type': 'application/json' }, body, signal: requestSignal,
    })
    if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== streamType || !response.body) {
      await response.body?.cancel().catch(() => undefined)
      throw invalidStream()
    }
    const runId = response.headers.get('X-Run-Id')
    if (runId && runId.length <= 128) onRun(runId)
    resetIdle()
    reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let bytes = 0
    while (!completed) {
      const chunk = await reader.read().catch((failure) => {
        if (requestSignal.aborted) throw failure
        throw new BackendRequestError('与后端的连接已中断，可以检查任务结果或重试。', 0, { code: 'STREAM_DISCONNECTED' })
      })
      if (chunk.done) {
        consumeLine(buffer + decoder.decode())
        break
      }
      resetIdle()
      bytes += chunk.value.byteLength
      if (bytes > maxStreamBytes) throw new BackendRequestError('请缩小研究范围以减少报告长度。', 0, { code: 'RESPONSE_TOO_LARGE' })
      const lines = (buffer + decoder.decode(chunk.value, { stream: true })).split('\n')
      buffer = lines.pop() ?? ''
      if (buffer.length > maxStreamLine) throw invalidStream()
      for (const line of lines) {
        if (line.length > maxStreamLine) throw invalidStream()
        consumeLine(line)
        if (completed) break
      }
    }
    if (!completed) throw new BackendRequestError('后端在综述完成前结束了连接，可以检查任务结果或重试。', 0, { code: 'STREAM_DISCONNECTED' })
    const recovered = awaitRunId ? await getBackendRun(backend, awaitRunId, request.project.id, request.conversationId, signal).catch(() => null) : null
    return { sections, evidence, reply, reportUnchanged, verification, taskStatus, ...(recovered?.status === 'completed' ? recovered.output : {}) }
  } catch (failure) {
    if (idle.signal.aborted && !signal.aborted) {
      throw new BackendRequestError('后端暂未发送进度，请检查服务或代理的流式连接。', 0, { code: 'STREAM_TIMEOUT' })
    }
    throw failure
  } finally {
    window.clearTimeout(timeout)
    if (frame !== undefined) cancelAnimationFrame(frame)
    if (reader) {
      await reader.cancel().catch(() => undefined)
      reader.releaseLock()
    }
  }
}

export type Sources = { mode: 'local' | 'online' | 'hybrid'; query: string; files: {id: string; name: string}[] }
function sourcesKey(id: string, url?: string) { return 'folio.sources.' + id + (url ? '.' + encodeURIComponent(url) : '') }
export function readSources(id: string, url?: string): Sources {
  const fallback: Sources = {mode:'local',query:'',files:[]}
  try {
    const value: unknown = JSON.parse(localStorage.getItem(sourcesKey(id,url)) ?? 'null')
    if (!isRecord(value)) return fallback
    return { mode: value.mode === 'online' || value.mode === 'hybrid' ? value.mode : 'local',
      query: typeof value.query === 'string' ? value.query.slice(0,1000) : '',
      files: Array.isArray(value.files) ? value.files.filter((f): f is Sources['files'][number] => isRecord(f) && isText(f.id) && isText(f.name)).slice(0,20) : [] }
  } catch { return fallback }
}
export function saveSources(id: string, value: Sources, url?: string) { localStorage.setItem(sourcesKey(id,url), JSON.stringify(value)) }
export async function uploadPdf(backend: BackendSettings, projectId: string, file: File) {
  const response = await backendFetch({...backend, url: backend.url}, '/projects/' + encodeURIComponent(projectId) + '/uploads', {method:'POST', headers:{'Content-Type':'application/pdf'}, body:file, signal:AbortSignal.timeout(60000)})
  const data = await response.json()
  if (!isText(data.file_id)) throw new Error('上传未返回文件 ID')
  return data.file_id as string
}
