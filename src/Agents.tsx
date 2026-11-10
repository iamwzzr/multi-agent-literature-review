import { FilePenLine, FlaskConical, ListTree, Search, ShieldCheck } from 'lucide-react'

export const agents = [
  { id: 'coordinator', name: '协调员', task: '拆解研究问题', activity: '正在整理研究问题，分配待办任务。', icon: ListTree },
  { id: 'researcher', name: '研究员', task: '检索文献证据', activity: '正在浏览示例论文，记录证据与页码。', icon: Search },
  { id: 'synthesizer', name: '撰写员', task: '综合研究发现', activity: '正在对照研究笔记，撰写综述。', icon: FilePenLine },
  { id: 'reviewer', name: '审阅员', task: '核对主张与引用', activity: '正在逐条比对综述和来源段落。', icon: ShieldCheck },
]

const labArt = `${import.meta.env.BASE_URL}agent-lab.webp`

export function AgentActivity({ step }: { step: number }) {
  const agent = agents[step]
  const sprite = {
    backgroundImage: `url(${labArt})`,
    backgroundPosition: `${(step % 2) * 100}% ${Math.floor(step / 2) * 100}%`,
  }

  return (
    <aside className="agent-activity" aria-labelledby="lab-title">
      <div className="lab-heading"><FlaskConical size={15} /> <h2 id="lab-title">研究实验室</h2><span>模拟运行</span></div>
      <div className="agent-scene" data-agent={agent.id} aria-hidden="true">
        <div className="agent-sprite" style={sprite} />
        <div className="agent-sprite agent-hand agent-hand-near" style={sprite} />
        <div className="agent-sprite agent-hand agent-hand-far" style={sprite} />
        <div className="agent-keystrokes"><i /><i /><i /></div>
      </div>
      <div className="agent-summary" role="status">
        <span className="activity-label">正在工作 · {step + 1}/{agents.length}</span>
        <strong>{agent.name}</strong>
        <p>{agent.activity}</p>
      </div>
      <ol className="lab-roster" aria-label="Agent 工作状态">
        {agents.map(({ id, name, icon: Icon }, index) => (
          <li key={id} aria-current={index === step ? 'step' : undefined}>
            <Icon size={15} /> <span>{name}</span>
            <small>{index < step ? '已完成' : index === step ? '进行中' : '等待中'}</small>
          </li>
        ))}
      </ol>
    </aside>
  )
}
