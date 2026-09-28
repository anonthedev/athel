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

function hostOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function TraceBlock({ label, children }: { label: string; children: ReactNode }): React.JSX.Element {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</h3>
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
          <ExternalLink href={event.source}>{hostOf(event.source)}</ExternalLink>
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
        <TraceBlock label={event.status === 'resolved' ? 'Resolved' : 'Failed'}>
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
        <TraceBlock label="Error">
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
  onAbort
}: {
  run: ResearchRun
  onAbort: () => void
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
      <header className="flex items-center gap-3 border-b px-8 py-4">
        <h2 className="min-w-0 truncate text-base font-medium">{run.topic}</h2>
        {run.status === 'running' ? (
          <span className="inline-flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
            <Spinner />
            {runStatusLabel(run)}
          </span>
        ) : null}
        {run.status === 'running' ? (
          <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={onAbort}>
            Abort
          </Button>
        ) : null}
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
          <div className="flex h-full items-center justify-center px-8">
            {run.status === 'error' ? (
              <p className="max-w-md text-center text-sm text-destructive">{run.error}</p>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                Writing the questions
              </div>
            )}
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-8 py-8">
            {run.events.map((event, index) => (
              <TraceEvent key={index} event={event} />
            ))}
            {run.error ? <p className="text-sm text-destructive">{run.error}</p> : null}
          </div>
        )}
      </div>
    </div>
  )
}
