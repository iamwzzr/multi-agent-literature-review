import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import { Folder, Monitor, Moon, Settings, Sun, X } from 'lucide-react'
import type { Project, ProjectConfig } from './projects'
import { useMediaQuery } from './useMediaQuery'

const themes = {
  light: { label: '浅色', icon: Sun },
  dark: { label: '深色', icon: Moon },
  system: { label: '跟随系统', icon: Monitor },
}
type Theme = keyof typeof themes

export function AppearanceSettings({ dialog }: { dialog: RefObject<HTMLDialogElement | null> }) {
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

  return (
    <dialog
      ref={dialog}
      id="workspace-settings"
      className="page-dialog settings-dialog"
      aria-labelledby="settings-title"
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
  const [error, setError] = useState('')

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
  }, [])

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name')).trim()
    const folder = String(data.get('folder')).trim()
    if (!name || !folder) {
      setError('请输入项目名称和工作目录。')
      return
    }
    if (otherFolders.includes(folder)) {
      setError('这个工作目录已用于另一个项目。')
      return
    }
    const knowledgePaths = [...new Set(String(data.get('knowledgePaths')).split(/\r?\n/).map((path) => path.trim()).filter(Boolean))]
    dialog.current?.close()
    onSave({ name, folder, knowledgePaths })
  }

  return (
    <dialog className="page-dialog project-dialog" ref={dialog} onClose={onClose} aria-labelledby="project-dialog-title">
      <div className="dialog-toolbar">
        <span id="project-dialog-title"><Folder size={16} /> {project ? '配置项目' : '新建项目'}</span>
        <button className="icon-button" type="button" aria-label="关闭项目设置" onClick={() => dialog.current?.close()}>
          <X size={17} />
        </button>
      </div>
      <form className="project-form" onSubmit={save} onInput={() => setError('')}>
        <label>项目名称<input name="name" defaultValue={project?.name} placeholder="例如，学术综述" maxLength={80} required /></label>
        <label>工作目录<input name="folder" defaultValue={project?.folder} placeholder="~/Research/my-project" maxLength={500} required /></label>
        <label>
          知识库路径
          <textarea name="knowledgePaths" rows={3} defaultValue={project?.knowledgePaths.join('\n')} placeholder="每行一个路径" maxLength={4000} />
        </label>
        <p>路径配置保存在当前标签页，供原型演示。</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="project-form-actions">
          <button type="button" onClick={() => dialog.current?.close()}>取消</button>
          <button type="submit">{project ? '保存配置' : '创建项目'}</button>
        </div>
      </form>
    </dialog>
  )
}
