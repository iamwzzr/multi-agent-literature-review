import { BackendRequestError } from './backend'
import type { AgentId } from './workflow'

type Presentation = {
  title: string
  action?: 'backend' | 'project'
  retry?: boolean
  informational?: boolean
}

const presentations: Record<string, Presentation> = {
  MODEL_NOT_CONFIGURED: { title: '模型尚未配置', retry: false },
  MODEL_CONFIG_INVALID: { title: '模型配置有误', retry: false },
  MODEL_AUTH_FAILED: { title: '模型鉴权失败', retry: false },
  MODEL_QUOTA_EXCEEDED: { title: '模型余额或额度不足', retry: false },
  MODEL_ENDPOINT_NOT_FOUND: { title: '模型或接口地址不可用', retry: false },
  MODEL_REQUEST_REJECTED: { title: '模型请求参数有误', retry: false },
  MODEL_RATE_LIMITED: { title: '模型调用受限' },
  MODEL_SERVICE_UNAVAILABLE: { title: '模型服务暂不可用' },
  MODEL_UNAVAILABLE: { title: '后端无法连接模型服务' },
  MODEL_HTTP_ERROR: { title: '模型服务返回错误' },
  MODEL_TIMEOUT: { title: '模型响应超时' },
  MODEL_OUTPUT_INVALID: { title: '模型返回格式异常' },
  MODEL_OUTPUT_TRUNCATED: { title: '模型输出被截断', retry: false },
  MODEL_REFUSAL: { title: '模型未完成请求', retry: false },
  MODEL_BUDGET_EXCEEDED: { title: '本轮达到模型调用上限', retry: false },
  CONTEXT_TOO_LARGE: { title: '模型上下文过长', retry: false },
  REQUEST_TOO_LARGE: { title: '本轮请求过大', retry: false },
  RESPONSE_TOO_LARGE: { title: '综述响应过长', retry: false },
  INVALID_REQUEST: { title: '本轮请求需要调整', retry: false },
  INVALID_KNOWLEDGE_PATH: { title: '知识库目录不可用', action: 'project', retry: false },
  PROJECT_CONFLICT: { title: '工作目录与项目不匹配', action: 'project', retry: false },
  LIBRARY_TOO_LARGE: { title: '知识库超出索引限制', action: 'project', retry: false },
  PDF_TOO_LARGE: { title: 'PDF 文件超出大小限制', action: 'project', retry: false },
  PDF_PARSE_FAILED: { title: 'PDF 无法解析', action: 'project', retry: false },
  PROJECT_BUSY: { title: '此项目正在运行任务' },
  SERVER_BUSY: { title: '后端并发已满' },
  RUN_TIMEOUT: { title: '本轮任务超时', retry: false },
  AUTH_REQUIRED: { title: '后端访问需要令牌', action: 'backend', retry: false },
  LOCAL_ONLY: { title: '后端仅接受本机连接', action: 'backend', retry: false },
  HTTPS_REQUIRED: { title: '远程后端需要 HTTPS', action: 'backend', retry: false },
  BACKEND_UNREACHABLE: { title: '无法连接后端', action: 'backend' },
  INVALID_STREAM: { title: '后端响应格式异常', action: 'backend', retry: false },
  STREAM_DISCONNECTED: { title: '后端连接中断', action: 'backend' },
  STREAM_TIMEOUT: { title: '后端连接超时', action: 'backend' },
  RUN_PENDING: { title: '上次任务仍在运行', retry: false, informational: true },
  RUN_INTERRUPTED: { title: '上次任务已中断' },
  RUN_STOPPED: { title: '本轮已停止', informational: true },
  CHECK_STOPPED: { title: '已停止检查任务', retry: false, informational: true },
}

export type ReviewFailure = Presentation & {
  message: string
  code?: string
  agent?: AgentId
  providerStatus?: number
  retry: boolean
}

export function describeReviewFailure(failure: unknown, localCode?: string): ReviewFailure {
  const details = failure instanceof BackendRequestError ? failure.details : undefined
  const code = localCode ?? details?.code
  const presentation = code && Object.hasOwn(presentations, code) ? presentations[code] : { title: '本轮未完成' }
  return {
    ...presentation,
    message: failure instanceof Error ? failure.message : typeof failure === 'string' ? failure : '生成失败，可以稍后重试。',
    code,
    agent: details?.agent,
    providerStatus: details?.providerStatus,
    retry: details?.retryable ?? presentation.retry ?? true,
  }
}
