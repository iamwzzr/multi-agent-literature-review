import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import { Folder, FolderOpen, FolderPlus, LibraryBig, Monitor, Moon, Plus, Server, Settings, Sun, X } from 'lucide-react'
import { checkBackend, defaultBackendUrl, normalizeBackendUrl } from './backend'
import type { BackendSettings } from './backend'
import { pickFolder } from './folderPicker'
import type { Project, ProjectConfig } from './projects'
import { useMediaQuery } from './useMediaQuery'

const themes = {
  light: { label: '浅色', icon: Sun },
  dark: { label: '深色', icon: Moon },
  system: { label: '跟随系统', icon: Monitor },
}
type Theme = keyof typeof themes
type FolderTarget = 'work' | 'knowledge'

export function WorkspaceSettings({ dialog, backend, onBackendSave }: {
  dialog: RefObject<HTMLDialogElement | null>
  backend: BackendSettings
  onBackendSave: (settings: BackendSettings) => void
}) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const savedTheme = localStorage.getItem('folio.theme')
      if (savedTheme === 'dark' || savedTheme === 'system') return savedTheme
    } catch {
      // Restricted browser contexts use the default appearance.
    }
    return 'light'
  })
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)')
  const dark = theme === 'dark' || (theme === 'system' && systemDark)
  const [url, setUrl] = useState(backend.url)
  const [useDemo, setUseDemo] = useState(backend.useDemo)
  const [status, setStatus] = useState<{ kind: 'checking' | 'success' | 'error'; text: string } | null>(null)
  const connectionTest = useRef<AbortController | null>(null)

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#1d1d1d' : '#ffffff')
  }, [dark])

  function chooseTheme(next: Theme) {
    setTheme(next)
    try {
      localStorage.setItem('folio.theme', next)
    } catch {
      // The choice still applies to the current page.
    }
  }

  function resetStatus() {
    connectionTest.current?.abort()
    connectionTest.current = null
    setStatus(null)
  }

  function address() {
    try {
      return normalizeBackendUrl(url)
    } catch (failure) {
      setStatus({ kind: 'error', text: failure instanceof Error ? failure.message : '后端地址无效。' })
    }
  }

  async function testConnection() {
    resetStatus()
    const normalized = address()
    if (!normalized) return
    const controller = new AbortController()
    connectionTest.current = controller
    setStatus({ kind: 'checking', text: '正在测试连接…' })
    try {
      await checkBackend(normalized, controller.signal)
      if (!controller.signal.aborted) setStatus({ kind: 'success', text: '连接成功，后端支持 Folio v1。' })
    } catch (failure) {
      if (!controller.signal.aborted) {
        setStatus({ kind: 'error', text: failure instanceof Error ? failure.message : '连接失败。' })
      }
    } finally {
      if (connectionTest.current === controller) connectionTest.current = null
    }
  }

  function saveBackend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    resetStatus()
    const normalized = address()
    if (!normalized) return
    onBackendSave({ url: normalized, useDemo })
    setUrl(normalized)
    setStatus({ kind: 'success', text: '已保存后端设置。' })
  }

  return (
    <dialog
      ref={dialog}
      id="workspace-settings"
      className="page-dialog settings-dialog"
      aria-labelledby="settings-title"
      onClose={() => {
        resetStatus()
        setUrl(backend.url)
        setUseDemo(backend.useDemo)
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close()
      }}
    >
      <div className="dialog-toolbar">
        <span id="settings-title"><Settings size={16} /> 设置</span>
        <button className="icon-button" type="button" aria-label="关闭设置" onClick={() => dialog.current?.close()}>
          <X size={17} />
        </button>
      </div>
      <fieldset className="appearance-field">
        <legend>外观主题</legend>
        <div className="appearance-options">
          {Object.entries(themes).map(([value, { label, icon: Icon }]) => (
            <label key={value}>
              <input className="sr-only" type="radio" name="appearance" value={value} checked={theme === value} onChange={() => chooseTheme(value as Theme)} />
              <span className="appearance-option"><Icon size={16} /> {label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <form className="backend-settings" onSubmit={saveBackend}>
        <h2><Server size={15} /> 后端连接</h2>
        <label htmlFor="backend-url">后端地址</label>
        <input
          id="backend-url"
          value={url}
          placeholder={defaultBackendUrl}
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => {
            resetStatus()
            setUrl(event.target.value)
          }}
        />
        <label className="demo-mode-option">
          <input type="checkbox" checked={useDemo} onChange={(event) => setUseDemo(event.target.checked)} />
          新建综述使用模拟数据
        </label>
        {status && <p className="backend-status" data-error={status.kind === 'error'} role={status.kind === 'error' ? 'alert' : 'status'}>{status.text}</p>}
        <div className="dialog-actions backend-actions">
          <button type="button" onClick={() => { resetStatus(); setUrl(defaultBackendUrl) }}>恢复默认地址</button>
          <button type="button" disabled={status?.kind === 'checking'} onClick={() => void testConnection()}>测试连接</button>
          <button type="submit">保存设置</button>
        </div>
      </form>
    </dialog>
  )
}

export function ProjectSettings({ project, otherFolders, onSave, onClose }: {
  project?: Project
  otherFolders: string[]
  onSave: (config: ProjectConfig) => void
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const nameInput = useRef<HTMLInputElement>(null)
  const nextPathId = useRef(project?.knowledgePaths.length ?? 0)
  const [name, setName] = useState(project?.name ?? '')
  const [folder, setFolder] = useState(project?.folder ?? '')
  const [knowledge, setKnowledge] = useState(() => (project?.knowledgePaths ?? []).map((value, id) => ({ id, value })))
  const [picking, setPicking] = useState(false)
  const [pathNotice, setPathNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
    nameInput.current?.focus()
  }, [])

  function addPath(value = '') {
    const id = nextPathId.current++
    setKnowledge((paths) => [...paths, { id, value }])
    if (!value) requestAnimationFrame(() => document.getElementById('knowledge-path-' + id)?.focus())
  }

  function acceptFolder(target: FolderTarget, folderName: string) {
    setError('')
    if (target === 'work') {
      setFolder(folderName)
      setName((current) => current.trim() ? current : folderName.slice(0, 80))
    } else if (knowledge.some(({ value }) => value.trim() === folderName)) {
      setPathNotice('已添加这个目录名。同名文件夹可以手动填写完整路径。')
    } else {
      addPath(folderName)
    }
  }

  async function browse(target: FolderTarget) {
    setPathNotice('')
    setPicking(true)
    try {
      const name = await pickFolder('folio-' + target, dialog.current ?? undefined)
      if (name && dialog.current?.open) acceptFolder(target, name)
    } catch (failure) {
      setPathNotice(failure instanceof Error ? failure.message : '无法选择文件夹。')
    } finally {
      setPicking(false)
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const projectName = name.trim()
    const workFolder = folder.trim()
    if (!projectName || !workFolder) {
      setError('请输入项目名称和工作目录。')
      return
    }
    if (otherFolders.includes(workFolder)) {
      setError('这个工作目录已用于另一个项目。同名文件夹可以填写完整路径。')
      return
    }
    const knowledgePaths = [...new Set(knowledge.map(({ value }) => value.trim()).filter(Boolean))]
    dialog.current?.close()
    onSave({ name: projectName, folder: workFolder, knowledgePaths })
  }

  return (
    <dialog className="page-dialog project-dialog" ref={dialog} onClose={onClose} aria-labelledby="project-dialog-title">
      <div className="dialog-toolbar">
        <span id="project-dialog-title"><Folder size={16} /> {project ? '配置项目' : '新建项目'}</span>
        <button className="icon-button" type="button" aria-label="关闭项目设置" onClick={() => dialog.current?.close()}>
          <X size={17} />
        </button>
      </div>
      <form className="project-form" onSubmit={save} onInput={() => { setError(''); setPathNotice('') }}>
        <label>项目名称<input ref={nameInput} name="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如，学术综述" maxLength={80} required /></label>
        <div className="project-field">
          <label htmlFor="project-folder"><span className="project-field-label"><Folder size={14} /> 工作目录</span></label>
          <div className="project-path-row">
            <input id="project-folder" name="folder" value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="~/Research/my-project" autoComplete="off" spellCheck={false} maxLength={500} required />
            <button className="context-button" type="button" aria-label="选择工作目录" disabled={picking} onClick={() => void browse('work')}><FolderOpen size={15} /> 浏览…</button>
          </div>
        </div>
        <section className="project-field" aria-labelledby="knowledge-paths-title">
          <h2 id="knowledge-paths-title" className="project-field-label"><LibraryBig size={14} /> 知识库路径</h2>
          {knowledge.map(({ id, value }, index) => (
            <div className="project-path-row" key={id}>
              <input
                id={'knowledge-path-' + id}
                aria-label={'知识库路径 ' + (index + 1)}
                value={value}
                placeholder="例如，~/Research/papers"
                autoComplete="off"
                spellCheck={false}
                maxLength={500}
                onChange={(event) => {
                  const updated = event.target.value
                  setKnowledge((paths) => paths.map((entry) => entry.id === id ? { id, value: updated } : entry))
                }}
              />
              <button className="icon-button" type="button" aria-label={'移除知识库路径 ' + (index + 1)} title="移除此路径" onClick={() => {
                setKnowledge((paths) => paths.filter((entry) => entry.id !== id))
                requestAnimationFrame(() => document.getElementById('add-manual-path')?.focus())
              }}><X size={15} /></button>
            </div>
          ))}
          <div className="project-path-actions">
            <button className="context-button" type="button" disabled={picking} onClick={() => void browse('knowledge')}><FolderPlus size={15} /> 添加文件夹</button>
            <button className="context-button" id="add-manual-path" type="button" onClick={() => addPath()}><Plus size={15} /> 手动填写</button>
          </div>
        </section>
        <p>浏览器只会填入目录名。需要完整路径时，可以直接编辑。</p>
        {pathNotice && <p className="form-error" role="status">{pathNotice}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={() => dialog.current?.close()}>取消</button>
          <button type="submit" disabled={picking}>{project ? '保存配置' : '创建项目'}</button>
        </div>
      </form>
    </dialog>
  )
}
