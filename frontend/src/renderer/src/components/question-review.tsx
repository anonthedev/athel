import { useLayoutEffect, useRef, type KeyboardEvent } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Textarea } from '@/components/ui/textarea'
import type { DraftQuestion } from '@/components/research-trace'

const questionLimit = 7
const submitHint = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl'

type QuestionReviewProps = {
  topic: string
  questions: DraftQuestion[]
  error: string | null
  onChange: (questions: DraftQuestion[]) => void
  onContinue: () => void
  onAbort: () => void
}

export function QuestionReview({
  topic,
  questions,
  error,
  onChange,
  onContinue,
  onAbort
}: QuestionReviewProps): React.JSX.Element {
  const fields = useRef<Array<HTMLTextAreaElement | null>>([])
  const focusIndex = useRef<number | null>(null)
  const ready = questions.map((question) => question.text.trim()).filter(Boolean)

  useLayoutEffect(() => {
    const index = focusIndex.current
    if (index === null) return
    focusIndex.current = null
    const field = fields.current[index]
    if (!field) return
    field.focus()
    const end = field.value.length
    field.setSelectionRange(end, end)
  }, [questions])

  function add(): void {
    if (questions.length >= questionLimit) return
    focusIndex.current = questions.length
    onChange([...questions, { id: crypto.randomUUID(), text: '' }])
  }

  function remove(index: number): void {
    const next = questions.filter((_, item) => item !== index)
    focusIndex.current = next.length === 0 ? null : Math.max(0, index - 1)
    onChange(next)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== 'Enter' || (!event.metaKey && !event.ctrlKey)) return
    event.preventDefault()
    if (ready.length > 0) onContinue()
  }

  function onFieldKeyDown(event: KeyboardEvent<HTMLTextAreaElement>, index: number): void {
    if (event.key === 'Enter' && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
      event.preventDefault()
      if (index < questions.length - 1) {
        fields.current[index + 1]?.focus()
        return
      }
      add()
      return
    }
    if (event.key === 'Backspace' && questions[index]?.text === '' && questions.length > 1) {
      event.preventDefault()
      remove(index)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col" onKeyDown={onKeyDown}>
      <header className="flex items-center gap-3 border-b px-8 py-4">
        <h2 className="min-w-0 truncate text-base font-medium">{topic}</h2>
        <span className="shrink-0 text-xs text-muted-foreground">Review questions</span>
        <Button type="button" variant="destructive" size="sm" className="ml-auto cursor-pointer" onClick={onAbort}>
          Abort
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-8 py-10">
          <div className="flex flex-col gap-2">
            <h3 className="text-2xl font-medium tracking-tight">Questions for this report</h3>
            <p className="text-sm text-muted-foreground">
              Change any question, then start the search.
            </p>
          </div>
          <ol className="flex flex-col gap-1">
            {questions.map((question, index) => (
              <li key={question.id} className="group flex items-start gap-3">
                <span className="w-6 shrink-0 pt-2 text-right text-sm text-muted-foreground tabular-nums">
                  {index + 1}
                </span>
                <Textarea
                  ref={(node) => {
                    fields.current[index] = node
                  }}
                  aria-label={`Question ${index + 1}`}
                  value={question.text}
                  rows={1}
                  placeholder="A question the report should answer"
                  className="min-h-10 flex-1 resize-none border-transparent bg-transparent px-2 py-1.5 text-base leading-7 shadow-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 md:text-base dark:bg-transparent"
                  onChange={(event) =>
                    onChange(
                      questions.map((item) =>
                        item.id === question.id ? { ...item, text: event.target.value } : item
                      )
                    )
                  }
                  onKeyDown={(event) => onFieldKeyDown(event, index)}
                />
                <button
                  type="button"
                  aria-label={`Remove question ${index + 1}`}
                  className="mt-1.5 flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground opacity-0 pointer-events-none group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 focus-visible:opacity-100 hover:bg-muted hover:text-foreground"
                  onClick={() => remove(index)}
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ol>
          {questions.length < questionLimit ? (
            <Button type="button" variant="ghost" className="self-start text-muted-foreground" onClick={add}>
              <Plus />
              Add a question
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">Seven questions is the limit.</p>
          )}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
      </div>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 px-8 py-3">
          <p className="text-xs text-muted-foreground">
            {ready.length === 0
              ? 'Add at least one question'
              : `${ready.length} ${ready.length === 1 ? 'question' : 'questions'}`}
          </p>
          <div className="flex items-center gap-3">
            <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Kbd className="border border-border bg-transparent dark:bg-transparent">{submitHint}</Kbd>
              <Kbd className="border border-border bg-transparent dark:bg-transparent">Enter</Kbd>
            </p>
            <Button
              type="button"
              className="disabled:bg-transparent disabled:text-muted-foreground disabled:opacity-100 dark:disabled:bg-transparent"
              disabled={ready.length === 0}
              onClick={onContinue}
            >
              Start research
            </Button>
          </div>
        </div>
      </footer>
    </div>
  )
}
