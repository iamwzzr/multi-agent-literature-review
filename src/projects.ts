import { demoReviews } from './demo'
import type { ReviewRun } from './demo'

export type ProjectConfig = {
  name: string
  folder: string
  knowledgePaths: string[]
}

export type Project = ProjectConfig & {
  id: string
  reviews: ReviewRun[]
}

export type Workspace = {
  projects: Project[]
  activeProjectId: string
}

const workspaceKey = 'folio.workspace'
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
    const seed = defaultWorkspace.projects.find(({ id }) => id === project.id)
    const additions = seed?.reviews.filter((sample) => !project.reviews.some(({ id }) => id === sample.id)) ?? []
    return additions.length ? { ...project, reviews: [...project.reviews, ...additions] } : project
  })
  for (const seed of defaultWorkspace.projects) {
    if (!projects.some(({ id, folder }) => id === seed.id || folder === seed.folder)) projects.push(seed)
  }
  return { ...workspace, projects }
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
    sessionStorage.setItem(workspaceKey, JSON.stringify(workspace))
  } catch {
    // The workspace can still be used in the current tab.
  }
}
