import { useEffect, useRef, useState } from 'react'
import { ChevronRight, Folder, FolderOpen, FolderPlus, LibraryBig, MessageSquareText, Settings, SlidersHorizontal, SquarePen, X } from 'lucide-react'
import type { ReviewRun } from './demo'
import type { Project } from './projects'

const folioIcon = `${import.meta.env.BASE_URL}folio.svg`
const minWidth = 184
const maxWidth = 336

export function Sidebar({ projects, projectId, reviews, runningIds, activeReviewId, view, drawer, width,
  onProject, onReview, onNew, onLibrary, onCreateProject, onEditProject, onSettings, onClose, onResize }: {
  projects: Project[]
  projectId: string
  reviews: ReviewRun[]
  runningIds: string[]
  activeReviewId?: string
  view: 'new' | 'review' | 'library'
  drawer: boolean
  width: number
  onProject: (id: string) => void
  onReview: (id: string) => void
  onNew: () => void
  onLibrary: () => void
  onCreateProject: () => void
  onEditProject: () => void
  onSettings: () => void
  onClose: () => void
  onResize: (width: number) => void
}) {
  const close = useRef<HTMLButtonElement>(null)
  const [collapsedProject, setCollapsedProject] = useState<string | null>(null)

  useEffect(() => {
    if (drawer) close.current?.focus()
  }, [drawer])

  return (
    <aside
      className="sidebar"
      id="workspace-sidebar"
      aria-label="工作区侧边栏"
      style={drawer ? undefined : { width }}
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
        <button className="sidebar-row new-review-button" type="button" onClick={onNew} aria-current={view === 'new' ? 'page' : undefined}>
          <SquarePen size={16} /> 新建综述
        </button>
        <div className="sidebar-projects-heading">
          <h2>项目</h2>
          <button className="icon-button" type="button" aria-label="新建项目" title="新建项目" onClick={onCreateProject}><FolderPlus size={16} /></button>
        </div>
        <ul className="project-tree">
          {projects.map((project) => {
            const active = project.id === projectId
            const expanded = active && project.id !== collapsedProject
            return (
              <li key={project.id}>
                <button
                  className="sidebar-row project-row"
                  type="button"
                  title={project.folder}
                  aria-current={active ? 'true' : undefined}
                  aria-expanded={expanded}
                  onClick={() => {
                    if (active) setCollapsedProject(expanded ? project.id : null)
                    else {
                      setCollapsedProject(null)
                      onProject(project.id)
                    }
                  }}
                >
                  <ChevronRight className="project-chevron" size={13} />
                  {expanded ? <FolderOpen size={16} /> : <Folder size={16} />}
                  <span>{project.name}</span>
                </button>
                {expanded && (
                  <div className="project-branch">
                    <div className="project-library-row">
                      <button className="sidebar-row library-button" type="button" onClick={onLibrary} aria-current={view === 'library' ? 'page' : undefined}>
                        <LibraryBig size={15} /> <span>知识库</span> <span className="sidebar-count">{project.knowledgePaths.length}</span>
                      </button>
                      <button className="icon-button project-config" type="button" aria-label="配置知识库" title="配置知识库路径" onClick={onEditProject}><SlidersHorizontal size={14} /></button>
                    </div>
                    {project.knowledgePaths.length > 0 && (
                      <ul className="knowledge-paths" aria-label="知识库路径">
                        {project.knowledgePaths.map((path) => (
                          <li key={path} title={path}><Folder size={12} /> <span>{path.split(/[\\/]+/).filter(Boolean).at(-1) ?? path}</span></li>
                        ))}
                      </ul>
                    )}
                    <h3 className="project-section-label">对话</h3>
                    {reviews.length === 0 && <p className="project-empty">提交研究问题后，对话会显示在这里。</p>}
                    <ul className="review-history">
                      {reviews.map((review) => (
                        <li key={review.id}>
                          <button className="sidebar-row history-row" type="button" title={review.title} aria-current={activeReviewId === review.id ? 'page' : undefined} onClick={() => onReview(review.id)}>
                            <MessageSquareText size={15} /> <span>{review.title}</span>
                            {runningIds.includes(review.id) && <span className="sidebar-run-dot" role="img" aria-label="运行中" title="运行中" />}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <button className="sidebar-row settings-button" type="button" aria-haspopup="dialog" aria-controls="workspace-settings" onClick={onSettings}>
          <Settings size={17} /> 设置
        </button>
      </div>
      {!drawer && <SidebarResizer width={width} onResize={onResize} />}
    </aside>
  )
}

function SidebarResizer({ width, onResize }: { width: number; onResize: (width: number) => void }) {
  const drag = useRef<{ pointerId: number; x: number; width: number } | null>(null)

  function resize(value: number) {
    onResize(Math.min(maxWidth, Math.max(minWidth, Math.round(value))))
  }

  return (
    <div
      className="sidebar-resizer"
      role="separator"
      aria-label="调整侧栏宽度"
      aria-controls="workspace-sidebar"
      aria-orientation="vertical"
      aria-valuemin={minWidth}
      aria-valuemax={maxWidth}
      aria-valuenow={width}
      tabIndex={0}
      title="拖动调整侧栏宽度"
      onPointerDown={(event) => {
        if (!event.isPrimary || event.button !== 0) return
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { pointerId: event.pointerId, x: event.clientX, width }
      }}
      onPointerMove={(event) => {
        const start = drag.current
        if (start?.pointerId === event.pointerId) resize(start.width + event.clientX - start.x)
      }}
      onLostPointerCapture={() => { drag.current = null }}
      onKeyDown={(event) => {
        let next: number
        switch (event.key) {
          case 'ArrowLeft': next = width - 12; break
          case 'ArrowRight': next = width + 12; break
          case 'Home': next = minWidth; break
          case 'End': next = maxWidth; break
          default: return
        }
        event.preventDefault()
        resize(next)
      }}
    />
  )
}
