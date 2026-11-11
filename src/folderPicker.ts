type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options: { id: string; mode: 'read' }) => Promise<FileSystemDirectoryHandle>
}

export async function pickFolder(id: string, container: HTMLElement = document.body): Promise<string | undefined> {
  const picker = window as DirectoryPickerWindow
  if (picker.showDirectoryPicker) {
    try {
      return (await picker.showDirectoryPicker({ id, mode: 'read' })).name
    } catch (failure) {
      if (failure instanceof DOMException && failure.name === 'AbortError') return
      throw new Error('无法打开文件夹选择器。你可以在项目配置里填写路径。')
    }
  }

  const input = document.createElement('input')
  if (!('webkitdirectory' in input)) throw new Error('此浏览器无法选择文件夹。请在项目配置里填写路径。')
  input.type = 'file'
  input.hidden = true
  input.multiple = true
  input.webkitdirectory = true
  container.append(input)

  return new Promise((resolve, reject) => {
    input.addEventListener('cancel', () => {
      input.remove()
      resolve(undefined)
    }, { once: true })
    input.addEventListener('change', () => {
      const name = input.files?.[0]?.webkitRelativePath.split('/')[0]
      input.remove()
      if (name) resolve(name)
      else reject(new Error('未取得目录名。空文件夹可以在项目配置里填写路径。'))
    }, { once: true })
    input.click()
  })
}
