import type { ModelChoice, Provider, SearchEngine } from '@/lib/settings'

const API = 'http://127.0.0.1:8000'

export type OpenRouterModel = {
  id: string
  name: string
  tools: boolean
  embedding?: boolean
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  } catch {
    // The response was not JSON.
  }
  return fallback
}

export type ReportSummary = {
  slug: string
  title: string
  updated_at: string
}

export type ResearchEvent =
  | { type: 'gaps'; questions: string[] }
  | { type: 'review'; thread_id: string; questions: string[]; error?: string }
  | { type: 'search'; gap_id: number; urls: string[] }
  | { type: 'finding'; gap_id: number; source: string; answers: boolean; note: string }
  | { type: 'dead_url'; url: string }
  | { type: 'gap'; id: number; question: string; status: string; missing: string[] }
  | { type: 'report'; markdown: string }
  | { type: 'activity'; message: string }
  | { type: 'done' }
  | { type: 'aborted' }
  | { type: 'error'; message: string }

type ResearchAuth = {
  provider: Provider
  apiKey: string
  models: ModelChoice
  tavilyKey: string
}

export function slugify(topic: string): string {
  const slug = Array.from(topic)
    .map((character) => (/^[\p{L}\p{N}]$/u.test(character) ? character.toLowerCase() : '-'))
    .join('')
    .replace(/^-+|-+$/gu, '')
  return Array.from(slug).slice(0, 40).join('').replace(/-+$/u, '')
}

export async function listReports(signal?: AbortSignal): Promise<ReportSummary[]> {
  const response = await fetch(`${API}/reports`, { signal })
  if (!response.ok) throw new Error('Could not load reports')
  return response.json() as Promise<ReportSummary[]>
}

export async function getReport(slug: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(`${API}/reports/${encodeURIComponent(slug)}`, { signal })
  if (!response.ok) throw new Error('Could not open that report')
  return response.text()
}

export async function listEmbeddingModels(apiKey: string, signal?: AbortSignal): Promise<OpenRouterModel[]> {
  const response = await fetch(`${API}/embedding-models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
    signal
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response, 'Could not load embedding models'))
  }
  return response.json() as Promise<OpenRouterModel[]>
}

export async function listOllamaModels(signal?: AbortSignal): Promise<OpenRouterModel[]> {
  const response = await fetch(`${API}/ollama/models`, { signal })
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response, 'Could not load Ollama models'))
  return response.json() as Promise<OpenRouterModel[]>
}

export async function listModels(signal?: AbortSignal): Promise<OpenRouterModel[]> {
  const response = await fetch(`${API}/models`, { signal })
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response, 'Could not load OpenRouter models'))
  return response.json() as Promise<OpenRouterModel[]>
}

export async function checkOpenRouterKey(apiKey: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${API}/openrouter/key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
    signal
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response, 'Could not check that key'))
  }
}

function researchBody(options: ResearchAuth): Record<string, string> {
  return {
    provider: options.provider,
    api_key: options.provider === 'ollama' ? '' : options.apiKey,
    planner_model: options.models.planner,
    extractor_model: options.models.extractor,
    writer_model: options.models.writer,
    embedding_model: options.models.embedding,
    tavily_api_key: options.tavilyKey
  }
}

async function readEventStream(response: Response, onEvent: (event: ResearchEvent) => void): Promise<void> {
  if (!response.body) throw new Error('Research returned an empty stream')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const emit = (chunk: string): void => {
    const dataLine = chunk.split('\n').find((line) => line.startsWith('data: '))
    if (!dataLine) return
    onEvent(JSON.parse(dataLine.slice(6)) as ResearchEvent)
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) emit(part)
    if (done) {
      if (buffer.trim()) emit(buffer)
      break
    }
  }
}

async function postResearch(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: ResearchEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response, `Research failed (${response.status})`))
  }
  await readEventStream(response, onEvent)
}

export async function startResearch(
  topic: string,
  options: ResearchAuth & { threadId: string; maxIterations: number; searchEngine: SearchEngine },
  onEvent: (event: ResearchEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  await postResearch(
    '/research',
    {
      topic,
      thread_id: options.threadId,
      max_iterations: options.maxIterations,
      search_engine: options.searchEngine,
      ...researchBody(options)
    },
    onEvent,
    signal
  )
}

export async function abortResearch(threadId: string): Promise<void> {
  const response = await fetch(`${API}/research/${encodeURIComponent(threadId)}/abort`, {
    method: 'POST'
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response, 'Could not abort research'))
  }
}

export async function resumeResearch(
  threadId: string,
  questions: string[],
  options: ResearchAuth,
  onEvent: (event: ResearchEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  await postResearch(
    `/research/${encodeURIComponent(threadId)}/resume`,
    { questions, ...researchBody(options) },
    onEvent,
    signal
  )
}

