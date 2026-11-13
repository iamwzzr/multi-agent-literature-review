import { pdfBackendUrl } from './backend'
import { demoReviews } from './demo'
import type { ReviewRun, ReviewTurn } from './demo'

export type ProjectConfig = {
  name: string
  folder: string
  knowledgePaths: string[]
}

export type Project = ProjectConfig & {
  id: string
  reviews: ReviewRun[]
  archivedReviewIds?: string[]
  removedDemoIds?: string[]
}

export type Workspace = {
  projects: Project[]
  activeProjectId: string
}

export type RecoverableRun = {
  projectId: string
  conversationId: string
  runId: string
  backendUrl: string
  title: string
  question: string
  referenceIds?: string[]
}

const workspaceKey = 'folio.workspace'
const recoveryKey = 'folio.recoverable-runs'
const seededReviews = (...ids: string[]) => demoReviews.filter(({ id }) => ids.includes(id))
const defaultWorkspace: Workspace = {
  activeProjectId: 'literature',
  projects: [
    {
      id: 'literature',
      name: '文献综述研究',
      folder: '~/Research/literature-review',
      knowledgePaths: ['~/Research/literature-review/papers', '~/Research/literature-review/notes'],
      reviews: seededReviews('collaboration', 'retrieval', 'extended-review'),
    },
    {
      id: 'citations',
      name: '引用核查实验',
      folder: '~/Research/citation-audit',
      knowledgePaths: ['~/Research/citation-audit/papers'],
      reviews: seededReviews('verification', 'evidence-gap'),
    },
    {
      id: 'empty-test',
      name: '空白测试项目',
      folder: '~/Research/folio-empty-test',
      knowledgePaths: [],
      reviews: [],
    },
  ],
}

function addFixtures(workspace: Workspace): Workspace {
  const projects = workspace.projects.map((project) => {
    const reviews = project.reviews.map(restoreReview)
    const seed = defaultWorkspace.projects.find(({ id }) => id === project.id)
    const additions = seed?.reviews.filter(({ id }) => (
      !project.removedDemoIds?.includes(id) && !project.reviews.some((review) => review.id === id)
    )) ?? []
    return { ...project, reviews: [...reviews, ...additions] }
  })
  for (const seed of defaultWorkspace.projects) {
    if (!projects.some(({ id, folder }) => id === seed.id || folder === seed.folder)) projects.push(seed)
  }
  return { ...workspace, projects }
}

function restoreReview(review: ReviewRun): ReviewRun {
  let previous: ReviewTurn | undefined
  function restore<T extends ReviewTurn>(turn: T): T {
    if (turn.reportUnchanged && previous && turn.sections.length === 0) {
      return { ...turn, sections: previous.sections, evidence: previous.evidence, verification: previous.verification }
    }
    if (!turn.reportUnchanged) previous = turn
    return turn
  }
  const history = review.history?.map(restore)
  const restored = restore({ ...review, history })
  if (restored.source !== 'backend' || restored.backendUrl) return restored
  const urls = new Set<string>()
  for (const turn of [...(history ?? []), restored]) {
    for (const { pdfUrl } of turn.evidence) {
      const url = pdfUrl && pdfBackendUrl(pdfUrl)
      if (url) urls.add(url)
    }
  }
  return urls.size === 1 ? { ...restored, backendUrl: urls.values().next().value } : restored
}

export function removeReview(project: Project, id: string): Project {
  const isFixture = defaultWorkspace.projects.some((seed) => seed.id === project.id && seed.reviews.some((review) => review.id === id))
  return {
    ...project,
    reviews: project.reviews.filter((review) => review.id !== id),
    archivedReviewIds: project.archivedReviewIds?.filter((reviewId) => reviewId !== id),
    removedDemoIds: isFixture ? [...new Set([...(project.removedDemoIds ?? []), id])] : project.removedDemoIds,
  }
}

export function readWorkspace(): Workspace {
  try {
    const saved = sessionStorage.getItem(workspaceKey)
    if (saved) {
      const workspace = JSON.parse(saved) as Workspace
      if (Array.isArray(workspace.projects) &&
        workspace.projects.every((project) => Array.isArray(project.knowledgePaths) && Array.isArray(project.reviews)) &&
        workspace.projects.some(({ id }) => id === workspace.activeProjectId)) return addFixtures(workspace)
    }
  } catch {
    // A fresh workspace is available when browser storage is restricted or invalid.
  }
  return defaultWorkspace
}

export function saveWorkspace(workspace: Workspace) {
  try {
    sessionStorage.setItem(workspaceKey, JSON.stringify(workspace, (_key, value) => {
      if (value?.reportUnchanged && Array.isArray(value.sections) && Array.isArray(value.evidence)) {
        return { ...value, sections: [], evidence: [] }
      }
      return value
    }))
    return true
  } catch {
    return false
  }
}

export function readRecoverableRuns(): RecoverableRun[] {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(recoveryKey) ?? '[]')
    return Array.isArray(saved) ? saved.filter((run) => run && typeof run.runId === 'string' && typeof run.projectId === 'string' &&
      typeof run.conversationId === 'string' && typeof run.backendUrl === 'string' && typeof run.question === 'string' &&
      typeof run.title === 'string') : []
  } catch {
    return []
  }
}

export function saveRecoverableRuns(runs: RecoverableRun[]) {
  try {
    if (runs.length) sessionStorage.setItem(recoveryKey, JSON.stringify(runs))
    else sessionStorage.removeItem(recoveryKey)
    return true
  } catch {
    return false
  }
}
