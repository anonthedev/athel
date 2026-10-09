import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'
import { ExternalLink } from '@/components/markdown-report'
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig
} from '@/components/ui/chart'
import { Spinner } from '@/components/ui/spinner'
import {
  ApiError,
  getTrace,
  type ResearchTraceData,
  type TraceCall,
  type TraceStep
} from '@/lib/api'
import { cn } from '@/lib/utils'

const roleOrder = ['planner', 'extractor', 'writer', 'embedding']

const roleLabels: Record<string, string> = {
  planner: 'Planner',
  extractor: 'Extractor',
  writer: 'Writer',
  embedding: 'Embeddings'
}

const nodeLabels: Record<string, string> = {
  generate_gaps: 'Drafted questions',
  review_gaps: 'Approved questions',
  draft_queries: 'Wrote search queries',
  search: 'Searched',
  collect_hits: 'Collected sources',
  scrape: 'Read pages',
  update_checklist: 'Checked gaps',
  write_final_report: 'Wrote the report'
}

const tokenConfig = {
  input: { label: 'Input tokens', color: 'var(--chart-1)' },
  output: { label: 'Output tokens', color: 'var(--chart-2)' }
} satisfies ChartConfig

const priceConfig = {
  cost: { label: 'Price', color: 'var(--chart-3)' }
} satisfies ChartConfig

function formatTokens(value: number): string {
  return value.toLocaleString()
}

function formatCost(value: number): string {
  const absolute = Math.abs(value)
  if (absolute === 0) return '$0'
  if (absolute < 0.01) return `$${value.toFixed(4)}`
  return `$${value.toFixed(2)}`
}

function formatWhen(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

function roleLabel(role: string): string {
  return roleLabels[role] ?? role
}

function stepTitle(nodes: string[]): string {
  if (nodes.length === 0) return 'Model call'
  const counts = new Map<string, number>()
  for (const node of nodes) counts.set(node, (counts.get(node) ?? 0) + 1)
  return [...counts.entries()]
    .map(([name, count]) => {
      const label = nodeLabels[name] ?? name
      return count > 1 ? `${label} × ${count}` : label
    })
    .join(', ')
}

function gapMark(status: string): { label: string; color: string } {
  if (status === 'resolved') return { label: 'Resolved', color: 'bg-success' }
  if (status === 'partial') return { label: 'Partial', color: 'bg-warning' }
  return { label: 'Unresolved', color: 'bg-destructive' }
}

function tokensByRole(calls: TraceCall[]): { role: string; input: number; output: number }[] {
  const totals = new Map<string, { role: string; input: number; output: number }>()
  for (const call of calls) {
    const key = roleLabels[call.role] ? call.role : call.role || 'other'
    const row = totals.get(key) ?? { role: roleLabel(key), input: 0, output: 0 }
    row.input += call.input_tokens
    row.output += call.output_tokens
    totals.set(key, row)
  }
  const ordered = roleOrder.filter((role) => totals.has(role)).map((role) => totals.get(role)!)
  for (const [key, row] of totals) {
    if (!roleOrder.includes(key)) ordered.push(row)
  }
  return ordered
}

function priceSeries(steps: TraceStep[]): { step: string; title: string; cost: number }[] | null {
  let total = 0
  let priced = false
  const points = steps.map((step, index) => {
    for (const call of step.calls) {
      if (call.cost != null) {
        total += call.cost
        priced = true
      }
    }
    return { step: String(index + 1), title: stepTitle(step.nodes), cost: total }
  })
  return priced ? points : null
}

function CallLabel({ label }: { label: string }): React.JSX.Element {
  if (label.startsWith('http://') || label.startsWith('https://')) {
    return (
      <span className="break-all">
        <ExternalLink href={label}>{label}</ExternalLink>
      </span>
    )
  }
  return <span>{label}</span>
}

function UsageCharts({
  calls,
  steps
}: {
  calls: TraceCall[]
  steps: TraceStep[]
}): React.JSX.Element | null {
  const byRole = tokensByRole(calls)
  const prices = priceSeries(steps)
  if (byRole.length === 0) return null

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-medium">Tokens by role</h3>
        <ChartContainer config={tokenConfig} className="aspect-auto! h-56 w-full">
          <BarChart data={byRole} accessibilityLayer>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="role" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} width={48} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="input" fill="var(--color-input)" radius={2} isAnimationActive={false} />
            <Bar dataKey="output" fill="var(--color-output)" radius={2} isAnimationActive={false} />
          </BarChart>
        </ChartContainer>
      </section>
      {prices ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">Price over the run</h3>
          <ChartContainer config={priceConfig} className="aspect-auto! h-56 w-full">
            <LineChart data={prices} accessibilityLayer>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="step" tickLine={false} axisLine={false} />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={56}
                tickFormatter={(value: number) => formatCost(value)}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line
                dataKey="cost"
                type="monotone"
                stroke="var(--color-cost)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ChartContainer>
        </section>
      ) : null}
    </div>
  )
}

function StepList({ steps }: { steps: TraceStep[] }): React.JSX.Element {
  return (
    <div className="flex flex-col">
      {steps.map((step, index) => (
        <section key={`${step.at ?? 'step'}-${index}`} className="flex flex-col gap-3 border-t py-6 first:border-t-0 first:pt-0">
          <div className="flex items-baseline justify-between gap-4">
            <h3 className="text-sm font-medium">{stepTitle(step.nodes)}</h3>
            {formatWhen(step.at) ? (
              <time className="shrink-0 text-sm text-muted-foreground" dateTime={step.at ?? undefined}>
                {formatWhen(step.at)}
              </time>
            ) : null}
          </div>
          {step.calls.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {step.calls.map((call, callIndex) => (
                <li key={`${call.role}-${callIndex}`} className="flex flex-col gap-1">
                  <p className="text-sm">
                    <span className="font-medium">{roleLabel(call.role)}</span>
                    {call.model ? <span className="text-muted-foreground"> {call.model}</span> : null}
                  </p>
                  {call.label ? (
                    <p className="text-sm text-muted-foreground">
                      <CallLabel label={call.label} />
                    </p>
                  ) : null}
                  <p className="flex flex-wrap gap-x-4 text-sm text-muted-foreground tabular-nums">
                    <span>{formatTokens(call.input_tokens)} input</span>
                    <span>{formatTokens(call.output_tokens)} output</span>
                    {call.cost != null ? <span>{formatCost(call.cost)}</span> : null}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
          {step.questions.length > 0 ? (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {step.questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ol>
          ) : null}
          {step.queries.map((item) => (
            <div key={item.question} className="flex flex-col gap-1">
              <p className="text-sm">{item.question}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {item.queries.map((query) => (
                  <li key={query}>{query}</li>
                ))}
              </ul>
            </div>
          ))}
          {step.urls.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {step.urls.map((url) => (
                <li key={url} className="text-sm break-all">
                  <ExternalLink href={url}>{url}</ExternalLink>
                </li>
              ))}
            </ul>
          ) : null}
          {step.findings.map((finding, findingIndex) => (
            <div key={`${finding.source}-${findingIndex}`} className="flex flex-col gap-1">
              <p className="text-sm break-all">
                <ExternalLink href={finding.source}>{finding.source}</ExternalLink>
              </p>
              {finding.note ? <p className="text-sm leading-6 whitespace-pre-wrap">{finding.note}</p> : null}
            </div>
          ))}
          {step.gaps.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {step.gaps.map((gap) => {
                const mark = gapMark(gap.status)
                return (
                  <li key={gap.question} className="flex items-start gap-2.5">
                    <span className={cn('mt-1.5 size-2.5 shrink-0 rounded-full', mark.color)} title={mark.label} />
                    <div className="min-w-0">
                      <p className="text-sm leading-5">{gap.question}</p>
                      {gap.missing.length > 0 ? (
                        <p className="text-sm text-muted-foreground">Still needed: {gap.missing.join('; ')}</p>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : null}
          {step.dead_urls.length > 0 ? (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer">Skipped {step.dead_urls.length}</summary>
              <ul className="flex flex-col gap-1 pt-2">
                {step.dead_urls.map((url) => (
                  <li key={url} className="break-all">
                    <ExternalLink href={url}>{url}</ExternalLink>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {step.report ? <p className="text-sm">The report is written.</p> : null}
        </section>
      ))}
    </div>
  )
}

export function ResearchUsage({ slug }: { slug: string }): React.JSX.Element {
  const [trace, setTrace] = useState<ResearchTraceData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setTrace(null)
    setError(null)
    getTrace(slug, controller.signal)
      .then((next) => setTrace(next))
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        if (cause instanceof ApiError && cause.status === 404) {
          setError('Usage was not saved for this report. Research started from now on keeps a trace after it finishes.')
          return
        }
        setError(cause instanceof Error ? cause.message : 'Could not load usage')
      })
    return () => controller.abort()
  }, [slug])

  if (error) {
    return (
      <div className="mx-auto w-full max-w-2xl px-8 py-10">
        <p role="alert" className="text-sm text-muted-foreground">
          {error}
        </p>
      </div>
    )
  }

  if (!trace) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        Loading usage
      </div>
    )
  }

  const input = trace.calls.reduce((sum, call) => sum + call.input_tokens, 0)
  const output = trace.calls.reduce((sum, call) => sum + call.output_tokens, 0)
  const priced = trace.calls.filter((call) => call.cost != null)
  const cost = priced.reduce((sum, call) => sum + (call.cost ?? 0), 0)
  const local = trace.provider === 'ollama'

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto">
      <div className="flex w-full max-w-3xl flex-col gap-10 px-8 py-8">
        <dl className="flex flex-wrap justify-center gap-x-10 gap-y-3 text-center">
          <div>
            <dt className="text-sm text-muted-foreground">Input tokens</dt>
            <dd className="text-2xl font-medium tracking-tight tabular-nums">{formatTokens(input)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Output tokens</dt>
            <dd className="text-2xl font-medium tracking-tight tabular-nums">{formatTokens(output)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Price</dt>
            <dd className="text-2xl font-medium tracking-tight tabular-nums">
              {priced.length > 0 ? formatCost(cost) : '—'}
            </dd>
          </div>
        </dl>
        {priced.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground">
            {local
              ? 'This run used a local model, so there is no API price.'
              : 'This run did not report a price.'}
          </p>
        ) : priced.length < trace.calls.length ? (
          <p className="text-center text-sm text-muted-foreground">Some calls did not report a price. The total includes the ones that did.</p>
        ) : null}
        {trace.calls.length === 0 && trace.steps.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground">This research has no saved steps.</p>
        ) : (
          <>
            <UsageCharts calls={trace.calls} steps={trace.steps} />
            {trace.steps.length > 0 ? (
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">Steps</h3>
                <StepList steps={trace.steps} />
              </section>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
