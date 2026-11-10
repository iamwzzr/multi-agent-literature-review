import { useId, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowUpRight, Building2, CornerUpLeft } from 'lucide-react'
import { agents } from './workflow'
import type { AgentId, RunPhase } from './workflow'

const roomArt = `${import.meta.env.BASE_URL}office-room.webp`
const fishArt = new URL(`${import.meta.env.BASE_URL}office-fish.webp`, document.baseURI).href
const stationPositions: Record<AgentId, [number, number]> = {
  planner: [32, 59],
  verification: [68, 59],
  search: [17, 94],
  analysis: [50, 94],
  writing: [83, 94],
}
const statusLabels = { waiting: '待命', working: '工作中', done: '已完成', feedback: '待补查' }

function deskStatus(id: AgentId, phase?: RunPhase) {
  if (phase?.working.includes(id)) return 'working'
  if (id === 'verification' && phase?.feedback) return 'feedback'
  if (phase?.done.includes(id)) return 'done'
  return 'waiting'
}

export function ResearchOffice({ phase, onOpenRun }: { phase?: RunPhase; onOpenRun?: () => void }) {
  const titleId = useId()
  const detailId = useId()
  const [selected, setSelected] = useState<AgentId | null>(null)
  const focused = selected ?? phase?.working[0] ?? 'planner'
  const agent = agents.find(({ id }) => id === focused) ?? agents[0]
  const focusedStatus = deskStatus(agent.id, phase)
  const workingCount = phase?.working.length ?? 0
  const focusedDetail = phase?.taskDetails?.[agent.id] ?? (focusedStatus === 'working' ? agent.activity : agent.task)
  const Icon = agent.icon

  return (
    <section className="research-office" aria-labelledby={titleId}>
      <header className="office-header">
        <div>
          <div className="eyebrow"><Building2 size={14} /> 研究工作区</div>
          <h2 id={titleId}>大肥鱼研究办公室</h2>
        </div>
        <div className="office-actions">
          {onOpenRun && <button type="button" className="context-button" onClick={onOpenRun}>查看会话 <ArrowUpRight size={13} /></button>}
          <span className="office-count" data-busy={workingCount > 0}><span />{workingCount > 0 ? `${workingCount} 个工位工作中` : '全员待命'}</span>
        </div>
      </header>

      <div className="office-layout">
        <div className="office-scene" style={{ '--fish-sprite': `url(${fishArt})` } as CSSProperties}>
          <img className="office-room" src={roomArt} alt="" draggable={false} />
          {phase?.feedback && (
            <span className="office-feedback" aria-hidden="true"><CornerUpLeft size={14} /> 反馈给规划</span>
          )}
          {agents.map(({ id, name }) => {
            const status = deskStatus(id, phase)
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
          <div className="office-phase" role="status">
            <span>当前阶段</span>
            <strong>{phase?.title ?? '办公室待命'}</strong>
            <p>{phase?.summary ?? '提交研究问题后，可以在这里查看每个工位的进度。'}</p>
          </div>
          <div className="office-desk-detail" id={detailId}>
            <span>选中工位</span>
            <strong><Icon size={15} /> {agent.name}</strong>
            <small>{agent.role} · {statusLabels[focusedStatus]}</small>
            <p>{focusedDetail}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
