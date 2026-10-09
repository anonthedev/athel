import { useEffect, useMemo, useRef, useState, type ReactNode, type Ref } from 'react'
import { Eye, EyeOff, Minus, Plus, SettingsIcon } from 'lucide-react'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from '@/components/ui/combobox'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ApiError, checkOpenRouterKey, type OpenRouterModel } from '@/lib/api'
import { hasTavilyKey, type ModelChoice, type Provider, type SearchEngine, type WritingTone } from '@/lib/settings'
import { cn } from '@/lib/utils'

type KeyStatus = 'idle' | 'checking' | 'accepted' | 'rejected' | 'invalid' | 'unreachable'

type KeyProps = {
  apiKey: string
  onApiKeyChange: (value: string) => void
  status: KeyStatus
}

type ResearchOptionsProps = KeyProps & {
  provider: Provider
  onProviderChange: (value: Provider) => void
  models: ModelChoice
  onModelsChange: (models: ModelChoice) => void
  maxIterations: number
  onMaxIterationsChange: (value: number) => void
  searchEngine: SearchEngine
  onSearchEngineChange: (value: SearchEngine) => void
  tavilyKey: string
  onTavilyKeyChange: (value: string) => void
  writingTone: WritingTone
  onWritingToneChange: (value: WritingTone) => void
  catalog: OpenRouterModel[]
  catalogLoaded?: boolean
  catalogError: string | null
  embeddingCatalog: OpenRouterModel[]
  embeddingCatalogError: string | null
}

function choicesFor(catalog: OpenRouterModel[], selectedId: string, requireTools: boolean): OpenRouterModel[] {
  const filtered = requireTools ? catalog.filter((model) => model.tools) : catalog
  if (!selectedId || filtered.some((model) => model.id === selectedId)) return filtered
  const existing = catalog.find((model) => model.id === selectedId)
  return [existing ?? { id: selectedId, name: selectedId, tools: true }, ...filtered]
}

function modelName(models: OpenRouterModel[], id: string): string {
  return models.find((model) => model.id === id)?.name ?? id.split('/').at(-1) ?? 'Model'
}

export function useApiKeyStatus(apiKey: string, onKeyRejectedChange: (rejected: boolean) => void): KeyStatus {
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
  const failed = status === 'rejected' || status === 'invalid'
  const tone = failed ? 'text-destructive' : status === 'accepted' ? 'text-success' : 'text-muted-foreground'

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor="openrouter-key" className="text-sm font-medium">
          OpenRouter API key
        </Label>
        <a
          href="https://openrouter.ai/keys"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-muted-foreground underline decoration-primary underline-offset-2 hover:text-foreground"
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
          aria-invalid={failed}
          aria-describedby="openrouter-key-status"
          className="h-9 pr-10"
          autoFocus={autoFocus}
          onChange={(event) => onApiKeyChange(event.target.value)}
          onBlur={() => onApiKeyChange(apiKey.trim())}
        />
        <button
          type="button"
          aria-label={visible ? 'Hide API key' : 'Show API key'}
          className="absolute top-1/2 right-0.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
      <p id="openrouter-key-status" aria-live="polite" className={`text-sm ${tone}`}>
        {message ?? 'Saved on this computer and sent only to the local server.'}
      </p>
    </div>
  )
}

function TavilyKeyField({
  id,
  value,
  onChange,
  onCommit,
  attention = false,
  inputRef,
  autoFocus = false
}: {
  id: string
  value: string
  onChange: (value: string) => void
  onCommit?: (value: string) => void
  attention?: boolean
  inputRef?: Ref<HTMLInputElement>
  autoFocus?: boolean
}): React.JSX.Element {
  const [visible, setVisible] = useState(false)
  const invalid = value.trim().length > 0 && (value.trim().length < 8 || /\s/u.test(value))
  const message = invalid
    ? "That isn't a Tavily API key"
    : attention
      ? 'Add a Tavily key to search with Tavily.'
      : 'Saved on this computer and sent only to the local server.'

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor={id} className="text-sm font-medium">
          Tavily API key
        </Label>
        <a
          href="https://app.tavily.com"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-muted-foreground underline decoration-primary underline-offset-2 hover:text-foreground"
        >
          Get a key
        </a>
      </div>
      <div className="relative">
        <Input
          ref={inputRef}
          id={id}
          value={value}
          type={visible ? 'text' : 'password'}
          autoComplete="off"
          spellCheck={false}
          placeholder="tvly-..."
          aria-invalid={invalid}
          aria-describedby={`${id}-status`}
          className="h-9 pr-10"
          autoFocus={autoFocus}
          onChange={(event) => onChange(event.target.value)}
          onBlur={(event) => {
            const next = event.currentTarget.value.trim()
            onChange(next)
            onCommit?.(next)
          }}
        />
        <button
          type="button"
          aria-label={visible ? 'Hide Tavily API key' : 'Show Tavily API key'}
          className="absolute top-1/2 right-0.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
      <p
        id={`${id}-status`}
        aria-live="polite"
        className={
          invalid ? 'text-sm text-destructive' : attention ? 'text-sm text-warning' : 'text-sm text-muted-foreground'
        }
      >
        {message}
      </p>
    </div>
  )
}

export function ApiKeyPrompt({ onUseLocal, ...props }: KeyProps & { onUseLocal: () => void }): React.JSX.Element {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="my-auto flex w-full max-w-md flex-col gap-6 self-center px-8 py-10">
        <div className="flex flex-col gap-2">
          <h1 className="text-[1.75rem] font-medium tracking-[-0.03em]">Add your OpenRouter key</h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Research runs with your key. It stays on this computer.
          </p>
        </div>
        <ApiKeyField {...props} autoFocus />
        <button
          type="button"
          className="self-start text-sm text-muted-foreground underline decoration-primary underline-offset-2 hover:text-foreground"
          onClick={onUseLocal}
        >
          Use a model on this computer
        </button>
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
  const selected = useMemo(() => models.find((model) => model.id === value) ?? null, [models, value])

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-col gap-0.5">
        <Label htmlFor={id} className="text-sm font-medium">
          {label}
        </Label>
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
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
        <ComboboxInput
          id={id}
          aria-describedby={`${id}-hint`}
          placeholder={modelName(models, value)}
          className="w-full"
        />
        <ComboboxContent className="w-(--anchor-width) min-w-(--anchor-width)">
          <ComboboxEmpty>No models match.</ComboboxEmpty>
          <ComboboxList>
            {(model: OpenRouterModel) => (
              <ComboboxItem key={model.id} value={model}>
                <span className="min-w-0 flex-1 truncate">{model.name}</span>
                {model.id.includes('/') ? (
                  <span className="shrink-0 text-xs text-muted-foreground">{model.id.split('/')[0]}</span>
                ) : null}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

function SettingsSection({ title, children }: { title: string; children: ReactNode }): React.JSX.Element {
  return (
    <section className="flex flex-col gap-3 border-t pt-5">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </section>
  )
}

export function SettingsDialog({
  open,
  onOpenChange,
  apiKey,
  onApiKeyChange,
  status,
  provider,
  onProviderChange,
  models,
  onModelsChange,
  maxIterations,
  onMaxIterationsChange,
  searchEngine,
  onSearchEngineChange,
  tavilyKey,
  onTavilyKeyChange,
  writingTone,
  onWritingToneChange,
  catalog,
  catalogLoaded = true,
  catalogError,
  embeddingCatalog,
  embeddingCatalogError
}: ResearchOptionsProps & {
  open: boolean
  onOpenChange: (open: boolean) => void
}): React.JSX.Element {
  const [needsTavilyKey, setNeedsTavilyKey] = useState(false)
  const tavilyRef = useRef<HTMLInputElement>(null)
  const plannerModels = useMemo(() => {
    const source = provider === 'ollama' ? catalog.filter((model) => model.tools) : catalog
    return choicesFor(source, models.planner, provider !== 'ollama')
  }, [catalog, models.planner, provider])
  const extractorModels = useMemo(() => {
    const source = provider === 'ollama' ? catalog.filter((model) => model.tools) : catalog
    return choicesFor(source, models.extractor, provider !== 'ollama')
  }, [catalog, models.extractor, provider])
  const writerModels = useMemo(() => {
    const source = provider === 'ollama' ? catalog.filter((model) => !model.embedding) : catalog
    return choicesFor(source, models.writer, false)
  }, [catalog, models.writer, provider])
  const embeddingModels = useMemo(() => {
    const source = provider === 'ollama' ? catalog.filter((model) => model.embedding) : embeddingCatalog
    return choicesFor(source, models.embedding, false)
  }, [catalog, embeddingCatalog, models.embedding, provider])
  const ollamaToolCount = provider === 'ollama' ? catalog.filter((model) => model.tools).length : 0
  const ollamaEmbedCount = provider === 'ollama' ? catalog.filter((model) => model.embedding).length : 0
  const ollamaNotice =
    provider !== 'ollama' || catalogError || !catalogLoaded
      ? null
      : catalog.length === 0
        ? 'No Ollama models are installed.'
        : ollamaToolCount === 0
          ? 'None of the installed models can call tools. Planner and extractor need one.'
          : ollamaEmbedCount === 0
            ? 'No embedding model is installed, so PDFs are skipped.'
            : null

  function chooseSearch(value: string): void {
    if (value === 'duckduckgo') {
      setNeedsTavilyKey(false)
      onSearchEngineChange('duckduckgo')
      return
    }
    if (value !== 'tavily') return
    if (hasTavilyKey(tavilyKey)) {
      setNeedsTavilyKey(false)
      onSearchEngineChange('tavily')
      return
    }
    setNeedsTavilyKey(true)
    tavilyRef.current?.focus()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[min(40rem,calc(100%-2rem))] gap-5 overflow-y-auto p-6 sm:max-w-lg">
        <DialogHeader className="pr-8">
          <DialogTitle>
            <SettingsIcon />
          </DialogTitle>
          <DialogDescription>Keys, search, and the models used for the next report.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <h3 className="text-sm font-medium">Keys</h3>
          <ApiKeyField apiKey={apiKey} onApiKeyChange={onApiKeyChange} status={status} />
          <TavilyKeyField
            id="tavily-key-settings"
            value={tavilyKey}
            attention={needsTavilyKey && !hasTavilyKey(tavilyKey)}
            inputRef={tavilyRef}
            onChange={onTavilyKeyChange}
            onCommit={(next) => {
              if (hasTavilyKey(next)) setNeedsTavilyKey(false)
              if (!hasTavilyKey(next) && searchEngine === 'tavily') onSearchEngineChange('duckduckgo')
            }}
          />
        </div>
        <SettingsSection title="Search">
          <RadioGroup value={searchEngine} onValueChange={chooseSearch} aria-label="Search" className="gap-2">
            <SearchChoice
              group="search"
              value="duckduckgo"
              title="DuckDuckGo"
              detail="Searches without an extra key."
              selected={searchEngine === 'duckduckgo'}
              onSelect={chooseSearch}
            />
            <SearchChoice
              group="search"
              value="tavily"
              title="Tavily"
              detail="Uses the Tavily key above."
              selected={searchEngine === 'tavily'}
              onSelect={chooseSearch}
            />
          </RadioGroup>
        </SettingsSection>
        <SettingsSection title="Follow-up searches">
          <div className="flex items-center justify-between gap-4">
            <p id="follow-up-hint" className="text-sm text-muted-foreground">
              When a question is still open, search again up to {maxIterations} {maxIterations === 1 ? 'time' : 'times'}
              .
            </p>
            <div className="flex shrink-0 items-center gap-1" role="group" aria-labelledby="follow-up-hint">
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Fewer follow-up searches"
                disabled={maxIterations <= 1}
                onClick={() => onMaxIterationsChange(maxIterations - 1)}
              >
                <Minus />
              </Button>
              <span className="w-6 text-center text-sm tabular-nums" aria-live="polite">
                {maxIterations}
              </span>
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="More follow-up searches"
                disabled={maxIterations >= 10}
                onClick={() => onMaxIterationsChange(maxIterations + 1)}
              >
                <Plus />
              </Button>
            </div>
          </div>
        </SettingsSection>
        <SettingsSection title="Writing style">
          <RadioGroup
            value={writingTone}
            onValueChange={(value) => {
              if (value === 'clear' || value === 'academic') onWritingToneChange(value)
            }}
            aria-label="Writing style"
            className="gap-2"
          >
            <SearchChoice
              group="writing-tone"
              value="clear"
              title="Clear"
              detail="Direct, accessible prose with technical terms explained."
              selected={writingTone === 'clear'}
              onSelect={() => onWritingToneChange('clear')}
            />
            <SearchChoice
              group="writing-tone"
              value="academic"
              title="Academic"
              detail="Formal scholarly prose for a specialist reader."
              selected={writingTone === 'academic'}
              onSelect={() => onWritingToneChange('academic')}
            />
          </RadioGroup>
        </SettingsSection>
        <SettingsSection title="Models">
          <RadioGroup
            value={provider}
            onValueChange={(value) => {
              if (value === 'openrouter' || value === 'ollama') onProviderChange(value)
            }}
            aria-label="Model source"
            className="gap-2"
          >
            <SearchChoice
              group="provider"
              value="openrouter"
              title="OpenRouter"
              detail="Uses the key above."
              selected={provider === 'openrouter'}
              onSelect={(value) => onProviderChange(value === 'ollama' ? 'ollama' : 'openrouter')}
            />
            <SearchChoice
              group="provider"
              value="ollama"
              title="Ollama"
              detail="Uses models installed on this computer."
              selected={provider === 'ollama'}
              onSelect={(value) => onProviderChange(value === 'ollama' ? 'ollama' : 'openrouter')}
            />
          </RadioGroup>
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
          <ModelField
            id="embedding-model"
            label="Embedding"
            hint="Ranks pages inside PDFs. Without one, PDFs are skipped."
            models={embeddingModels}
            value={models.embedding}
            onChange={(embedding) => onModelsChange({ ...models, embedding })}
          />
          {catalogError ? <p className="text-sm text-destructive">{catalogError}</p> : null}
          {ollamaNotice ? <p className="text-sm text-muted-foreground">{ollamaNotice}</p> : null}
          {provider === 'openrouter' && embeddingCatalogError ? (
            <p className="text-sm text-destructive">{embeddingCatalogError}</p>
          ) : null}
        </SettingsSection>
      </DialogContent>
    </Dialog>
  )
}

function SearchChoice({
  group,
  value,
  title,
  detail,
  selected,
  onSelect
}: {
  group: string
  value: string
  title: string
  detail: string
  selected: boolean
  onSelect: (value: string) => void
}): React.JSX.Element {
  return (
    <div
      className={cn(
        'flex cursor-pointer items-center gap-3 rounded-lg border p-3',
        selected ? 'border-primary bg-accent/70' : 'hover:bg-muted'
      )}
      onClick={() => onSelect(value)}
    >
      <RadioGroupItem
        id={`${group}-${value}`}
        value={value}
        aria-label={title}
        aria-describedby={`${group}-${value}-detail`}
      />
      <span>
        <span className="block text-sm">{title}</span>
        <span id={`${group}-${value}-detail`} className="mt-0.5 block text-sm text-muted-foreground">
          {detail}
        </span>
      </span>
    </div>
  )
}
