interface PaperSelectorProps {
  papers: Array<{
    id: string
    title: string
    authors: string[]
    year: number | null
    dimensions?: Array<{ id: string; label: string; content: string }>
    steps?: Record<string, { label: string; subQuestions: Array<{ id: string; label: string; content: string }> }>
  }>
  selectedIds: Set<string>
  onToggle: (id: string) => void
}

export function PaperSelector({ papers, selectedIds, onToggle }: PaperSelectorProps) {
  return (
    <section className="paper-bar">
      <div className="paper-bar-label">选择文献</div>
      <div className="paper-cards">
        {papers.map((p) => {
          const sel = selectedIds.has(p.id)
          const auth = (p.authors || []).slice(0, 3).join(', ')
          const yr = p.year ? ` (${p.year})` : ''
          const dc = p.dimensions ? p.dimensions.length : 0
          return (
            <div
              key={p.id}
              className={`paper-card${sel ? ' selected' : ''}`}
              onClick={() => onToggle(p.id)}
            >
              <div className="paper-card-title">{p.title || '未命名文献'}</div>
              <div className="paper-card-meta">
                {auth}{yr}
              </div>
              {dc > 0 && <span className="paper-card-dims">{dc} 个维度</span>}
            </div>
          )
        })}
      </div>
    </section>
  )
}
