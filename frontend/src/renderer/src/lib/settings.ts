const keyStorage = 'deep-research.openrouter-api-key'
const plannerStorage = 'deep-research.planner-model'
const extractorStorage = 'deep-research.extractor-model'
const writerStorage = 'deep-research.writer-model'
const iterationsStorage = 'deep-research.max-iterations'
const searchEngineStorage = 'deep-research.search-engine'
const tavilyKeyStorage = 'deep-research.tavily-api-key'

export const defaultModels = {
  planner: 'openai/gpt-5-mini',
  extractor: 'google/gemini-3.1-flash-lite',
  writer: 'anthropic/claude-sonnet-5'
} as const

export type ModelChoice = {
  planner: string
  extractor: string
  writer: string
}

export type SearchEngine = 'tavily' | 'duckduckgo'

export type ResearchSettings = {
  apiKey: string
  models: ModelChoice
  maxIterations: number
  searchEngine: SearchEngine
  tavilyKey: string
}

function readItem(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function readIterations(): number {
  const parsed = Number(readItem(iterationsStorage))
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 10) return 3
  return parsed
}

export function hasTavilyKey(value: string): boolean {
  const key = value.trim()
  return key.length >= 8 && !/\s/u.test(key)
}

function readSearchEngine(tavilyKey: string): SearchEngine {
  if (readItem(searchEngineStorage) === 'tavily' && hasTavilyKey(tavilyKey)) return 'tavily'
  return 'duckduckgo'
}

export function readSettings(): ResearchSettings {
  const tavilyKey = readItem(tavilyKeyStorage)
  return {
    apiKey: readItem(keyStorage),
    models: {
      planner: readItem(plannerStorage) || defaultModels.planner,
      extractor: readItem(extractorStorage) || defaultModels.extractor,
      writer: readItem(writerStorage) || defaultModels.writer
    },
    maxIterations: readIterations(),
    searchEngine: readSearchEngine(tavilyKey),
    tavilyKey
  }
}

export function writeSettings(settings: ResearchSettings): void {
  try {
    localStorage.setItem(keyStorage, settings.apiKey)
    localStorage.setItem(plannerStorage, settings.models.planner)
    localStorage.setItem(extractorStorage, settings.models.extractor)
    localStorage.setItem(writerStorage, settings.models.writer)
    localStorage.setItem(iterationsStorage, String(settings.maxIterations))
    localStorage.setItem(searchEngineStorage, settings.searchEngine)
    localStorage.setItem(tavilyKeyStorage, settings.tavilyKey)
  } catch {
    // The desktop window can still run this session if storage is blocked.
  }
}
