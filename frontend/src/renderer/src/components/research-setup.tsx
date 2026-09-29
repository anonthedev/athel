import { useEffect, useMemo, useRef, useState } from 'react'
import { Eye, EyeOff, KeyRound } from 'lucide-react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from '@/components/ui/combobox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { ApiError, checkOpenRouterKey, type OpenRouterModel } from '@/lib/api'
import type { ModelChoice } from '@/lib/settings'

type KeyStatus = 'idle' | 'checking' | 'accepted' | 'rejected' | 'invalid' | 'unreachable'

type KeyProps = {
  apiKey: string
  onApiKeyChange: (value: string) => void
  status: KeyStatus
}

type ResearchOptionsProps = KeyProps & {
  models: ModelChoice
  onModelsChange: (models: ModelChoice) => void
  maxIterations: number
  onMaxIterationsChange: (value: number) => void
  catalog: OpenRouterModel[]
  catalogError: string | null
}

function choicesFor(
  catalog: OpenRouterModel[],
  selectedId: string,
  requireTools: boolean
): OpenRouterModel[] {
  const filtered = requireTools ? catalog.filter((model) => model.tools) : catalog
  if (!selectedId || filtered.some((model) => model.id === selectedId)) return filtered
  const existing = catalog.find((model) => model.id === selectedId)
  return [existing ?? { id: selectedId, name: selectedId, tools: true }, ...filtered]
}

function modelName(models: OpenRouterModel[], id: string): string {
  return models.find((model) => model.id === id)?.name ?? id.split('/').at(-1) ?? 'Model'
}

export function useApiKeyStatus(
  apiKey: string,
  onKeyRejectedChange: (rejected: boolean) => void
): KeyStatus {
  const [status, setStatus] = useState<KeyStatus>(() => {
    const key = apiKey.trim()
    if (key.length < 8) return 'idle'
    if (/\s/u.test(key)) return 'invalid'
    return 'checking'
  })
  const onKeyRejectedChangeRef = useRef(onKeyRejectedChange)
  onKeyRejectedChangeRef.current = onKeyRejectedChange

  useEffect(() => {
    const key = apiKey.trim()
    if (key.length < 8) {
      setStatus('idle')
      onKeyRejectedChangeRef.current(false)
      return
    }
    if (/\s/u.test(key)) {
      setStatus('invalid')
      onKeyRejectedChangeRef.current(true)
      return
    }

    const controller = new AbortController()
    setStatus('checking')
    const timer = window.setTimeout(() => {
      void checkOpenRouterKey(key, controller.signal).then(
        () => {
          setStatus('accepted')
          onKeyRejectedChangeRef.current(false)
        },
        (cause: unknown) => {
          if (cause instanceof DOMException && cause.name === 'AbortError') return
          if (cause instanceof ApiError && (cause.status === 401 || cause.status === 422)) {
            setStatus(cause.status === 422 ? 'invalid' : 'rejected')
            onKeyRejectedChangeRef.current(true)
            return
          }
          setStatus('unreachable')
          onKeyRejectedChangeRef.current(false)
        }
      )
    }, 500)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [apiKey])

  return status
}

function keyMessage(status: KeyStatus): string | null {
  if (status === 'checking') return 'Checking key'
  if (status === 'accepted') return 'Key accepted'
  if (status === 'rejected') return 'OpenRouter rejected that key'
  if (status === 'invalid') return "That isn't an OpenRouter API key"
  if (status === 'unreachable') return 'Could not reach OpenRouter to check the key'
  return null
}

function ApiKeyField({
  apiKey,
  onApiKeyChange,
  status,
  autoFocus = false
}: KeyProps & { autoFocus?: boolean }): React.JSX.Element {
  const [visible, setVisible] = useState(false)
  const message = keyMessage(status)

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor="openrouter-key" className="text-xs font-medium text-muted-foreground">
          OpenRouter API key
        </Label>
        <a
          href="https://openrouter.ai/keys"
          target="_blank"
          rel="noreferrer"
          className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          Get a key
        </a>
      </div>
      <div className="relative">
        <Input
          id="openrouter-key"
          value={apiKey}
          type={visible ? 'text' : 'password'}
          autoComplete="off"
          spellCheck={false}
          placeholder="sk-or-..."
          aria-invalid={status === 'rejected' || status === 'invalid'}
          className="pr-8"
          autoFocus={autoFocus}
          onChange={(event) => onApiKeyChange(event.target.value)}
          onBlur={() => onApiKeyChange(apiKey.trim())}
        />
        <button
          type="button"
          aria-label={visible ? 'Hide API key' : 'Show API key'}
          className="absolute top-1/2 right-1 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
        </button>
      </div>
      <p className={status === 'rejected' || status === 'invalid' ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
        {message ?? 'Saved on this computer and sent only to the local server.'}
      </p>
    </div>
  )
}

export function ApiKeyPrompt(props: KeyProps): React.JSX.Element {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-8 py-8">
      <div className="my-auto flex w-full max-w-md flex-col gap-6">
        <div className="flex flex-col gap-2 text-center">
          <h2 className="text-2xl font-medium tracking-tight">Add your OpenRouter key</h2>
          <p className="text-sm text-muted-foreground">
            Research runs with your key. It stays on this computer.
          </p>
        </div>
        <div className="overflow-hidden rounded-2xl border bg-card p-4 shadow-sm">
          <ApiKeyField {...props} autoFocus />
        </div>
      </div>
    </div>
  )
}

function ModelField({
  id,
  label,
  hint,
  models,
  value,
  onChange
}: {
  id: string
  label: string
  hint: string
  models: OpenRouterModel[]
  value: string
  onChange: (id: string) => void
}): React.JSX.Element {
  const selected = useMemo(
    () => models.find((model) => model.id === value) ?? null,
    [models, value]
  )

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-col gap-0.5">
        <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</Label>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <Combobox
        items={models}
        value={selected}
        autoHighlight
        itemToStringLabel={(model: OpenRouterModel) => model.name}
        isItemEqualToValue={(left: OpenRouterModel, right: OpenRouterModel) => left.id === right.id}
        filter={(model: OpenRouterModel, query: string) => {
          const needle = query.trim().toLowerCase()
          if (!needle) return true
          return `${model.name} ${model.id}`.toLowerCase().includes(needle)
        }}
        onValueChange={(next: OpenRouterModel | null) => {
          if (next) onChange(next.id)
        }}
      >
        <ComboboxInput id={id} placeholder={modelName(models, value)} className="w-full" />
        <ComboboxContent className="w-(--anchor-width) min-w-(--anchor-width)">
          <ComboboxEmpty>No models match.</ComboboxEmpty>
          <ComboboxList>
            {(model: OpenRouterModel) => (
              <ComboboxItem key={model.id} value={model}>
                <span className="min-w-0 flex-1 truncate">{model.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{model.id.split('/')[0]}</span>
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

export function ResearchOptions({
  apiKey,
  onApiKeyChange,
  status,
  models,
  onModelsChange,
  maxIterations,
  onMaxIterationsChange,
  catalog,
  catalogError
}: ResearchOptionsProps): React.JSX.Element {
  const plannerModels = useMemo(
    () => choicesFor(catalog, models.planner, true),
    [catalog, models.planner]
  )
  const extractorModels = useMemo(
    () => choicesFor(catalog, models.extractor, true),
    [catalog, models.extractor]
  )
  const writerModels = useMemo(
    () => choicesFor(catalog, models.writer, false),
    [catalog, models.writer]
  )

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Dialog>
          <DialogTrigger
            type="button"
            className="cursor-pointer inline-flex h-7 items-center rounded-md border border-border bg-background px-2.5 text-xs hover:bg-muted dark:bg-muted/70 text-muted-foreground"
          >
            Configure Models
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Models</DialogTitle>
              <DialogDescription>
                Choose who drafts the questions, reads the pages, and writes the report.
              </DialogDescription>
            </DialogHeader>
            <ModelField
              id="planner-model"
              label="Planner"
              hint="Drafts the research questions."
              models={plannerModels}
              value={models.planner}
              onChange={(planner) => onModelsChange({ ...models, planner })}
            />
            <ModelField
              id="extractor-model"
              label="Extractor"
              hint="Reads pages and pulls out facts."
              models={extractorModels}
              value={models.extractor}
              onChange={(extractor) => onModelsChange({ ...models, extractor })}
            />
            <ModelField
              id="writer-model"
              label="Writer"
              hint="Writes the report from the notes."
              models={writerModels}
              value={models.writer}
              onChange={(writer) => onModelsChange({ ...models, writer })}
            />
            {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
          </DialogContent>
        </Dialog>
        <Select
          value={String(maxIterations)}
          onValueChange={(value) => {
            const parsed = Number(value)
            if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 10) onMaxIterationsChange(parsed)
          }}
        >
          <SelectTrigger size="sm" aria-label="Max iterations" className="max-w-40 cursor-pointer hover:bg-muted">
            <span className="text-muted-foreground">Iterations</span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent side="top" align="start">
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
        <Popover>
          <PopoverTrigger
            type="button"
            aria-label="Change API key"
            className="inline-flex size-7 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer dark:bg-muted/70"
          >
            <KeyRound className="size-3.5" />
          </PopoverTrigger>
          <PopoverContent side="top" align="start" className="w-80">
            <ApiKeyField apiKey={apiKey} onApiKeyChange={onApiKeyChange} status={status} />
          </PopoverContent>
        </Popover>
      </div>
      {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
    </div>
  )
}
