import { useRef, useEffect } from 'react'
import { marked } from 'marked'

function md2html(raw: string): string {
  let h = marked.parse(raw || '', { async: false }) as string
  h = h.replace(/<table>/g, '<div class="table-wrapper"><table>')
  h = h.replace(/<\/table>/g, '</table></div>')
  return h
}

function mathRender(el: HTMLElement) {
  if (typeof (window as any).renderMathInElement === 'function') {
    ;(window as any).renderMathInElement(el, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\(', right: '\\)', display: false },
        { left: '\\[', right: '\\]', display: true },
      ],
    })
  }
}

function formatAuthors(authors: string[], year: number | null): string {
  const auth = (authors || []).slice(0, 3).join(', ')
  const yr = year ? ` (${year})` : ''
  return auth + yr
}

interface AnswerCardProps {
  paper: {
    id: string
    title: string
    authors: string[]
    year: number | null
  }
  content: string | null
  variant: 'preview' | 'full'
}

export function AnswerCard({ paper, content, variant }: AnswerCardProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const hasContent = content && content.trim()

  useEffect(() => {
    if (contentRef.current && hasContent) {
      mathRender(contentRef.current)
    }
  }, [hasContent, content])

  const meta = formatAuthors(paper.authors, paper.year)
  const titleText = paper.title || '未命名文献'

  if (variant === 'preview') {
    return (
      <div className="preview-card">
        <div className="preview-card-header">
          <div className="preview-card-title">{titleText}</div>
          <div className="preview-card-meta">{meta}</div>
        </div>
        {hasContent ? (
          <div
            ref={contentRef}
            className="preview-card-content md-content"
            dangerouslySetInnerHTML={{ __html: md2html(content!) }}
          />
        ) : (
          <div
            className="preview-card-content"
            style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center' }}
          >
            （未包含此维度）
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="answer-card">
      <div className="answer-card-header">
        <div className="answer-card-title">{titleText}</div>
        <div className="answer-card-meta">{meta}</div>
      </div>
      {hasContent ? (
        <div
          ref={contentRef}
          className="answer-card-content md-content"
          dangerouslySetInnerHTML={{ __html: md2html(content!) }}
        />
      ) : (
        <div className="answer-card-empty">（未包含此维度）</div>
      )}
    </div>
  )
}
