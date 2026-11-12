import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ChevronRight, Folder, FolderOpen, X } from 'lucide-react'
import { BackendRequestError, fetchFolders } from './backend'
import type { BackendSettings, FolderListing } from './backend'

export function FolderDialog({ backend, initialPath = null, onSelect, onClose, onManual }: {
  backend: BackendSettings
  initialPath?: string | null
  onSelect: (path: string) => void
  onClose: () => void
  onManual?: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [path, setPath] = useState(initialPath)
  const [listing, setListing] = useState<FolderListing | null>(null)
  const [error, setError] = useState('')

  function browse(next: string | null) {
    setListing(null)
    setError('')
    setPath(next)
  }

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void fetchFolders(backend, path, controller.signal).then((value) => {
      if (!controller.signal.aborted) setListing(value)
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return
      setError(failure instanceof BackendRequestError && failure.status === 404
        ? '此后端尚不支持目录浏览，请手动填写路径。'
        : failure instanceof Error ? failure.message : '无法读取后端目录。')
    })
    return () => controller.abort()
  }, [backend, path])

  return (
    <dialog className="page-dialog project-dialog folder-dialog" ref={dialog} onClose={onClose} aria-labelledby="folder-dialog-title">
      <div className="dialog-toolbar">
        <span id="folder-dialog-title"><FolderOpen size={16} /> 选择后端目录</span>
        <button className="icon-button" type="button" aria-label="关闭目录选择" onClick={() => dialog.current?.close()}><X size={17} /></button>
      </div>
      <div className="project-form">
        <div className="project-path-actions">
          {path && <button className="context-button" type="button" onClick={() => browse(listing?.parent ?? null)}><ArrowLeft size={15} /> 上一级</button>}
          <span className="folder-current" title={path ?? undefined}>{listing?.current ?? path ?? '允许的根目录'}</span>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        {!error && !listing && <p role="status">正在读取目录…</p>}
        {listing && (
          <ul className="folder-options" aria-label="子目录">
            {listing.folders.map((folder) => (
              <li key={folder.path}><button className="sidebar-row" type="button" onClick={() => browse(folder.path)} title={folder.path}>
                <Folder size={16} /><span>{folder.name}</span><ChevronRight size={14} />
              </button></li>
            ))}
          </ul>
        )}
        {listing?.folders.length === 0 && <p>这里没有子目录。</p>}
        {listing?.truncated && <p>仅显示前 250 项，可手动填写其他目录。</p>}
        <div className="dialog-actions">
          {onManual && <button type="button" onClick={onManual}>手动填写</button>}
          <button type="button" onClick={() => dialog.current?.close()}>取消</button>
          <button className="folder-confirm" type="button" disabled={!listing?.current} onClick={() => listing?.current && onSelect(listing.current)}>选择当前目录</button>
        </div>
      </div>
    </dialog>
  )
}
