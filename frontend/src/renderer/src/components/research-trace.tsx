import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import type { ResearchEvent } from '@/lib/api'
import { ExternalLink } from '@/components/markdown-report'

export type DraftQuestion = {
  id: string
  text: string
}

export type ResearchRun = {
  id: string
  topic: string
  status: 'running' | 'review' | 'error'
  phase: 'drafting' | 'researching'
  questions: DraftQuestion[]
  reviewError: string | null
  events: ResearchEvent[]
  error: string | null
}

export function runStatusLabel(run: Pick<ResearchRun, 'status' | 'phase'>): string {
  if (run.status === 'error') return 'Could not finish'
  if (run.status === 'review') return 'Review questions'
  if (run.phase === 'drafting') return 'Drafting questions'
  return 'Researching'
}

function gapStatusLabel(status: string): string {
  if (status === 'resolved') return 'Resolved'
  if (status === 'partial') return 'Partially answered'
  return 'Failed'
}

function TraceBlock({
  label,
  tone = 'text-muted-foreground',
  children
}: {
  label: string
  tone?: string
  children: ReactNode
}): React.JSX.Element {
  return (
    <section className="flex flex-col gap-2 border-t pt-5 first:border-t-0 first:pt-0">
      <h3 className={`text-sm font-medium ${tone}`}>{label}</h3>
      {children}
    </section>
  )
}

function TraceEvent({ event }: { event: ResearchEvent }): React.JSX.Element | null {
  switch (event.type) {
    case 'gaps':
      return (
        <TraceBlock label="Questions">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {event.questions.map((question, index) => (
              <li key={`${index}-${question}`}>{question}</li>
            ))}
          </ol>
        </TraceBlock>
      )
    case 'search':
      return (
        <TraceBlock label="Sources">
          <ul className="flex flex-col gap-1">
            {event.urls.map((url) => (
              <li key={url} className="text-sm break-all">
                <ExternalLink href={url}>{url}</ExternalLink>
              </li>
            ))}
          </ul>
        </TraceBlock>
      )
    case 'finding':
      return (
        <TraceBlock label={event.answers ? 'Finding' : 'Note'}>
          <p className="text-sm break-all">
            <ExternalLink href={event.source}>{event.source}</ExternalLink>
          </p>
          {event.note ? <p className="text-sm leading-6 whitespace-pre-wrap">{event.note}</p> : null}
        </TraceBlock>
      )
    case 'dead_url':
      return (
        <TraceBlock label="Skipped">
          <p className="text-sm break-all">
            <ExternalLink href={event.url}>{event.url}</ExternalLink>
          </p>
        </TraceBlock>
      )
    case 'gap':
      if (event.status === 'pending') return null
      return (
        <TraceBlock
          label={gapStatusLabel(event.status)}
          tone={
            event.status === 'resolved'
              ? 'text-success'
              : event.status === 'partial'
                ? 'text-warning'
                : 'text-destructive'
          }
        >
          <p className="text-sm">{event.question}</p>
          {event.missing.length > 0 ? (
            <p className="text-sm text-muted-foreground">{event.missing.join(' ')}</p>
          ) : null}
        </TraceBlock>
      )
    case 'report':
      return (
        <TraceBlock label="Report">
          <p className="text-sm">The report is written.</p>
        </TraceBlock>
      )
    case 'error':
      return (
        <TraceBlock label="Error" tone="text-destructive">
          <p className="text-sm text-destructive">{event.message}</p>
        </TraceBlock>
      )
    case 'review':
    case 'done':
    case 'aborted':
      return null
  }
}

export function ResearchTrace({
  run,
  onAbort,
  onOpenSettings,
  leading
}: {
  run: ResearchRun
  onAbort: () => void
  onOpenSettings: () => void
  leading?: ReactNode
}): React.JSX.Element {
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  useEffect(() => {
    const node = scroller.current
    if (!node || !stick.current) return
    node.scrollTop = node.scrollHeight
  }, [run.events.length])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-2">
        {leading}
        <h2 className="min-w-0 truncate px-2 text-sm font-medium" title={run.topic}>
          {run.topic}
        </h2>
        {run.status === 'running' ? (
          <span className="inline-flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
            <Spinner />
            {runStatusLabel(run)}
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            className="inline-flex h-8 items-center rounded-md px-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            onClick={onOpenSettings}
          >
            Settings
          </button>
          {run.status === 'running' ? (
            <Button type="button" variant="outline" size="sm" onClick={onAbort}>
              Abort
            </Button>
          ) : null}
        </div>
      </header>
      <div
        ref={scroller}
        className="min-h-0 flex-1 overflow-y-auto"
        onScroll={() => {
          const node = scroller.current
          if (!node) return
          stick.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80
        }}
      >
        {run.events.length === 0 ? (
          <div className="mx-auto w-full max-w-2xl px-8 py-10">
            {run.status === 'error' ? (
              <p role="alert" className="text-sm text-destructive">
                {run.error}
              </p>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                Writing the questions
              </div>
            )}
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-2xl flex-col px-8 py-8">
            {run.events.map((event, index) => (
              <TraceEvent key={index} event={event} />
            ))}
            {run.error ? (
              <p role="alert" className="pt-5 text-sm text-destructive">
                {run.error}
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
