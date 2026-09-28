const API = 'http://127.0.0.1:8000'

export type ReportSummary = {
  slug: string
  title: string
  updated_at: string
}

export type ResearchEvent =
  | { type: 'gaps'; questions: string[] }
  | { type: 'search'; gap_id: number; urls: string[] }
  | { type: 'finding'; gap_id: number; source: string; answers: boolean; note: string }
  | { type: 'dead_url'; url: string }
  | { type: 'gap'; id: number; question: string; status: string; missing: string[] }
  | { type: 'report'; markdown: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export function slugify(topic: string): string {
  return Array.from(topic)
    .map((character) => (/^[\p{L}\p{N}]$/u.test(character) ? character.toLowerCase() : '-'))
    .join('')
    .replace(/^-+|-+$/gu, '')
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

export async function startResearch(
  topic: string,
  onEvent: (event: ResearchEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API}/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ topic }),
    signal
  })
  if (!response.ok) throw new Error(`Research failed (${response.status})`)
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

