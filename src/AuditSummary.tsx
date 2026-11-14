import type { ReviewTurn } from './demo'
import { reportWarning } from './ReportPreview'
function record(value:unknown): Record<string,unknown> {return value && typeof value==='object' && !Array.isArray(value) ? value as Record<string,unknown> : {}}
export function AuditSummary({turn}:{turn:ReviewTurn}) {
 const audit=turn.audit
 if (!audit) return null
 const review=record(audit.review)
 const issues=Array.isArray(review.issues)?review.issues:[]
 const unresolved=Array.isArray(audit.unresolved)?audit.unresolved:[]
 const usage=record(audit.usage)
 return <section className="audit-summary" aria-label="审核与未解决问题">
 <h2>审核结果</h2><p>{reportWarning(turn)}</p>
 <dl><dt>审核结论</dt><dd>{({pass:'通过',revise:'需要修订',undetermined:'尚无法判断'} as Record<string,string>)[String(review.verdict)] ?? '尚未审核'}</dd><dt>报告版本</dt><dd>{String(audit.report_version ?? '未知')}</dd><dt>证据版本</dt><dd>{String(audit.evidence_snapshot_id ?? '未知')}</dd></dl>
 <h3>未解决问题</h3>{unresolved.length ? <ul>{unresolved.map((item,i)=><li key={i}>{String(item)}</li>)}</ul> : <p>后端未报告未解决问题。</p>}
 {issues.length>0 && <details><summary>审核意见 · {issues.length} 条</summary><ul>{issues.map((item,i)=>{const issue=record(item);return <li key={i}><strong>{issue.severity==='blocking'?'阻断问题':'提示'} · {issue.owner==='researcher'?'Researcher':'Reporter'}</strong><p>{String(issue.problem ?? '')}</p><p>建议处理：{String(issue.required_fix ?? '未提供')}</p><span>{issue.status==='resolved'?'已解决':'待处理'}</span></li>})}</ul></details>}
 {Object.keys(usage).length>0 && <p>模型调用 {String(usage.model_calls ?? '未知')} 次 · 工具调用 {String(usage.tool_calls ?? '未知')} 次 · Token {String(usage.tokens ?? '未知')}</p>}
 </section>
}
