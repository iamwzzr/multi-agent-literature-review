import type { Evidence, ReviewRun, ReviewSection, ReviewTurn } from './demo'
import type { Project } from './projects'
import { agents } from './workflow'
import type { AgentActivity, AgentId } from './workflow'

export const defaultBackendUrl = 'http://localhost:35549'
const settingsKey = 'folio.backend'
const apiPrefix = '/api/v1'
const streamType = 'application/x-ndjson'
const agentIds = new Set<string>(agents.map(({ id }) => id))

export type BackendSettings = { url: string; useDemo: boolean }
type EvidenceItem = Omit<Evidence, 'source' | 'pdfUrl'>
type ReviewOutput = Pick<ReviewTurn, 'sections' | 'evidence'>
type ContextTurn = { question: string; sections: ReviewSection[]; evidence: EvidenceItem[] }
type ReviewRequest = {
  conversationId: string
  project: { id: string; name: string; workingDirectory: string; knowledgePaths: string[] }
  question: string
  history: ContextTurn[]
  references: { conversationId: string; title: string; turn: ContextTurn }[]
}
type ReviewUpdate = { kind: 'phase'; phase: AgentActivity } | ({ kind: 'report' } & ReviewOutput)

export function normalizeBackendUrl(input: string) {
  const value = input.trim() || defaultBackendUrl
  const url = URL.canParse(value) ? new URL(value) : null
  if (!url || !/^https?:\/\//i.test(value) || url.username || url.password || url.search || url.hash) {
    throw new Error('请输入 HTTP 或 HTTPS 服务地址，地址中请勿包含账号、密码、查询参数或锚点。')
  }
  return url.origin + url.pathname.replace(/\/+$/, '')
}

export function readBackendSettings(): BackendSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(settingsKey) ?? '{}')
    return {
      url: normalizeBackendUrl(typeof saved?.url === 'string' ? saved.url : ''),
      useDemo: saved?.useDemo === true,
    }
  } catch {
    return { url: defaultBackendUrl, useDemo: false }
  }
}

export function saveBackendSettings(settings: BackendSettings) {
  try {
    localStorage.setItem(settingsKey, JSON.stringify(settings))
  } catch {
    // Settings remain available in the current page.
  }
}

function toContext({ question, sections, evidence }: ReviewTurn): ContextTurn {
  return {
    question,
    sections,
    evidence: evidence.map(({ paper, page, excerpt, context }) => ({ paper, page, excerpt, context })),
  }
}

export function reviewRequest(project: Project, review: ReviewRun): ReviewRequest {
  return {
    conversationId: review.id,
    project: { id: project.id, name: project.name, workingDirectory: project.folder, knowledgePaths: project.knowledgePaths },
    question: review.question,
    history: (review.history ?? []).map(toContext),
    references: project.reviews
      .filter(({ id, source }) => source === 'backend' && review.referenceIds?.includes(id) && !project.archivedReviewIds?.includes(id))
      .map((reference) => ({ conversationId: reference.id, title: reference.title, turn: toContext(reference) })),
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

async function backendFetch(url: string, endpoint: string, init: RequestInit) {
  let response: Response
  try {
    response = await fetch(url + apiPrefix + endpoint, {
      ...init,
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
    })
  } catch (failure) {
    if (init.signal?.aborted) throw failure
    throw new Error('无法连接后端 ' + url + '。请检查服务地址和跨域配置。')
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    if (isRecord(payload) && isRecord(payload.error) && isText(payload.error.message)) throw new Error(payload.error.message)
    throw new Error('后端返回 HTTP ' + response.status + '。')
  }
  return response
}

export async function checkBackend(url: string, signal: AbortSignal) {
  const timeout = AbortSignal.timeout(5000)
  try {
    const response = await backendFetch(url, '/health', {
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
  return new Error('后端返回的数据不符合 Folio v1 流式接口。')
}

export async function streamBackendReview(url: string, request: ReviewRequest, signal: AbortSignal, onUpdate: (update: ReviewUpdate) => void): Promise<ReviewOutput> {
  const response = await backendFetch(url, '/reviews/stream', {
    method: 'POST',
    headers: { Accept: streamType, 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== streamType || !response.body) {
    await response.body?.cancel().catch(() => undefined)
    throw invalidStream()
  }

  let sections: ReviewSection[] = []
  let evidence: Evidence[] = []
  let completed = false

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
      case 'evidence': {
        if (event.index !== evidence.length + 1 || !isEvidence(event.item)) throw invalidStream()
        const { paper, page, excerpt, context } = event.item
        let pdfUrl: string | undefined
        if (paper.pdfAvailable) {
          const pdf = new URL(url + apiPrefix + '/papers/pdf')
          pdf.search = new URLSearchParams({ projectId: request.project.id, paperId: paper.id }).toString()
          pdf.hash = 'page=' + page
          pdfUrl = pdf.href
        }
        evidence = [...evidence, { paper, page, excerpt, context, source: 'backend', pdfUrl }]
        if (sections.length === 0) return
        break
      }
      case 'section':
        if (!isText(event.id) || !isText(event.heading) || sections.some(({ id }) => id === event.id)) throw invalidStream()
        sections = [...sections, { id: event.id, heading: event.heading, paragraphs: [] }]
        break
      case 'delta': {
        const { sectionId, paragraph, text } = event
        const section = sections.find(({ id }) => id === sectionId)
        if (!section || typeof text !== 'string' || typeof paragraph !== 'number' ||
          !Number.isInteger(paragraph) || paragraph < 0 || paragraph > section.paragraphs.length) throw invalidStream()
        const paragraphs = [...section.paragraphs]
        paragraphs[paragraph] = (paragraphs[paragraph] ?? '') + text
        sections = sections.map((entry) => entry === section ? { ...entry, paragraphs } : entry)
        break
      }
      case 'done': {
        const paragraphs = sections.flatMap((section) => section.paragraphs)
        if (!paragraphs.some(isText) || paragraphs.some((text) => Array.from(text.matchAll(/\[\[(\d+)\]\]/g), ([, index]) => Number(index))
          .some((index) => index < 1 || index > evidence.length))) throw invalidStream()
        completed = true
        return
      }
      case 'error':
        if (!isText(event.code) || !isText(event.message)) throw invalidStream()
        throw new Error(event.message)
      default:
        throw invalidStream()
    }
    onUpdate({ kind: 'report', sections, evidence })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (!completed) {
      const chunk = await reader.read().catch((failure) => {
        if (signal.aborted) throw failure
        throw new Error('与后端的连接已中断。')
      })
      if (chunk.done) {
        consumeLine(buffer + decoder.decode())
        break
      }
      const lines = (buffer + decoder.decode(chunk.value, { stream: true })).split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        consumeLine(line)
        if (completed) break
      }
    }
    if (!completed) throw new Error('后端连接已结束，本轮综述尚未完成。')
    return { sections, evidence }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
