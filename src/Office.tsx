import { useId, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowUpRight, CornerUpLeft, X } from 'lucide-react'
import { displayAgents, displayAgentStatus } from './workflow'
import type { AgentActivity, AgentId } from './workflow'

const roomArt = `${import.meta.env.BASE_URL}office-room.webp`
const fishArt = new URL(`${import.meta.env.BASE_URL}office-fish.webp`, document.baseURI).href
const stationPositions: Record<AgentId, [number, number]> = {
  planner: [32, 55],
  verification: [83, 94],
  search: [17, 94],
  analysis: [50, 94],
  writing: [50, 94],
}
const statusLabels = { waiting: '待命', working: '工作中', done: '已完成', feedback: '待补查' }

export function ResearchOffice({ phase, onOpenRun, onClose }: { phase?: AgentActivity; onOpenRun?: () => void; onClose: () => void }) {
  const titleId = useId()
  const detailId = useId()
  const [selected, setSelected] = useState<AgentId | null>(null)
  const focused = selected ?? displayAgents.find(a => displayAgentStatus(a, phase) === 'working')?.id ?? 'search'
  const agent = displayAgents.find(({ id }) => id === focused) ?? displayAgents[0]
  const focusedStatus = displayAgentStatus(agent, phase)
  const workingCount = displayAgents.filter(a => displayAgentStatus(a, phase) === 'working').length
  const focusedDetail = agent.members.map(id => phase?.taskDetails?.[id]).filter(Boolean).join('；') || (focusedStatus === 'working' ? agent.activity : agent.task)
  const Icon = agent.icon

  return (
    <aside className="office-panel" id="office-panel" aria-labelledby={titleId} onKeyDown={(event) => {
      if (event.key === 'Escape') onClose()
    }}>
      <header className="inspector-header">
        <h2 id={titleId}>大肥鱼研究办公室</h2>
        <button className="icon-button inspector-close" type="button" aria-label="收起办公室" onClick={onClose}><X size={15} /></button>
      </header>
      <div className="office-actions">
        <span className="office-count" data-busy={workingCount > 0}><span />{workingCount > 0 ? `${workingCount} 个工位工作中` : phase?.working.includes('planner') ? '程序协调中' : '全员待命'}</span>
        {onOpenRun && <button type="button" className="context-button" onClick={onOpenRun}>查看会话 <ArrowUpRight size={13} /></button>}
      </div>

      <div className="office-scene" style={{ '--fish-sprite': `url(${fishArt})` } as CSSProperties}>
        <img className="office-room" src={roomArt} alt="" draggable={false} />
        {phase?.feedback && (
          <span className="office-feedback" aria-hidden="true"><CornerUpLeft size={14} /> 程序协调返工</span>
        )}
        {displayAgents.map((item) => {
          const { id, name } = item
          const status = displayAgentStatus(item, phase)
          const [x, y] = stationPositions[id]
          return (
            <button
              type="button"
              key={id}
              className="office-desk"
              data-agent={id}
              data-status={status}
              style={{ left: `${x}%`, top: `${y}%` }}
              aria-label={`${name}，${statusLabels[status]}`}
              aria-controls={detailId}
              aria-pressed={focused === id}
              onClick={() => setSelected(id)}
            >
              <span className="fish-art" aria-hidden="true">
                <span className="fish-pose" />
                {status === 'working' && (
                  <>
                    <span className="fish-pose fish-hand fish-hand-near" />
                    <span className="fish-pose fish-hand fish-hand-far" />
                    <span className="fish-keybeats"><i /><i /><i /></span>
                  </>
                )}
              </span>
              <span className="desk-plaque"><strong>{name}</strong><small>{statusLabels[status]}</small></span>
            </button>
          )
        })}
      </div>

      <div className="office-caption">
        {phase && (
          <div className="office-phase" role="status">
            <span>当前阶段</span>
            <strong>{phase.title}</strong>
            <p>{phase.summary}</p>
          </div>
        )}
        <div className="office-desk-detail" id={detailId}>
          <strong><Icon size={15} /> {agent.name}</strong>
          <small>{agent.role} · {statusLabels[focusedStatus]}</small>
          <p>{focusedDetail}</p>
        </div>
      </div>
    </aside>
  )
}
