const keyStorage = 'deep-research.openrouter-api-key'
const providerStorage = 'deep-research.provider'
const plannerStorage = 'deep-research.planner-model'
const extractorStorage = 'deep-research.extractor-model'
const writerStorage = 'deep-research.writer-model'
const embeddingStorage = 'deep-research.embedding-model'
const ollamaPlannerStorage = 'deep-research.ollama.planner-model'
const ollamaExtractorStorage = 'deep-research.ollama.extractor-model'
const ollamaWriterStorage = 'deep-research.ollama.writer-model'
const ollamaEmbeddingStorage = 'deep-research.ollama.embedding-model'
const iterationsStorage = 'deep-research.max-iterations'
const searchEngineStorage = 'deep-research.search-engine'
const tavilyKeyStorage = 'deep-research.tavily-api-key'
const writingToneStorage = 'deep-research.writing-tone'

export const defaultModels = {
  planner: 'openai/gpt-5-mini',
  extractor: 'google/gemini-3.1-flash-lite',
  writer: 'anthropic/claude-sonnet-5',
  embedding: 'openai/text-embedding-3-small'
} as const

export type ModelChoice = {
  planner: string
  extractor: string
  writer: string
  embedding: string
}

export type SearchEngine = 'tavily' | 'duckduckgo'
export type WritingTone = 'clear' | 'academic'

export type Provider = 'openrouter' | 'ollama'

export const emptyOllamaModels: ModelChoice = {
  planner: '',
  extractor: '',
  writer: '',
  embedding: ''
}

export function fillOllamaModels(
  current: ModelChoice,
  catalog: { id: string; tools: boolean; embedding?: boolean }[]
): ModelChoice {
  const chat = catalog.find((model) => model.tools)
  const embed = catalog.find((model) => model.embedding)
  return {
    planner: current.planner || chat?.id || '',
    extractor: current.extractor || chat?.id || '',
    writer: current.writer || chat?.id || '',
    embedding: current.embedding || embed?.id || ''
  }
}

export type ResearchSettings = {
  provider: Provider
  apiKey: string
  models: ModelChoice
  ollamaModels: ModelChoice
  maxIterations: number
  searchEngine: SearchEngine
  tavilyKey: string
  writingTone: WritingTone
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

function readProvider(): Provider {
  return readItem(providerStorage) === 'ollama' ? 'ollama' : 'openrouter'
}

function readWritingTone(): WritingTone {
  return readItem(writingToneStorage) === 'academic' ? 'academic' : 'clear'
}

export function readSettings(): ResearchSettings {
  const tavilyKey = readItem(tavilyKeyStorage)
  return {
    provider: readProvider(),
    apiKey: readItem(keyStorage),
    models: {
      planner: readItem(plannerStorage) || defaultModels.planner,
      extractor: readItem(extractorStorage) || defaultModels.extractor,
      writer: readItem(writerStorage) || defaultModels.writer,
      embedding: readItem(embeddingStorage) || defaultModels.embedding
    },
    ollamaModels: {
      planner: readItem(ollamaPlannerStorage),
      extractor: readItem(ollamaExtractorStorage),
      writer: readItem(ollamaWriterStorage),
      embedding: readItem(ollamaEmbeddingStorage)
    },
    maxIterations: readIterations(),
    searchEngine: readSearchEngine(tavilyKey),
    tavilyKey,
    writingTone: readWritingTone()
  }
}

export function writeSettings(settings: ResearchSettings): void {
  try {
    localStorage.setItem(providerStorage, settings.provider)
    localStorage.setItem(keyStorage, settings.apiKey)
    localStorage.setItem(plannerStorage, settings.models.planner)
    localStorage.setItem(extractorStorage, settings.models.extractor)
    localStorage.setItem(writerStorage, settings.models.writer)
    localStorage.setItem(embeddingStorage, settings.models.embedding)
    localStorage.setItem(ollamaPlannerStorage, settings.ollamaModels.planner)
    localStorage.setItem(ollamaExtractorStorage, settings.ollamaModels.extractor)
    localStorage.setItem(ollamaWriterStorage, settings.ollamaModels.writer)
    localStorage.setItem(ollamaEmbeddingStorage, settings.ollamaModels.embedding)
    localStorage.setItem(iterationsStorage, String(settings.maxIterations))
    localStorage.setItem(searchEngineStorage, settings.searchEngine)
    localStorage.setItem(tavilyKeyStorage, settings.tavilyKey)
    localStorage.setItem(writingToneStorage, settings.writingTone)
  } catch {
    // The desktop window can still run this session if storage is blocked.
  }
}
