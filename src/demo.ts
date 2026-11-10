export type Paper = {
  id: string
  title: string
  author: string
  year: number
  pages: number
  summary: string
}

export type Evidence = {
  paper: Paper
  page: number
  excerpt: string
  context: string
}

export type ReviewSection = {
  id: string
  heading: string
  paragraphs: string[]
}

export type ReviewRun = {
  id: string
  title: string
  question: string
  evidence: Evidence[]
  sections: ReviewSection[]
}

const tracing: Paper = {
  id: 'evidence-tracing',
  title: 'Evidence Tracing in Collaborative Review',
  author: 'Lin 等',
  year: 2025,
  pages: 12,
  summary: '演示怎样把综述中的主张连接到来源页码和对应段落。',
}

const retrieval: Paper = {
  id: 'local-retrieval',
  title: 'Local Retrieval for Literature Synthesis',
  author: 'Wang 等',
  year: 2024,
  pages: 10,
  summary: '演示以子问题为单位检索文献，并比较检索覆盖率。',
}

const verification: Paper = {
  id: 'claim-verification',
  title: 'Claim-Level Verification in AI Writing',
  author: 'Chen 等',
  year: 2025,
  pages: 15,
  summary: '演示按主张核查引用、标记推断并请求补充证据的工作流。',
}

const coordination: Paper = {
  id: 'agent-coordination',
  title: 'Coordinating Research Agents',
  author: 'Zhou 等',
  year: 2025,
  pages: 9,
  summary: '演示研究任务分配，以及由证据缺口触发的定向补查。',
}

export const demoEvidence: Evidence[] = [
  {
    paper: tracing,
    page: 4,
    excerpt: '为每项主张保留来源段落与页码，使审阅员能够从综述直接回到证据。',
    context: '示例工作流为每条主张记录论文标识、页码和原文片段。审阅员沿引用链返回来源，核对综述是否保留了原文中的限定条件。',
  },
  {
    paper: retrieval,
    page: 6,
    excerpt: '以子问题为单位检索，可以把未覆盖的主题暴露在综合撰写之前。',
    context: '示例把研究问题拆成多个检索任务，并为每项任务单独统计候选段落。长文档中的方法和结果部分会被分别保留。',
  },
  {
    paper: verification,
    page: 8,
    excerpt: '核查时应区分原文直接支持的陈述、综合推断，以及仍缺少依据的结论。',
    context: '示例审阅表逐条记录主张、证据与核查结果。出现冲突或无法定位的引文时，审阅员向研究员提出具体的补证请求。',
  },
  {
    paper: coordination,
    page: 5,
    excerpt: '当审阅发现证据缺口时，可以只重新分派相关子任务，再修订受影响的段落。',
    context: '示例协调员保留任务之间的依赖关系。只更新受到新证据影响的部分，可以让前后版本的修改更容易追溯。',
  },
]

export const demoReviews: ReviewRun[] = [
  {
    id: 'collaboration',
    title: '多智能体协作与证据核查',
    question: '多智能体分工如何改善文献综述的证据覆盖和引用核查？',
    evidence: demoEvidence,
    sections: [
      {
        id: 'summary',
        heading: '综述摘要',
        paragraphs: [
          '在这个示例流程中，协调员先把研究问题拆成若干子问题，由研究员并行查阅论文。撰写员汇总发现时保留来源页码，使审阅员可以从综述中的主张直接回到原文。[[1]][[2]]',
          '审阅环节逐条区分直接证据、综合推断与未解决的缺口。发现依据不足时，协调员可以把补查交回对应的研究员，再修订受影响的段落。[[3]][[4]]',
        ],
      },
      {
        id: 'findings',
        heading: '主要发现',
        paragraphs: [
          '按子问题整理检索结果，有助于看清哪些主题已有证据、哪些仍需补充。保留原文段落与页码后，同一条证据可以在撰写和核查时复用。[[2]][[1]]',
          '独立审阅使意见可以落到具体主张。团队能够保留已经核对的段落，并集中修订存在争议的部分。[[3]][[4]]',
        ],
      },
      {
        id: 'gaps',
        heading: '待核查的问题',
        paragraphs: ['在正式评估中，还需要比较不同论文集合上的证据覆盖率、引用正确率，以及多轮协作的时间成本。'],
      },
    ],
  },
  {
    id: 'retrieval',
    title: '长文档检索与证据定位',
    question: '从一组本地论文中检索时，怎样让找到的证据能准确回到原文？',
    evidence: [demoEvidence[1], demoEvidence[0]],
    sections: [
      {
        id: 'summary',
        heading: '综述摘要',
        paragraphs: ['示例检索流程为每个子问题保留候选论文和段落，将分段内容与原论文的页码关联。综合阶段可以按需打开上下文并检查抽取结果。[[1]][[2]]'],
      },
      {
        id: 'gaps',
        heading: '待核查的问题',
        paragraphs: ['后续评估需要覆盖双栏论文、跨页段落和扫描版文档，观察页码与正文的映射是否稳定。'],
      },
    ],
  },
  {
    id: 'verification',
    title: '学术写作中的引用可靠性',
    question: '如何判断一条引用能否支持综述中的主张？',
    evidence: [demoEvidence[2], demoEvidence[0]],
    sections: [
      {
        id: 'summary',
        heading: '综述摘要',
        paragraphs: ['示例审阅流程将综述拆成可单独检查的主张，并比对来源段落。范围不匹配或缺少限定条件时，审阅员记录原因并请求修订。[[1]][[2]]'],
      },
      {
        id: 'gaps',
        heading: '待核查的问题',
        paragraphs: ['正式评估需要考虑引用多篇论文才能支持的主张，以及不同研究对同一问题给出相反结果的情况。'],
      },
    ],
  },
]

export function createDemoReview(question: string): ReviewRun {
  return {
    id: crypto.randomUUID(),
    title: question,
    question,
    evidence: demoEvidence,
    sections: [
      {
        id: 'summary',
        heading: '综述预览',
        paragraphs: ['已接收研究问题。这里展示固定的示例内容，方便预览任务记录与引用检查。点击引用编号可查看对应的示例摘录。[[1]][[2]]'],
      },
      {
        id: 'findings',
        heading: '核查预览',
        paragraphs: ['在接入研究流程后，这里将展示证据支持的发现和审阅员标记的缺口。以下编号演示怎样返回文献中的相关页面。[[3]][[4]]'],
      },
    ],
  }
}
