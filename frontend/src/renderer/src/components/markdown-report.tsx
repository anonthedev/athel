import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'

export function ExternalLink({
  href,
  children
}: {
  href?: string
  children?: ReactNode
}): React.JSX.Element {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
      {children}
    </a>
  )
}

export function MarkdownReport({ markdown }: { markdown: string }): React.JSX.Element {
  return (
    <article className="markdown reading-column px-8 py-10">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => <ExternalLink href={href}>{children}</ExternalLink>
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  )
}
