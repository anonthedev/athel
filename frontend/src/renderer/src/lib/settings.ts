const keyStorage = 'deep-research.openrouter-api-key'
const plannerStorage = 'deep-research.planner-model'
const extractorStorage = 'deep-research.extractor-model'
const writerStorage = 'deep-research.writer-model'
const iterationsStorage = 'deep-research.max-iterations'

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

export type ResearchSettings = {
  apiKey: string
  models: ModelChoice
  maxIterations: number
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

export function readSettings(): ResearchSettings {
  return {
    apiKey: readItem(keyStorage),
    models: {
      planner: readItem(plannerStorage) || defaultModels.planner,
      extractor: readItem(extractorStorage) || defaultModels.extractor,
      writer: readItem(writerStorage) || defaultModels.writer
    },
    maxIterations: readIterations()
  }
}

export function writeSettings(settings: ResearchSettings): void {
  try {
    localStorage.setItem(keyStorage, settings.apiKey)
    localStorage.setItem(plannerStorage, settings.models.planner)
    localStorage.setItem(extractorStorage, settings.models.extractor)
    localStorage.setItem(writerStorage, settings.models.writer)
    localStorage.setItem(iterationsStorage, String(settings.maxIterations))
  } catch {
    // The desktop window can still run this session if storage is blocked.
  }
}
