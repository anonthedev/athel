import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type Ref } from 'react'
import { Folder, Moon, PanelLeft, PanelLeftClose, Plus, Settings, SettingsIcon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { MarkdownReport } from '@/components/markdown-report'
import { QuestionReview } from '@/components/question-review'
import { ApiKeyPrompt, SettingsDialog, useApiKeyStatus } from '@/components/research-setup'
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
import { hasTavilyKey, readSettings, writeSettings } from '@/lib/settings'
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
const sidebarStorage = 'deep-research.sidebar'

function readSidebarOpen(): boolean {
  try {
    return localStorage.getItem(sidebarStorage) !== 'closed'
  } catch {
    return true
  }
}

function SettingsButton({
  onClick,
  className
}: {
  onClick: () => void
  className?: string
}): React.JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex h-8 items-center rounded-md px-2 text-sm text-muted-foreground hover:text-foreground',
        className
      )}
      onClick={onClick}
    >
      <SettingsIcon className="size-4" />
    </button>
  )
}

function SidebarToggle({
  open,
  buttonRef,
  className,
  onClick
}: {
  open: boolean
  buttonRef: Ref<HTMLButtonElement>
  className?: string
  onClick: () => void
}): React.JSX.Element {
  return (
    <button
      ref={buttonRef}
      type="button"
      aria-expanded={open}
      aria-controls="report-list"
      aria-keyshortcuts="Control+\\ Meta+\\"
      aria-label={open ? 'Hide reports' : 'Show reports'}
      className={cn(
        'flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground',
        className
      )}
      onClick={onClick}
    >
      {open ? <PanelLeftClose className="size-4" /> : <PanelLeft className="size-4" />}
    </button>
  )
}

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
  const [sidebarOpen, setSidebarOpen] = useState(readSidebarOpen)
  const [settingsOpen, setSettingsOpen] = useState(false)
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
  const focusSidebar = useRef<'open' | 'closed' | null>(null)
  const expandRef = useRef<HTMLButtonElement>(null)
  const collapseRef = useRef<HTMLButtonElement>(null)
  const topicRef = useRef<HTMLTextAreaElement>(null)
  const continuing = useRef(new Set<string>())
  const runAbort = useRef(new Map<string, AbortController>())
  const abortedRuns = useRef(new Set<string>())
  const userNavigated = useRef(false)
  const openSeq = useRef(0)

  function go(next: Screen): void {
    userNavigated.current = true
    screenRef.current = next
    setScreen(next)
    if (next.type === 'compose') requestAnimationFrame(() => topicRef.current?.focus())
  }

  const setSidebar = useCallback((next: boolean): void => {
    focusSidebar.current = next ? 'open' : 'closed'
    setSidebarOpen(next)
    try {
      localStorage.setItem(sidebarStorage, next ? 'open' : 'closed')
    } catch {
      // The window still toggles for this session.
    }
  }, [])

  useLayoutEffect(() => {
    if (focusSidebar.current === 'open') collapseRef.current?.focus()
    if (focusSidebar.current === 'closed') expandRef.current?.focus()
    focusSidebar.current = null
  }, [sidebarOpen])

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key !== '\\' || event.altKey || event.shiftKey || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      setSidebar(!sidebarOpen)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setSidebar, sidebarOpen])

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

  const modelsReady = Boolean(models.planner && models.extractor && models.writer && models.embedding)
  const activeRun = runs.find((run) => screen.type === 'trace' && run.id === screen.id)
  const ongoing = runs.filter(
    (run) => run.status === 'running' || run.status === 'review' || run.status === 'error'
  )

  return (
    <div className="flex h-full min-h-0 w-full bg-background font-sans text-foreground">
      <aside
        id="report-list"
        inert={!sidebarOpen}
        aria-hidden={!sidebarOpen}
        className={cn(
          'h-full shrink-0 overflow-hidden transition-[width] duration-200 ease-out motion-reduce:transition-none',
          sidebarOpen ? 'w-72' : 'w-0'
        )}
      >
        <div className="flex h-full w-72 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
        <div className="flex items-center justify-between gap-2 px-3 pt-3">
          <span className="px-1 text-base font-medium tracking-[-0.03em]">Athel</span>
          <SidebarToggle
            open
            buttonRef={collapseRef}
            className="hover:bg-sidebar-accent"
            onClick={() => setSidebar(false)}
          />
        </div>
        <div className="px-3 pt-3 pb-2">
          <Button type="button" className="w-full" onClick={() => go({ type: 'compose' })}>
            <Plus />
            New research
          </Button>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="flex flex-col gap-1 px-2 pb-4">
            {ongoing.length > 0 ? (
              <h2 className="px-3 pt-3 pb-1 text-sm text-muted-foreground">Ongoing research</h2>
            ) : null}
            <ul className="flex flex-col">
              {ongoing.map((run) => {
                const current = screen.type === 'trace' && screen.id === run.id
                return (
                  <li key={run.id}>
                    <button
                      type="button"
                      title={run.topic}
                      aria-current={current ? 'page' : undefined}
                      className={cn(
                        'relative flex w-full flex-col items-start gap-0.5 rounded-md py-2 pr-2 pl-3 text-left hover:bg-sidebar-accent',
                        current &&
                          'bg-sidebar-accent before:absolute before:top-2 before:bottom-2 before:left-0 before:w-0.5 before:rounded-full before:bg-primary'
                      )}
                      onClick={() => go({ type: 'trace', id: run.id })}
                    >
                      <span className="line-clamp-2 text-sm font-medium">{run.topic}</span>
                      <span
                        className={cn(
                          'inline-flex items-center gap-2 text-sm text-muted-foreground',
                          run.status === 'error' && 'text-destructive'
                        )}
                      >
                        {run.status === 'running' ? (
                          <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
                        ) : null}
                        {runStatusLabel(run)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>

            <div className="flex items-center justify-between px-3 pt-3 pb-1">
              <h2 className="text-sm text-muted-foreground">Reports</h2>
              <button
                type="button"
                aria-label="Open reports folder"
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
                onClick={() => void window.api.openReportsFolder()}
              >
                <Folder className="size-4" />
              </button>
            </div>
            {loadingList ? (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
                <Spinner />
                Loading reports
              </div>
            ) : null}
            {listError ? (
              <p role="alert" className="px-3 py-2 text-sm text-destructive">
                {listError}
              </p>
            ) : null}
            {!loadingList && reports.length === 0 ? (
              <p className="px-3 py-3 text-sm text-muted-foreground">No reports yet.</p>
            ) : null}
            <ul className="flex flex-col">
              {reports.map((report) => {
                const current = screen.type === 'report' && screen.slug === report.slug
                return (
                  <li key={report.slug}>
                    <button
                      type="button"
                      title={report.title}
                      aria-current={current ? 'page' : undefined}
                      className={cn(
                        'relative flex w-full flex-col items-start gap-0.5 rounded-md py-2 pr-2 pl-3 text-left hover:bg-sidebar-accent',
                        current &&
                          'bg-sidebar-accent before:absolute before:top-2 before:bottom-2 before:left-0 before:w-0.5 before:rounded-full before:bg-primary'
                      )}
                      onClick={() => void openSaved(report)}
                    >
                      <span className="line-clamp-2 text-sm font-medium">{report.title}</span>
                      <span className="text-sm text-muted-foreground">{formatUpdated(report.updated_at)}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </ScrollArea>
        <div className="flex items-center justify-between gap-2 border-t border-sidebar-border px-2 py-2">
          <SettingsButton onClick={() => setSettingsOpen(true)} className="hover:bg-sidebar-accent" />
          <button
            type="button"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
            onClick={() => {
              const next = theme === 'dark' ? 'light' : 'dark'
              setTheme(next)
              applyTheme(next)
            }}
          >
            {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
        </div>
      </aside>

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        {screen.type === 'compose' && !sidebarOpen ? (
          <div className="absolute top-2 left-2 z-10">
            <SidebarToggle
              open={false}
              buttonRef={expandRef}
              className="hover:bg-muted"
              onClick={() => setSidebar(true)}
            />
          </div>
        ) : null}
        {screen.type === 'compose' && !keyReady ? (
          <ApiKeyPrompt apiKey={apiKey} onApiKeyChange={setApiKey} status={keyStatus} />
        ) : null}

        {screen.type === 'compose' && keyReady ? (
          <form
            className="flex h-full min-h-0 w-full flex-1 items-center justify-center overflow-y-auto px-8 py-8"
            onSubmit={onSubmit}
          >
            <div className="my-auto flex w-full max-w-xl flex-col items-center gap-8">
              <div className="flex flex-col gap-2 text-center">
                <h1 id="topic-label" className="text-2xl font-medium tracking-tight">
                  What should I research?
                </h1>
                <p className="text-sm text-muted-foreground">
                  Ask one question. You can edit the research questions before the search starts.
                </p>
              </div>
              <div className="flex w-full flex-col gap-3">
                <div className="research-field w-full overflow-hidden rounded-2xl border bg-card">
                  <Textarea
                    ref={topicRef}
                    id="topic"
                    aria-labelledby="topic-label"
                    autoFocus
                    value={topic}
                    placeholder="A question, a debate, or a stretch of history"
                    rows={5}
                    className="min-h-36 resize-none border-0 bg-transparent px-4 py-4 text-base shadow-none md:text-base dark:bg-transparent"
                    onChange={(event) => setTopic(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                        event.preventDefault()
                        event.currentTarget.form?.requestSubmit()
                      }
                    }}
                  />
                  <div className="flex items-center justify-between gap-3 px-3 pb-3">
                    <button
                      type="button"
                      aria-label="Settings"
                      className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                      onClick={() => setSettingsOpen(true)}
                    >
                      <Settings className="size-4" />
                    </button>
                    <div className="flex items-center gap-3">
                      <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                        <Kbd className="border border-border bg-transparent dark:bg-transparent">{submitHint}</Kbd>
                        <Kbd className="border border-border bg-transparent dark:bg-transparent">Enter</Kbd>
                      </p>
                      <Button type="submit" disabled={topic.trim().length === 0 || !modelsReady}>
                        Research
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Select
                    value={searchEngine}
                    onValueChange={(value) => {
                      if (value === 'duckduckgo') {
                        setSearchEngine('duckduckgo')
                        return
                      }
                      if (value !== 'tavily') return
                      if (hasTavilyKey(tavilyKey)) {
                        setSearchEngine('tavily')
                        return
                      }
                      setSettingsOpen(true)
                    }}
                  >
                    <SelectTrigger size="sm" aria-label="Search engine" className="cursor-pointer">
                      <span className="text-muted-foreground">Search</span>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent side="bottom" align="start">
                      <SelectItem value="tavily">Tavily</SelectItem>
                      <SelectItem value="duckduckgo">DuckDuckGo</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select
                    value={String(maxIterations)}
                    onValueChange={(value) => {
                      const parsed = Number(value)
                      if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 10) setMaxIterations(parsed)
                    }}
                  >
                    <SelectTrigger size="sm" aria-label="Follow-up searches" className="cursor-pointer">
                      <span className="text-muted-foreground">Iterations</span>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent side="bottom" align="start">
                      {Array.from({ length: 10 }, (_, index) => {
                        const count = String(index + 1)
                        return (
                          <SelectItem key={count} value={count}>
                            {count}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="rounded-full border bg-background px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => {
                      setTopic(suggestion)
                      topicRef.current?.focus()
                    }}
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
            onOpenSettings={() => setSettingsOpen(true)}
            leading={
              sidebarOpen ? null : (
                <SidebarToggle
                  open={false}
                  buttonRef={expandRef}
                  className="hover:bg-muted"
                  onClick={() => setSidebar(true)}
                />
              )
            }
          />
        ) : null}

        {screen.type === 'trace' && activeRun && activeRun.status !== 'review' ? (
          <ResearchTrace
            run={activeRun}
            onAbort={() => abortRun(activeRun.id)}
            onOpenSettings={() => setSettingsOpen(true)}
            leading={
              sidebarOpen ? null : (
                <SidebarToggle
                  open={false}
                  buttonRef={expandRef}
                  className="hover:bg-muted"
                  onClick={() => setSidebar(true)}
                />
              )
            }
          />
        ) : null}

        {screen.type === 'report' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <header className="flex h-12 shrink-0 items-center gap-2 border-b px-2">
              {sidebarOpen ? null : (
                <SidebarToggle
                  open={false}
                  buttonRef={expandRef}
                  className="hover:bg-muted"
                  onClick={() => setSidebar(true)}
                />
              )}
              <h2
                className="min-w-0 flex-1 truncate px-2 text-sm font-medium"
                title={article?.slug === screen.slug ? article.title : undefined}
              >
                {article?.slug === screen.slug ? article.title : 'Report'}
              </h2>
            </header>
            {reportError && article?.slug !== screen.slug ? (
              <p role="alert" className="px-8 py-4 text-sm text-destructive">
                {reportError}
              </p>
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
      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
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
    </div>
  )
}

export default App
