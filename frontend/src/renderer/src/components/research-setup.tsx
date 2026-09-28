import { useEffect, useMemo, useRef, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from '@/components/ui/combobox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError, checkOpenRouterKey, type OpenRouterModel } from '@/lib/api'
import type { ModelChoice } from '@/lib/settings'

type KeyStatus = 'idle' | 'checking' | 'accepted' | 'rejected' | 'unreachable'

type ResearchSetupProps = {
  apiKey: string
  onApiKeyChange: (value: string) => void
  models: ModelChoice
  onModelsChange: (models: ModelChoice) => void
  catalog: OpenRouterModel[]
  catalogError: string | null
  onKeyRejectedChange: (rejected: boolean) => void
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

function ModelSelect({
  id,
  label,
  models,
  value,
  onChange
}: {
  id: string
  label: string
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
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</Label>
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
        <ComboboxInput id={id} placeholder="Search models" className="w-full" />
        <ComboboxContent>
          <ComboboxEmpty>No models match.</ComboboxEmpty>
          <ComboboxList>
            {(model: OpenRouterModel) => (
              <ComboboxItem key={model.id} value={model}>
                <span className="min-w-0 flex-1 truncate">{model.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {model.id.split('/')[0]}
                </span>
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

export function ResearchSetup({
  apiKey,
  onApiKeyChange,
  models,
  onModelsChange,
  catalog,
  catalogError,
  onKeyRejectedChange
}: ResearchSetupProps): React.JSX.Element {
  const [visible, setVisible] = useState(false)
  const [status, setStatus] = useState<KeyStatus>('idle')
  const onKeyRejectedChangeRef = useRef(onKeyRejectedChange)
  onKeyRejectedChangeRef.current = onKeyRejectedChange

  useEffect(() => {
    const key = apiKey.trim()
    if (key.length < 8) {
      setStatus('idle')
      onKeyRejectedChangeRef.current(false)
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
          if (cause instanceof ApiError && cause.status === 401) {
            setStatus('rejected')
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

  const keyMessage =
    status === 'checking'
      ? 'Checking key'
      : status === 'accepted'
        ? 'Key accepted'
        : status === 'rejected'
          ? 'OpenRouter rejected that key'
          : status === 'unreachable'
            ? 'Could not reach OpenRouter to check the key'
            : null

  return (
    <div className="flex flex-col gap-3">
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
            aria-invalid={status === 'rejected'}
            className="pr-8"
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
        {keyMessage ? (
          <p className={status === 'rejected' ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
            {keyMessage}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Saved on this computer and sent only to the local server.</p>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        The planner drafts questions, the extractor reads pages, and the writer writes the report.
      </p>

      {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
      {catalog.length === 0 && !catalogError ? (
        <p className="text-xs text-muted-foreground">Loading OpenRouter models</p>
      ) : null}

      <ModelSelect
        id="planner-model"
        label="Planner"
        models={plannerModels}
        value={models.planner}
        onChange={(planner) => onModelsChange({ ...models, planner })}
      />
      <ModelSelect
        id="extractor-model"
        label="Extractor"
        models={extractorModels}
        value={models.extractor}
        onChange={(extractor) => onModelsChange({ ...models, extractor })}
      />
      <ModelSelect
        id="writer-model"
        label="Writer"
        models={writerModels}
        value={models.writer}
        onChange={(writer) => onModelsChange({ ...models, writer })}
      />
    </div>
  )
}
