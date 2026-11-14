import { useEffect, useState } from 'react'
import { readSources, saveSources, uploadPdf } from './backend'
import type { BackendSettings, Sources as SourceSettings } from './backend'

export function Sources({projectId, backend, busy, onUploadBusy}: {
  projectId: string; backend: BackendSettings; busy: boolean; onUploadBusy: (busy:boolean)=>void
}) {
  const [value,setValue] = useState(() => readSources(projectId,backend.url))
  const [status,setStatus] = useState('')
  const [uploading,setUploading] = useState(false)
  useEffect(() => () => onUploadBusy(false), [onUploadBusy])
  function update(next: SourceSettings) {
    setValue(next)
    try {saveSources(projectId,next,backend.url)} catch {setStatus('浏览器无法保存资料设置，请检查存储空间后重试。')}
  }
  async function upload(file: File) {
    if (busy || uploading || backend.useDemo) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {setStatus('请选择 PDF 文件');return}
    if (file.size > 30_000_000) {setStatus('PDF 不能超过 30 MB');return}
    if (value.files.length >= 20) {setStatus('每个项目最多上传 20 个 PDF');return}
    setUploading(true);onUploadBusy(true);setStatus(file.name+'：上传中')
    try {
      const id = await uploadPdf(backend,projectId,file)
      update({...value,files:[...value.files.filter(f=>f.id!==id),{id,name:file.name}]})
      setStatus(file.name+'：上传成功')
    } catch(error) {setStatus(file.name+'：上传失败，'+(error instanceof Error ? error.message : String(error)))}
    finally {setUploading(false);onUploadBusy(false)}
  }
  return <section className="source-controls" aria-label="本轮资料来源">
    <fieldset disabled={busy || uploading}><legend>资料来源</legend>
      {(['local','online','hybrid'] as const).map((mode,i)=><label key={mode}><input type="radio" name={'source-'+projectId} checked={value.mode===mode} onChange={()=>update({...value,mode})}/>{['本地','联网 · arXiv','混合'][i]}</label>)}
    </fieldset>
    <p>{value.mode==='online'?'仅检索 arXiv，本轮不使用本地目录和上传资料。':value.mode==='hybrid'?'使用本地资料，必要时补充在线论文。':'使用配置目录与上传的 PDF。'} 论文片段可能发送给云模型。</p>
    {value.mode!=='local' && <label className="source-query">英文关键词 / arXiv 检索式<input maxLength={1000} value={value.query} disabled={busy||uploading} onChange={e=>update({...value,query:e.target.value})}/></label>}
    {value.mode!=='online' && <label className="source-upload" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const file=e.dataTransfer.files[0];if(file)void upload(file)}}>
      选择或拖放 PDF · 最多 30 MB
      <input type="file" accept="application/pdf,.pdf" disabled={busy||uploading||backend.useDemo} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);e.target.value=''}}/>
    </label>}
    {backend.useDemo && <p>演示模式不上传文件，请在后端设置中关闭演示模式。</p>}
    {status && <p role="status">{status}</p>}
    {value.files.length>0 && <details><summary>已上传 PDF · {value.files.length} 个{value.mode==='online'?'（本轮不使用）':''}</summary><ul>{value.files.map(f=><li key={f.id}>{f.name} · 已上传</li>)}</ul></details>}
  </section>
}
