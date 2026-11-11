export type Paper = {
  id: string
  title: string
  author: string
  year: number | null
  pages: number
  summary: string
}

export type Evidence = {
  paper: Paper
  page: number
  excerpt: string
  context: string
  source?: 'backend'
}

export type ReviewSection = {
  id: string
  heading: string
  paragraphs: string[]
}

export type ReviewTurn = {
  question: string
  referenceIds?: string[]
  evidence: Evidence[]
  sections: ReviewSection[]
}

export type ReviewRun = ReviewTurn & {
  id: string
  title: string
  history?: ReviewTurn[]
  source?: 'backend'
  mockVerified?: true
  mockFlow?: 'direct'
}

export function lastTurn({ question, referenceIds, evidence, sections }: ReviewRun): ReviewTurn {
  return { question, referenceIds, evidence, sections }
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

const demoEvidence: Evidence[] = [
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

const extendedEvidence: Evidence[] = [
  ...demoEvidence,
  {
    paper: { id: 'eligibility', title: 'Eligibility Decisions in a Small Research Corpus', author: 'Xu 等', year: 2024, pages: 18, summary: '示例包含去重、纳入标准和排除理由。' },
    page: 1,
    excerpt: '先记录论文的纳入标准与排除理由，再比较不同检索任务得到的结果。',
    context: '示例把时间范围、文献类型和主题相关性分成三项纳入标准。重复版本只保留一份，并记下合并依据。',
  },
  {
    paper: { id: 'cross-page', title: 'Preserving Context Across PDF Page Boundaries', author: 'Liu 等', year: 2025, pages: 31, summary: '演示跨页段落、双栏排版和原文定位。' },
    page: 27,
    excerpt: '跨页证据需要同时保留前一页的限定条件和后一页的结果描述。',
    context: '本例将跨页段落拆成相邻的两个引文，并保留论文内的章节名称。核查时可以分别打开这两页。',
  },
  {
    paper: { id: 'matrix', title: 'An Evidence Matrix for Comparing Research Methods', author: 'He 等', year: 2025, pages: 44, summary: '演示如何按方法、样本和限制横向比较研究。' },
    page: 14,
    excerpt: '证据矩阵应同时保存研究设计、样本规模、指标定义与结论适用范围。',
    context: '示例矩阵以论文为行、观察项为列。发现度量口径不同时，先解释差异，再决定能否归纳到同一结论。',
  },
  {
    paper: { id: 'disagreement', title: 'Reporting Conflicting Findings in Evidence Synthesis', author: 'Yao 等', year: 2025, pages: 61, summary: '演示怎样呈现相反发现和缺少证据的主题。' },
    page: 45,
    excerpt: '结果互相矛盾时，应先比较研究条件和指标，再说明证据在哪些场景仍不一致。',
    context: '示例两组研究在样本和评价口径上有差异。综述保留双方原结论，并给出可以逐项核对的比较维度。',
  },
  {
    paper: { id: 'revision-log', title: 'Tracking Claim-Level Revisions Across Multi-Agent Literature Review Pipelines with Incomplete Evidence', author: 'Guo 等', year: 2026, pages: 76, summary: '长标题样例，包含修改记录和多位数页码。' },
    page: 62,
    excerpt: '保留修订前后的主张以及新增的引用，便于复核员比较调整依据。',
    context: '示例修订记录使用主张编号串联旧版本、核查意见和新版本。每项变更都对应一处来源或一条范围限制。',
  },
  {
    paper: { id: 'evaluation', title: 'A Reproducibility Checklist for Assisted Literature Reviews', author: 'Tang 等', year: 2026, pages: 128, summary: '综合评估样例，包含三位数页码和可复现检查清单。' },
    page: 120,
    excerpt: '交付前逐项检查检索范围、引用定位和复核记录，保证读者能复现关键判断。',
    context: '示例附录列出最小复核清单，包括检索词、排除规则、来源页码和未解决问题。清单中的每条记录都能独立回到原文。',
  },
]

const longReview: ReviewRun = {
  id: 'extended-review',
  title: '多智能体学术综述的证据覆盖、可复核性与引用核查方法',
  question: '如何评估多智能体文献综述从检索覆盖到引用复核的完整流程？',
  referenceIds: ['collaboration', 'retrieval'],
  mockFlow: 'direct',
  evidence: extendedEvidence,
  sections: [
    {
      id: 'summary', heading: '综述摘要',
      paragraphs: [
        '这篇长报告使用模拟材料，演示一份可追溯的文献综述如何组织检索、分析、撰写和核查。研究问题拆解后，每一项结论都沿着证据记录回到原文页码。[[1]][[10]]',
        '示例采用两层核查。先检查引用能否定位，再比较来源是否支持主张的范围和强度。核查记录随报告一起保存，便于从提纲或引用索引返回需要复核的段落。[[3]][[9]]',
      ],
    },
    {
      id: 'scope', heading: '研究范围与纳入标准',
      paragraphs: [
        '示例把研究范围分成检索覆盖、证据组织和引用准确性三个部分。每个子问题使用一致的时间范围和文献类型限制，并记录题目相近但主题不同的排除理由。[[5]]',
        '多份版本指向同一研究时，保留最完整的版本供核查。需要对照的段落仍记录原始文件标识和页码，以免引用在版本切换后失去定位。[[1]][[6]]',
      ],
    },
    {
      id: 'search', heading: '检索策略与候选文献',
      paragraphs: [
        '检索工位按子问题生成候选词，再用方法名称、任务目标和研究场景补充召回。命中较少的主题单独登记，后续可调整关键词或加入可比较的同义术语。[[2]]',
        '初筛时同时保留摘要和正文的位置。遇到跨页的证据段，示例记录相邻页并注明阅读顺序，以便复核员打开原文后看到完整上下文。[[6]]',
      ],
    },
    {
      id: 'analysis', heading: '证据矩阵与论文分析',
      paragraphs: [
        '分析工位把样本、研究设计、指标和结论限制放进证据矩阵。相同的结果名称有时对应不同的测量方式，示例要求在归类前先核对各论文对指标的定义。[[7]]',
        '比较条件不一致的研究时，先陈述可复核的观察，再说明综合推断。对于只有单篇论文支持的发现，综述保留该论文的适用边界。[[3]][[8]]',
      ],
    },
    {
      id: 'synthesis', heading: '综合发现与分歧',
      paragraphs: [
        '撰写工位按子问题整理共同发现，也保留证据分歧。示例把结论的差异与研究对象、评估口径和实验条件并列呈现，读者可以回到来源判断差异是否足以解释结果。[[7]][[8]]',
        '对覆盖不足的主题，报告列出缺少的资料类型和下一步检索方向。规划工位可以据此分派局部补查，其他已完成的章节仍可独立复核。[[4]]',
      ],
    },
    {
      id: 'citation-audit', heading: '引用核查与修订记录',
      paragraphs: [
        '核查工位逐项对照综述主张、引用编号和原文摘录，确认页码落在正确文件中。能定位的引用还要检查它支持的是整个主张，还是仅支持其中一个限定条件。[[1]][[3]]',
        '修改报告时，每一条修订保留旧主张、补入证据和新版本。示例附上修订页和复核清单，便于核对较长的英文论文标题和三位数页码。[[9]][[10]]',
      ],
    },
    {
      id: 'limitations', heading: '局限与后续验证',
      paragraphs: [
        '这份示例只覆盖小型论文集合。进一步验证时需要更换检索任务、论文版式和证据分歧程度，分别记录定位错误、范围不一致和无法找到原文的情况。[[6]][[8]]',
        '评价可以分别统计检索覆盖率和引用核查正确率。把两者分开记录，有助于判断问题来自找不到文献、读错上下文，还是最终表述超出了证据范围。[[2]][[10]]',
      ],
    },
    {
      id: 'checklist', heading: '交付前复核清单',
      paragraphs: [
        '逐项确认每个子问题都有明确的检索范围，主要结论都能打开来源页，跨页证据保留阅读顺序，修订记录可回溯。最后标记尚需补查的内容，方便后续会话继续复核。[[5]][[6]][[9]][[10]]',
      ],
    },
  ],
}

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
    mockFlow: 'direct',
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
  longReview,
  {
    id: 'evidence-gap',
    title: '证据不足时的待核查清单',
    question: '当资料缺少可定位的原文时，综述如何呈现证据缺口？',
    evidence: [],
    sections: [
      { id: 'summary', heading: '当前证据状态', paragraphs: ['这个样例模拟尚未找到可定位原文的报告。待验证项包括候选论文、需要查找的章节和可能缺失的原文页码。'] },
      { id: 'gaps', heading: '待补充资料', paragraphs: ['补查目标包括候选论文的全文版本、具体结果段和研究条件。新资料可作为后续会话的核查对象。'] },
    ],
  },
]

export const testPrompts = [
  { id: 'retrieval', label: '一次核查通过', detail: '并行研究后直接交付' },
  { id: 'collaboration', label: '退回补查', detail: '缺页码、修订与复核' },
  { id: 'extended-review', label: '长报告与引用', detail: `${longReview.sections.length} 节 · ${longReview.evidence.length} 条引用` },
].map((sample) => ({ ...sample, question: demoReviews.find(({ id }) => id === sample.id)!.question }))

export function createDemoReview(question: string, referenceIds: string[]): ReviewRun {
  const id = crypto.randomUUID()
  const example = demoReviews.find((review) => review.question === question)
  if (example) return { ...example, id, referenceIds }

  return {
    id,
    title: question,
    question,
    referenceIds,
    evidence: demoEvidence,
    sections: [
      {
        id: 'summary',
        heading: '综述预览',
        paragraphs: ['在这份固定示例中，统筹规划把问题拆成检索、分析和撰写任务。检索员收集候选段落，分析员整理证据及其限制，撰写员将这些发现归入综述提纲。[[1]][[2]]'],
      },
      {
        id: 'findings',
        heading: '核查预览',
        paragraphs: ['核查员发现一处引用缺少原文页码，反馈给统筹规划。检索员补齐来源，撰写员修订引用，核查员复核后交付带页码的示例综述。[[3]][[4]]'],
      },
    ],
  }
}

export function createDemoFollowUp(review: ReviewRun, question: string, referenceIds: string[]): ReviewRun {
  const { evidence, sections: previous, history = [] } = review
  const earlier = lastTurn(review)
  const body = previous.filter(({ id }) => id !== 'revision-note')
  let sections: ReviewSection[]

  if (/精简|要点|简短|简洁|缩短|压缩|摘要|概括|shorten|summary|concise/i.test(question)) {
    const points = body.slice(0, 3).flatMap(({ paragraphs }) => paragraphs.slice(0, 1).map((paragraph) => {
      const text = paragraph.replace(/\[\[\d+\]\]/g, '').replace(/^•\s*/, '')
      const firstSentence = text.match(/^[^。！？]+[。！？]?/)?.[0] ?? text
      const citations = [...new Set(paragraph.match(/\[\[\d+\]\]/g))].join('')
      return `• ${firstSentence}${citations}`
    }))
    sections = [{ id: 'key-points', heading: '精简版 · 要点', paragraphs: points.length ? points : ['上一轮没有可提炼的综述内容。'] }]
  } else if (/局限|不足|限制|展望|未来|limitation/i.test(question)) {
    sections = [
      ...body.filter(({ id }) => id !== 'limitations'),
      {
        id: 'limitations',
        heading: '研究局限与后续方向',
        paragraphs: [
          '示例文献的数量和覆盖范围有限。比较研究结果时，应保留各论文的样本、方法和评价指标，避免把单一研究的发现推广到其他场景。',
          evidence.length ? '下一步可补充不同研究条件下的对照文献，记录尚未覆盖的问题，并逐条核对有争议的结论。' : '目前没有可定位的原文和页码。下一步应先补充相关来源，再决定哪些结论可以保留。',
        ],
      },
    ]
  } else if (/引用|核查|证据|来源|citation|evidence|source/i.test(question)) {
    sections = [{
      id: 'citation-check',
      heading: '引用核查清单',
      paragraphs: evidence.length
        ? evidence.map(({ paper, page, excerpt }, index) => `${paper.title} · 第 ${page} 页：${excerpt}[[${index + 1}]]`)
        : ['上一轮没有可核对的引用。补充来源和页码后，才能核查对应的结论。'],
    }]
  } else {
    sections = [
      { id: 'revision-note', heading: '本轮修改', paragraphs: [`已记录你的要求：「${question}」。下面是基于上一轮内容的模拟回复。`] },
      ...body,
    ]
  }

  return { ...review, question, referenceIds, sections, history: [...history, earlier], mockVerified: undefined }
}
