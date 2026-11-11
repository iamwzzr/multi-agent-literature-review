import { BadgeCheck, FilePenLine, ListTree, Search, TextSearch } from 'lucide-react'

export const agents = [
  { id: 'planner', name: '统筹规划', role: 'Supervisor / Planner', task: '任务规划与协调', activity: '在白板上拆解研究问题，分派检索、分析与撰写任务。', icon: ListTree },
  { id: 'search', name: '文献检索', role: 'Search Agent', task: '查找候选文献', activity: '在知识库中寻找相关论文，记录候选段落和页码。', icon: Search },
  { id: 'analysis', name: '论文分析', role: 'Analysis Agent', task: '整理研究证据', activity: '对照论文的方法、发现与限制，整理可比较的证据。', icon: TextSearch },
  { id: 'writing', name: '综述撰写', role: 'Writing Agent', task: '生成结构化综述', activity: '先搭建综述提纲，再把研究发现写进相应章节。', icon: FilePenLine },
  { id: 'verification', name: '事实核查', role: 'Verification Agent', task: '核对事实与引用', activity: '逐条比对综述主张、文献摘录和引用页码。', icon: BadgeCheck },
] as const

export type AgentId = typeof agents[number]['id']

export type RunPhase = {
  title: string
  summary: string
  duration: number
  working: AgentId[]
  done: AgentId[]
  feedback?: true
  taskDetails?: Partial<Record<AgentId, string>>
}

const reviewPhases: RunPhase[] = [
  {
    title: '规划任务',
    summary: '统筹规划收到研究问题，正在安排三个研究工位。',
    duration: 2300,
    working: ['planner'],
    done: [],
  },
  {
    title: '并行研究',
    summary: '检索员查找论文，分析员整理已有证据，撰写员同步搭建提纲。',
    duration: 4000,
    working: ['search', 'analysis', 'writing'],
    done: ['planner'],
  },
  {
    title: '事实与引用核查',
    summary: '三个工位汇交材料，核查员开始逐条核对事实和页码。',
    duration: 2300,
    working: ['verification'],
    done: ['planner', 'search', 'analysis', 'writing'],
  },
  {
    title: '反馈给规划',
    summary: '核查发现一处引用缺少原文页码，退回规划重新分派。',
    duration: 2900,
    working: ['planner'],
    done: ['search', 'analysis', 'writing'],
    feedback: true,
    taskDetails: {
      planner: '接收核查意见，安排检索员补原文页码、撰写员更新引用。',
      verification: '已标出缺少原文页码的引用，等待补查结果。',
    },
  },
  {
    title: '补查与修订',
    summary: '检索员补充页码，撰写员据此更新相关段落。',
    duration: 2900,
    working: ['search', 'writing'],
    done: ['planner', 'analysis'],
    taskDetails: {
      search: '回到示例论文，定位待核对引用的原文和具体页码。',
      writing: '按补充的来源更新相关段落和引用。',
    },
  },
  {
    title: '复核后交付',
    summary: '核查员重新检查修订处，确认后交付带引用的综述。',
    duration: 2200,
    working: ['verification'],
    done: ['planner', 'search', 'analysis', 'writing'],
    taskDetails: { verification: '核对补齐的页码和修订后的主张，准备交付。' },
  },
]

const followUpPhases: RunPhase[] = [
  {
    title: '规划修改',
    summary: '统筹规划正在整理这一轮的要求，找出需要调整的章节。',
    duration: 1200,
    working: ['planner'],
    done: [],
    taskDetails: { planner: '阅读你的追问，对照上一轮综述安排修改。' },
  },
  {
    title: '修订综述',
    summary: '论文分析整理相关证据，综述撰写按要求调整回复。',
    duration: 2300,
    working: ['analysis', 'writing'],
    done: ['planner'],
    taskDetails: { writing: '根据本轮要求，整理上一轮综述的内容。' },
  },
  {
    title: '复核本轮修改',
    summary: '事实核查对照示例文献，检查调整后的表述和引用。',
    duration: 1400,
    working: ['verification'],
    done: ['planner', 'analysis', 'writing'],
  },
]

export const reviewFlows = {
  direct: reviewPhases.slice(0, 3),
  revision: reviewPhases,
  followUp: followUpPhases,
}
