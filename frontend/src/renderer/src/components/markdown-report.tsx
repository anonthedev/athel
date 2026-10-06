import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const remarkPlugins = [remarkGfm]

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
        remarkPlugins={remarkPlugins}
        components={{
          a: ({ href, children }) => <ExternalLink href={href}>{children}</ExternalLink>,
          table: ({ children }) => (
            <div className="markdown-table">
              <table>{children}</table>
            </div>
          )
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  )
}
