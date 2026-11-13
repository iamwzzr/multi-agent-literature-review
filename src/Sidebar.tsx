import { useEffect, useId, useRef, useState } from 'react'
import { Archive, ArchiveRestore, ChevronRight, Ellipsis, Folder, FolderOpen, FolderPlus, LibraryBig, MessageSquareText, Plus, Settings, SlidersHorizontal, SquarePen, Trash2, X } from 'lucide-react'
import type { ReviewRun } from './demo'
import type { Project } from './projects'

const folioIcon = `${import.meta.env.BASE_URL}folio.svg`
const minWidth = 184
const maxWidth = 336

export function Sidebar({ projects, projectId, reviews, archivedIds, runningIds, activeReviewId, view, drawer, width, pickingFolder, folderError,
  onProject, onReview, onArchive, onDelete, onNew, onNewConversation, onLibrary, onAddKnowledge, onCreateProject, onEditProject, onSettings, onClose, onResize }: {
  projects: Project[]
  projectId: string
  reviews: ReviewRun[]
  archivedIds: ReadonlySet<string>
  runningIds: string[]
  activeReviewId?: string
  view: 'new' | 'review' | 'library'
  drawer: boolean
  width: number
  pickingFolder: boolean
  folderError?: string
  onProject: (id: string) => void
  onReview: (id: string) => void
  onArchive: (id: string, archive: boolean) => void
  onDelete: (review: ReviewRun) => void
  onNew: () => void
  onNewConversation: () => void
  onLibrary: () => void
  onAddKnowledge: () => void
  onCreateProject: () => void
  onEditProject: () => void
  onSettings: () => void
  onClose: () => void
  onResize: (width: number) => void
}) {
  const close = useRef<HTMLButtonElement>(null)
  const archiveSummary = useRef<HTMLElement>(null)
  const [collapsedProject, setCollapsedProject] = useState<string | null>(null)
  const activeReviews = reviews.filter(({ id }) => !archivedIds.has(id))
  const archivedReviews = reviews.filter(({ id }) => archivedIds.has(id))

  useEffect(() => {
    if (drawer) close.current?.focus()
  }, [drawer])

  function reviewList(entries: ReviewRun[], archived: boolean) {
    return (
      <ul className="review-history">
        {entries.map((review) => (
          <li className="conversation-row" key={review.id} data-current={activeReviewId === review.id}>
            <button id={'conversation-' + review.id} className="sidebar-row history-row" type="button" title={review.title} aria-current={activeReviewId === review.id ? 'page' : undefined} onClick={() => onReview(review.id)}>
              <MessageSquareText size={15} /> <span>{review.title}</span>
              {runningIds.includes(review.id) && <span className="sidebar-run-dot" role="img" aria-label="运行中" title="运行中" />}
            </button>
            <ConversationActions
              title={review.title}
              archived={archived}
              onArchive={() => {
                onArchive(review.id, !archived)
                requestAnimationFrame(() => (archived ? document.getElementById('conversation-' + review.id) : archiveSummary.current)?.focus())
              }}
              onDelete={() => onDelete(review)}
            />
          </li>
        ))}
      </ul>
    )
  }

  return (
    <aside
      className="sidebar"
      id="workspace-sidebar"
      aria-label="工作区侧边栏"
      style={drawer ? undefined : { width }}
      onKeyDown={(event) => {
        if (drawer && event.key === 'Escape' && !(event.target as HTMLElement).closest('.conversation-actions')) onClose()
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
                      <button className="icon-button project-shortcut" type="button" aria-label="添加知识库文件夹" title="添加知识库文件夹" disabled={pickingFolder} onClick={onAddKnowledge}><Plus size={16} /></button>
                    </div>
                    {folderError && <p className="project-empty" role="status">{folderError}</p>}
                    {project.knowledgePaths.length > 0 && (
                      <ul className="knowledge-paths" aria-label="知识库路径">
                        {project.knowledgePaths.map((path) => (
                          <li key={path} title={path}><Folder size={12} /> <span>{path.split(/[\\/]+/).filter(Boolean).at(-1) ?? path}</span></li>
                        ))}
                      </ul>
                    )}
                    <div className="project-section-heading">
                      <h3 className="project-section-label">对话</h3>
                      <button className="icon-button project-shortcut" type="button" aria-label="新建对话" title="新建对话" onClick={onNewConversation}><Plus size={16} /></button>
                    </div>
                    {activeReviews.length > 0 ? reviewList(activeReviews, false) : (
                      <p className="project-empty">{archivedReviews.length ? '没有未归档的对话。' : '提交研究问题后，对话会显示在这里。'}</p>
                    )}
                    {archivedReviews.length > 0 && (
                      <details className="archive-group">
                        <summary className="sidebar-row archive-summary" ref={archiveSummary}>
                          <ChevronRight className="archive-chevron" size={12} /> <Archive size={14} /> 已归档 <span className="sidebar-count">{archivedReviews.length}</span>
                        </summary>
                        {reviewList(archivedReviews, true)}
                      </details>
                    )}
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

function ConversationActions({ title, archived, onArchive, onDelete }: {
  title: string
  archived: boolean
  onArchive: () => void
  onDelete: () => void
}) {
  const menuId = useId()
  const menu = useRef<HTMLDivElement>(null)

  return (
    <>
      <button
        className="icon-button conversation-more"
        type="button"
        popoverTarget={menuId}
        aria-label={'对话操作：' + title}
        title="对话操作"
        onClick={({ currentTarget }) => {
          const panel = menu.current
          if (!panel) return
          const { top, bottom, right } = currentTarget.getBoundingClientRect()
          const below = window.innerHeight - bottom >= 92
          panel.style.right = Math.max(8, Math.min(window.innerWidth - right, window.innerWidth - 160)) + 'px'
          panel.style.top = below ? bottom + 4 + 'px' : 'auto'
          panel.style.bottom = below ? 'auto' : window.innerHeight - top + 4 + 'px'
        }}
      ><Ellipsis size={16} /></button>
      <div
        ref={menu}
        id={menuId}
        popover="auto"
        className="conversation-actions"
        role="group"
        aria-label="对话操作"
        onToggle={(event) => {
          if (event.newState === 'open') event.currentTarget.querySelector('button')?.focus()
        }}
      >
        <button type="button" onClick={() => { menu.current?.hidePopover(); onArchive() }}>
          {archived ? <ArchiveRestore size={15} /> : <Archive size={15} />} {archived ? '恢复对话' : '归档对话'}
        </button>
        <button className="delete-action" type="button" aria-haspopup="dialog" onClick={() => { menu.current?.hidePopover(); onDelete() }}>
          <Trash2 size={15} /> 删除对话
        </button>
      </div>
    </>
  )
}

export function DeleteReviewDialog({ review, onDelete, onClose }: { review: ReviewRun; onDelete: (localOnly: boolean) => Promise<void>; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
    cancel.current?.focus()
  }, [])

  async function confirm(localOnly: boolean) {
    setDeleting(true)
    setError('')
    try {
      await onDelete(localOnly)
    } catch (failure) {
      setDeleting(false)
      setError(failure instanceof Error ? failure.message : '无法删除对话。')
    }
  }

  return (
    <dialog className="page-dialog delete-dialog" ref={dialog} aria-labelledby="delete-review-title" aria-describedby="delete-review-detail" onClose={onClose}
      onCancel={(event) => { if (deleting) event.preventDefault() }}>
      <div className="dialog-toolbar">
        <span id="delete-review-title"><Trash2 size={16} /> 删除对话</span>
        <button className="icon-button" type="button" disabled={deleting} aria-label="关闭删除确认" onClick={() => dialog.current?.close()}><X size={17} /></button>
      </div>
      <div className="delete-dialog-body">
        <p id="delete-review-detail">{review.source === 'backend'
          ? `删除「${review.title}」及原后端保存的报告与运行记录。仅移除本标签页会保留后端记录。`
          : `「${review.title}」及其所有回复将被删除，无法恢复。`}</p>
        {error && <p role="alert">{error}</p>}
        <div className="dialog-actions">
          <button ref={cancel} type="button" disabled={deleting} onClick={() => dialog.current?.close()}>取消</button>
          {review.source === 'backend' && <button type="button" disabled={deleting} onClick={() => void confirm(true)}>仅移除本标签页</button>}
          <button className="danger-button" type="button" disabled={deleting} onClick={() => void confirm(false)}>{deleting ? '删除中…' : '删除对话'}</button>
        </div>
      </div>
    </dialog>
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
