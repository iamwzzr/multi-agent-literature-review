// Print an ordinary document, outside the modal dialog's clipped top layer.
export async function printReport(report: Element, title: string) {
  const frame = document.createElement('iframe')
  frame.title = '打印综述'
  frame.setAttribute('aria-hidden', 'true')
  frame.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;border:0;opacity:0;pointer-events:none'
  document.body.append(frame)
  const target = frame.contentDocument
  const view = frame.contentWindow
  if (!target || !view) { frame.remove(); return }
  target.title = title
  target.documentElement.lang = 'zh-CN'
  const base = target.createElement('base')
  base.href = document.baseURI
  target.head.append(base)
  const loading: Promise<void>[] = []
  for (const source of document.querySelectorAll('style, link[rel="stylesheet"]')) {
    const clone = source.cloneNode(true) as HTMLElement
    if (clone instanceof HTMLLinkElement) loading.push(new Promise(resolve => {
      clone.onload = () => resolve(); clone.onerror = () => resolve()
    }))
    target.head.append(clone)
  }
  target.body.append(target.importNode(report, true))
  const reset = target.createElement('style')
  reset.textContent = `html,body{display:block!important;width:auto!important;min-width:0!important;height:auto!important;max-height:none!important;overflow:visible!important;margin:0!important;background:white!important}
    .report-document{box-sizing:border-box;width:100%!important;max-width:100%!important;min-width:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;box-shadow:none!important;overflow:visible!important}
    .comparison-table-scroll{overflow:visible!important;width:100%!important}
    table{width:100%!important;table-layout:fixed!important;border-collapse:collapse}
    th,td{min-width:0!important;max-width:none!important;white-space:normal!important;overflow-wrap:anywhere!important;word-break:normal}
    thead{display:table-header-group}tr{break-inside:avoid}h1,h2,h3{break-after:avoid}.report-warning{break-inside:avoid;white-space:normal;overflow-wrap:anywhere}`
  target.head.append(reset)
  await Promise.all(loading)
  await target.fonts.ready
  view.addEventListener('afterprint', () => window.setTimeout(() => frame.remove(), 0), {once:true})
  view.focus()
  view.print()
}
