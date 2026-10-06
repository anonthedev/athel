import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDownIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { ResearchEvent } from '@/lib/api'
import { cn } from '@/lib/utils'
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
  activity: string | null
  error: string | null
}

type GapEvent = Extract<ResearchEvent, { type: 'gap' }>

type TracePiece =
  | { kind: 'event'; event: ResearchEvent }
  | { kind: 'gaps'; gaps: GapEvent[] }
  | { kind: 'skipped'; urls: string[] }

export function runStatusLabel(run: Pick<ResearchRun, 'status' | 'phase'>): string {
  if (run.status === 'error') return 'Could not finish'
  if (run.status === 'review') return 'Review questions'
  if (run.phase === 'drafting') return 'Drafting questions'
  return 'Researching'
}

function gapMark(status: string): { label: string; color: string } {
  if (status === 'resolved') return { label: 'Resolved', color: 'bg-success' }
  if (status === 'partial') return { label: 'Partial', color: 'bg-warning' }
  return { label: 'Unresolved', color: 'bg-destructive' }
}

function groupTrace(events: ResearchEvent[]): TracePiece[] {
  const pieces: TracePiece[] = []
  let skipped: Extract<TracePiece, { kind: 'skipped' }> | null = null

  for (const event of events) {
    if (event.type === 'dead_url') {
      if (!skipped) {
        skipped = { kind: 'skipped', urls: [] }
        pieces.push(skipped)
      }
      if (!skipped.urls.includes(event.url)) skipped.urls.push(event.url)
      continue
    }
    if (event.type === 'gap') {
      const last = pieces[pieces.length - 1]
      if (last?.kind === 'gaps') last.gaps.push(event)
      else pieces.push({ kind: 'gaps', gaps: [event] })
      continue
    }
    pieces.push({ kind: 'event', event })
  }

  return pieces
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
    <section className="flex flex-col gap-2">
      <h3 className={`text-sm font-medium ${tone}`}>{label}</h3>
      {children}
    </section>
  )
}

function SkippedUrls({ urls }: { urls: string[] }): React.JSX.Element {
  const [open, setOpen] = useState(false)

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="inline-flex items-center gap-1.5 rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        Skipped ({urls.length})
        <ChevronDownIcon
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
          aria-hidden="true"
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="flex flex-col gap-1 pt-2">
          {urls.map((url) => (
            <li key={url} className="text-sm break-all">
              <ExternalLink href={url}>{url}</ExternalLink>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  )
}

function GapList({ gaps }: { gaps: GapEvent[] }): React.JSX.Element {
  return (
    <ul className="flex flex-col gap-2">
      {gaps.map((gap, index) => {
        const mark = gapMark(gap.status)
        return (
          <li key={`${gap.id}-${index}`} className="flex items-center gap-2.5">
            <Tooltip>
              <TooltipTrigger
                aria-label={mark.label}
                className={cn(
                  'size-2.5 shrink-0 rounded-full border-0 p-0 outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  mark.color
                )}
              />
              <TooltipContent side="right">{mark.label}</TooltipContent>
            </Tooltip>
            <p className="min-w-0 text-sm leading-5">{gap.question}</p>
          </li>
        )
      })}
    </ul>
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
    case 'dead_url':
    case 'gap':
    case 'activity':
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
  const pieces = groupTrace(run.events)

  useEffect(() => {
    const node = scroller.current
    if (!node || !stick.current) return
    node.scrollTop = node.scrollHeight
  }, [run.events.length, run.activity])

  return (
    <TooltipProvider delay={300}>
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-2">
          {leading}
          <h2 className="min-w-0 truncate px-2 text-sm font-medium" title={run.topic}>
            {run.topic}
          </h2>
          {run.status === 'running' ? (
            <span className="inline-flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
              <Spinner />
              {run.activity ?? runStatusLabel(run)}
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
                  {run.activity ?? 'Writing the questions'}
                </div>
              )}
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-8 py-8">
              {pieces.map((piece, index) => {
                if (piece.kind === 'skipped') return <SkippedUrls key="skipped" urls={piece.urls} />
                if (piece.kind === 'gaps') return <GapList key={`gaps-${index}`} gaps={piece.gaps} />
                return <TraceEvent key={index} event={piece.event} />
              })}
              {run.status === 'running' && run.activity ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Spinner />
                  {run.activity}
                </div>
              ) : null}
              {run.error ? (
                <p role="alert" className="text-sm text-destructive">
                  {run.error}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </TooltipProvider>
  )
}
