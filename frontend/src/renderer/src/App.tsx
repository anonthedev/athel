import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Folder, Moon, Plus, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { MarkdownReport } from '@/components/markdown-report'
import { QuestionReview } from '@/components/question-review'
import { ApiKeyPrompt, ResearchOptions, useApiKeyStatus } from '@/components/research-setup'
import { ResearchTrace, runStatusLabel, type DraftQuestion, type ResearchRun } from '@/components/research-trace'
import {
  abortResearch,
  getReport,
  listEmbeddingModels,
  listModels,
  listReports,
  resumeResearch,
  slugify,
  startResearch,
  type OpenRouterModel,
  type ReportSummary,
  type ResearchEvent
} from '@/lib/api'
import { readSettings, writeSettings } from '@/lib/settings'
import { applyTheme, readTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

type Screen = { type: 'compose' } | { type: 'trace'; id: string } | { type: 'report'; slug: string }

type Article = {
  slug: string
  title: string
  markdown: string
}

const suggestions = [
  'How do solid-state batteries store energy?',
  'Why did the shipping container change trade?',
  'What makes cities flood more often?'
]

const submitHint = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl'

function formatUpdated(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

function App(): React.JSX.Element {
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [runs, setRuns] = useState<ResearchRun[]>([])
  const [screen, setScreen] = useState<Screen>({ type: 'compose' })
  const [topic, setTopic] = useState('')
  const [article, setArticle] = useState<Article | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [theme, setTheme] = useState<Theme>(readTheme)
  const [apiKey, setApiKey] = useState(() => readSettings().apiKey)
  const [models, setModels] = useState(() => readSettings().models)
  const [maxIterations, setMaxIterations] = useState(() => readSettings().maxIterations)
  const [searchEngine, setSearchEngine] = useState(() => readSettings().searchEngine)
  const [tavilyKey, setTavilyKey] = useState(() => readSettings().tavilyKey)
  const [catalog, setCatalog] = useState<OpenRouterModel[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [embeddingCatalog, setEmbeddingCatalog] = useState<OpenRouterModel[]>([])
  const [embeddingCatalogError, setEmbeddingCatalogError] = useState<string | null>(null)
  const [keyRejected, setKeyRejected] = useState(false)
  const keyStatus = useApiKeyStatus(apiKey, setKeyRejected)
  const keyReady = keyStatus === 'accepted'
  const screenRef = useRef<Screen>({ type: 'compose' })
  const continuing = useRef(new Set<string>())
  const runAbort = useRef(new Map<string, AbortController>())
  const abortedRuns = useRef(new Set<string>())
  const userNavigated = useRef(false)
  const openSeq = useRef(0)

  function go(next: Screen): void {
    userNavigated.current = true
    screenRef.current = next
    setScreen(next)
  }

  useEffect(() => {
    writeSettings({ apiKey, models, maxIterations, searchEngine, tavilyKey })
  }, [apiKey, models, maxIterations, searchEngine, tavilyKey])

  useEffect(() => {
    const controller = new AbortController()
    listModels(controller.signal)
      .then((items) => setCatalog(items))
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setCatalogError(cause instanceof Error ? cause.message : 'Could not load OpenRouter models')
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!keyReady) return
    const controller = new AbortController()
    listEmbeddingModels(apiKey, controller.signal)
      .then((items) => {
        setEmbeddingCatalog(items)
        setEmbeddingCatalogError(null)
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setEmbeddingCatalogError(cause instanceof Error ? cause.message : 'Could not load embedding models')
      })
    return () => controller.abort()
  }, [apiKey, keyReady])

  useEffect(() => {
    const controller = new AbortController()
    listReports(controller.signal)
      .then(async (items) => {
        setReports(items)
        const first = items[0]
        if (!first || userNavigated.current) return
        const markdown = await getReport(first.slug, controller.signal)
        if (userNavigated.current) return
        screenRef.current = { type: 'report', slug: first.slug }
        setScreen({ type: 'report', slug: first.slug })
        setArticle({ slug: first.slug, title: first.title, markdown })
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setListError(cause instanceof Error ? cause.message : 'Could not load reports')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingList(false)
      })
    return () => controller.abort()
  }, [])

  async function openSaved(report: ReportSummary): Promise<void> {
    const seq = ++openSeq.current
    go({ type: 'report', slug: report.slug })
    setReportError(null)
    if (article?.slug === report.slug && article.markdown) return
    try {
      const markdown = await getReport(report.slug)
      if (openSeq.current !== seq) return
      setArticle({ slug: report.slug, title: report.title, markdown })
    } catch (cause: unknown) {
      if (openSeq.current !== seq) return
      setReportError(cause instanceof Error ? cause.message : 'Could not open that report')
    }
  }

  function patchRun(id: string, update: (run: ResearchRun) => ResearchRun): void {
    setRuns((current) => current.map((item) => (item.id === id ? update(item) : item)))
  }

  function draftQuestions(questions: string[]): DraftQuestion[] {
    return questions.map((text) => ({ id: crypto.randomUUID(), text }))
  }

  function applyEvent(
    id: string,
    researchEvent: ResearchEvent,
    report: { markdown: string },
    paused: { value: boolean }
  ): void {
    if (abortedRuns.current.has(id)) return
    if (researchEvent.type === 'aborted') {
      abortRun(id)
      return
    }
    if (researchEvent.type === 'report') report.markdown = researchEvent.markdown
    if (researchEvent.type === 'review') {
      paused.value = true
      patchRun(id, (item) => ({
        ...item,
        status: 'review',
        questions: draftQuestions(researchEvent.questions),
        reviewError: researchEvent.error ?? null
      }))
      return
    }
    if (researchEvent.type === 'error') {
      patchRun(id, (item) => ({ ...item, status: 'error', error: researchEvent.message }))
      return
    }
    if (researchEvent.type === 'done' || researchEvent.type === 'gaps') return
    patchRun(id, (item) => ({ ...item, events: [...item.events, researchEvent] }))
  }

  async function openFinishedReport(id: string, nextTopic: string, reportMarkdown: string): Promise<void> {
    if (abortedRuns.current.has(id)) return
    const items = await listReports()
    if (abortedRuns.current.has(id)) return
    setReports(items)
    const saved = items.find((item) => item.slug === slugify(nextTopic))
    if (!saved) {
      patchRun(id, (item) => ({
        ...item,
        status: 'error',
        error: item.error ?? 'Report was not saved'
      }))
      return
    }

    const markdown = reportMarkdown || (await getReport(saved.slug))
    if (abortedRuns.current.has(id)) return
    const watching = screenRef.current.type === 'trace' && screenRef.current.id === id
    if (watching) {
      screenRef.current = { type: 'report', slug: saved.slug }
      setScreen({ type: 'report', slug: saved.slug })
      setArticle({ slug: saved.slug, title: saved.title, markdown })
      setReportError(null)
    }
    setRuns((current) => current.filter((item) => item.id !== id))
  }

  function failRun(id: string, cause: unknown): void {
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    const message = cause instanceof Error ? cause.message : 'Research failed'
    patchRun(id, (item) => ({ ...item, status: 'error', error: message }))
  }

  function bindRun(id: string): AbortSignal {
    const controller = new AbortController()
    runAbort.current.set(id, controller)
    return controller.signal
  }

  function abortRun(id: string): void {
    if (abortedRuns.current.has(id)) return
    abortedRuns.current.add(id)
    runAbort.current.get(id)?.abort()
    runAbort.current.delete(id)
    continuing.current.delete(id)
    void abortResearch(id).catch(() => undefined)
    setRuns((current) => current.filter((item) => item.id !== id))
    if (screenRef.current.type === 'trace' && screenRef.current.id === id) {
      go({ type: 'compose' })
    }
  }

  function onSubmit(event: FormEvent): void {
    event.preventDefault()
    const nextTopic = topic.trim()
    const nextKey = apiKey.trim()
    if (!nextTopic || nextKey.length < 8 || keyRejected) return
    if (!models.planner || !models.extractor || !models.writer || !models.embedding) return

    const id = crypto.randomUUID()
    const run: ResearchRun = {
      id,
      topic: nextTopic,
      status: 'running',
      phase: 'drafting',
      questions: [],
      reviewError: null,
      events: [],
      error: null
    }
    setRuns((current) => [run, ...current])
    go({ type: 'trace', id })
    setTopic('')

    void (async () => {
      const report = { markdown: '' }
      const paused = { value: false }
      const signal = bindRun(id)
      try {
        await startResearch(
          nextTopic,
          { apiKey: nextKey, models, tavilyKey, threadId: id, maxIterations, searchEngine },
          (researchEvent) => {
            applyEvent(id, researchEvent, report, paused)
          },
          signal
        )
        if (abortedRuns.current.has(id) || paused.value) return
        await openFinishedReport(id, nextTopic, report.markdown)
      } catch (cause: unknown) {
        if (abortedRuns.current.has(id)) return
        failRun(id, cause)
      }
    })()
  }

  function continueResearch(id: string): void {
    if (continuing.current.has(id)) return
    const run = runs.find((item) => item.id === id)
    const nextKey = apiKey.trim()
    if (!run || run.status !== 'review') return
    const questions = run.questions
      .map((question) => question.text.trim())
      .filter(Boolean)
      .slice(0, 7)
    if (questions.length === 0) {
      patchRun(id, (item) => ({ ...item, reviewError: 'Add at least one question' }))
      return
    }

    continuing.current.add(id)
    patchRun(id, (item) => ({
      ...item,
      status: 'running',
      phase: 'researching',
      reviewError: null,
      events: [{ type: 'gaps', questions }, ...item.events.filter((event) => event.type !== 'gaps')]
    }))

    void (async () => {
      const report = { markdown: '' }
      const paused = { value: false }
      const signal = bindRun(id)
      try {
        await resumeResearch(id, questions, { apiKey: nextKey, models, tavilyKey }, (researchEvent) => {
          applyEvent(id, researchEvent, report, paused)
        }, signal)
      } catch (cause: unknown) {
        if (abortedRuns.current.has(id)) return
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        const message = cause instanceof Error ? cause.message : 'Research failed'
        patchRun(id, (item) => ({ ...item, status: 'review', reviewError: message }))
        return
      } finally {
        continuing.current.delete(id)
      }
      if (abortedRuns.current.has(id) || paused.value) return
      try {
        await openFinishedReport(id, run.topic, report.markdown)
      } catch (cause: unknown) {
        if (abortedRuns.current.has(id)) return
        failRun(id, cause)
      }
    })()
  }

  const activeRun = runs.find((run) => screen.type === 'trace' && run.id === screen.id)
  const ongoing = runs.filter(
    (run) => run.status === 'running' || run.status === 'review' || run.status === 'error'
  )

  return (
    <div className="flex h-full min-h-0 w-full bg-background font-sans text-foreground">
      <aside className="flex w-72 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
        <div className="px-3 pt-3 pb-2">
          <Button type="button" className="w-full" onClick={() => go({ type: 'compose' })}>
            <Plus />
            New Research
          </Button>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="flex flex-col gap-1 px-2 pb-4">
            {ongoing.length > 0 ? (
              <div className="px-2.5 pt-3 pb-1 text-xs font-medium text-muted-foreground">
                Ongoing research
              </div>
            ) : null}
            {ongoing.map((run) => (
              <button
                key={run.id}
                type="button"
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left hover:bg-sidebar-accent',
                  screen.type === 'trace' && screen.id === run.id && 'bg-sidebar-accent'
                )}
                onClick={() => go({ type: 'trace', id: run.id })}
              >
                <span className="line-clamp-2 text-sm font-medium">{run.topic}</span>
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  {run.status === 'running' ? <Spinner /> : null}
                  {runStatusLabel(run)}
                </span>
              </button>
            ))}

            <div className="flex items-center justify-between px-2.5 pt-3 pb-1">
              <span className="text-xs font-medium text-muted-foreground">Reports</span>
              <button
                type="button"
                aria-label="Open reports folder"
                className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
                onClick={() => void window.api.openReportsFolder()}
              >
                <Folder className="size-3.5" />
              </button>
            </div>
            {loadingList ? (
              <div className="flex items-center gap-2 px-2.5 py-3 text-sm text-muted-foreground">
                <Spinner />
                Loading reports
              </div>
            ) : null}
            {listError ? <p className="px-2.5 py-2 text-sm text-destructive">{listError}</p> : null}
            {!loadingList && reports.length === 0 ? (
              <p className="px-2.5 py-3 text-sm text-muted-foreground">No reports yet.</p>
            ) : null}
            {reports.map((report) => (
              <button
                key={report.slug}
                type="button"
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left hover:bg-sidebar-accent',
                  screen.type === 'report' && screen.slug === report.slug && 'bg-sidebar-accent'
                )}
                onClick={() => void openSaved(report)}
              >
                <span className="line-clamp-2 text-sm font-medium">{report.title}</span>
                <span className="text-xs text-muted-foreground">
                  {formatUpdated(report.updated_at)}
                </span>
              </button>
            ))}
          </div>
        </ScrollArea>
        <div className="flex justify-end border-t px-3 py-2">
          <button
            type="button"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
            onClick={() => {
              const next = theme === 'dark' ? 'light' : 'dark'
              setTheme(next)
              applyTheme(next)
            }}
          >
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {screen.type === 'compose' && !keyReady ? (
          <ApiKeyPrompt apiKey={apiKey} onApiKeyChange={setApiKey} status={keyStatus} />
        ) : null}

        {screen.type === 'compose' && keyReady ? (
          <form className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-8 py-8" onSubmit={onSubmit}>
            <div className="my-auto flex w-full max-w-xl flex-col items-center gap-8">
              <div className="flex flex-col gap-2 text-center">
                <h2 className="text-2xl font-medium tracking-tight">What should I research?</h2>
                <p className="text-sm text-muted-foreground">
                  Ask one question. You can edit the research questions before the search starts.
                </p>
              </div>
              <div className="w-full overflow-hidden rounded-2xl border bg-card shadow-sm transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/40">
                <Textarea
                  autoFocus
                  value={topic}
                  placeholder="A question, a debate, or a stretch of history"
                  rows={5}
                  className="min-h-36 resize-none border-0 bg-transparent px-4 py-4 text-base shadow-none focus-visible:border-transparent focus-visible:ring-0 disabled:bg-transparent md:text-base dark:bg-transparent dark:disabled:bg-transparent"
                  onChange={(event) => setTopic(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault()
                      event.currentTarget.form?.requestSubmit()
                    }
                  }}
                />
                <div className="flex flex-wrap items-end justify-between gap-3 bg-card px-3 pb-3">
                  <ResearchOptions
                    apiKey={apiKey}
                    onApiKeyChange={setApiKey}
                    status={keyStatus}
                    models={models}
                    onModelsChange={setModels}
                    maxIterations={maxIterations}
                    onMaxIterationsChange={setMaxIterations}
                    searchEngine={searchEngine}
                    onSearchEngineChange={setSearchEngine}
                    tavilyKey={tavilyKey}
                    onTavilyKeyChange={setTavilyKey}
                    catalog={catalog}
                    catalogError={catalogError}
                    embeddingCatalog={embeddingCatalog}
                    embeddingCatalogError={embeddingCatalogError}
                  />
                  <div className="ml-auto flex items-center gap-3">
                    <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Kbd className="border border-border bg-transparent dark:bg-transparent">{submitHint}</Kbd>
                      <Kbd className="border border-border bg-transparent dark:bg-transparent">Enter</Kbd>
                    </p>
                    <Button
                      type="submit"
                      className="disabled:bg-muted disabled:cursor-not-allowed disabled:text-muted-foreground disabled:opacity-100 dark:disabled:bg-muted cursor-pointer rounded-md"
                      disabled={
                        topic.trim().length === 0 ||
                        !models.planner ||
                        !models.extractor ||
                        !models.writer ||
                        !models.embedding
                      }
                    >
                      Research
                    </Button>
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="rounded-full border bg-background px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setTopic(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </form>
        ) : null}

        {screen.type === 'trace' && activeRun?.status === 'review' ? (
          <QuestionReview
            topic={activeRun.topic}
            questions={activeRun.questions}
            error={activeRun.reviewError}
            onChange={(questions) =>
              patchRun(activeRun.id, (item) => ({ ...item, questions, reviewError: null }))
            }
            onContinue={() => continueResearch(activeRun.id)}
            onAbort={() => abortRun(activeRun.id)}
          />
        ) : null}

        {screen.type === 'trace' && activeRun && activeRun.status !== 'review' ? (
          <ResearchTrace run={activeRun} onAbort={() => abortRun(activeRun.id)} />
        ) : null}

        {screen.type === 'report' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <header className="border-b py-4">
              <h2 className="reading-column truncate px-8 text-base font-medium">
                {article?.slug === screen.slug ? article.title : 'Report'}
              </h2>
            </header>
            {reportError && article?.slug !== screen.slug ? (
              <p className="px-8 py-4 text-sm text-destructive">{reportError}</p>
            ) : null}
            {article?.slug === screen.slug ? (
              <div className="min-h-0 flex-1 overflow-y-auto">
                <MarkdownReport markdown={article.markdown} />
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                Opening report
              </div>
            )}
          </div>
        ) : null}
      </main>
    </div>
  )
}

export default App
