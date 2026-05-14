import { AnswerCard } from './AnswerCard'

function getDimContent(
  paper: {
    dimensions?: Array<{ id: string; label: string; content: string }>
    steps?: Record<string, { label: string; subQuestions: Array<{ id: string; label: string; content: string }> }>
  },
  dimId: string,
  mode: 'long' | 'quant' | 'qual'
): string | null {
  if (mode === 'long') {
    const dim = (paper.dimensions || []).find((d) => d.id === dimId)
    return dim?.content || null
  }
  for (const step of Object.values(paper.steps || {})) {
    for (const sq of step.subQuestions || []) {
      if (sq.id === dimId) return sq.content || null
    }
  }
  return null
}

interface AccordionPanelProps {
  dimId: string
  dimLabel: string
  papers: Array<{
    id: string
    title: string
    authors: string[]
    year: number | null
    dimensions?: Array<{ id: string; label: string; content: string }>
    steps?: Record<string, { label: string; subQuestions: Array<{ id: string; label: string; content: string }> }>
  }>
  state: 'collapsed' | 'preview' | 'full'
  selected: boolean
  onToggleSelect: (dimId: string) => void
  onToggleExpand: (dimId: string) => void
  onExpandFull: (dimId: string) => void
  onCollapseToPreview: (dimId: string) => void
  mode: 'long' | 'quant' | 'qual'
}

export function AccordionPanel({
  dimId,
  dimLabel,
  papers,
  state,
  selected,
  onToggleSelect,
  onToggleExpand,
  onExpandFull,
  onCollapseToPreview,
  mode,
}: AccordionPanelProps) {
  const isExpanded = state !== 'collapsed'

  return (
    <div className={`accordion-item${isExpanded ? ' expanded' : ''}`} data-dim-id={dimId}>
      <div
        className="accordion-header"
        onClick={(e) => {
          if ((e.target as HTMLInputElement).type === 'checkbox') return
          onToggleExpand(dimId)
        }}
      >
        <input
          type="checkbox"
          className="accordion-checkbox"
          checked={selected}
          onClick={(e) => {
            e.stopPropagation()
            onToggleSelect(dimId)
          }}
          readOnly
        />
        <span className="accordion-label">{dimLabel}</span>
        <span className="accordion-arrow">▼</span>
      </div>

      {isExpanded && (
        <div className="accordion-body" style={{ maxHeight: 'none' }}>
          {state === 'preview' && (
            <div className="accordion-preview">
              <div className="preview-cards-scroll">
                {papers.map((p) => (
                  <AnswerCard
                    key={p.id}
                    paper={p}
                    content={getDimContent(p, dimId, mode)}
                    variant="preview"
                  />
                ))}
              </div>
              <div className="expand-divider">
                <span className="expand-btn" onClick={(e) => { e.stopPropagation(); onExpandFull(dimId) }}>
                  展开详细对比
                </span>
              </div>
            </div>
          )}
          {state === 'full' && (
            <div className="accordion-full-content">
              <div className="answer-cards-scroll">
                {papers.map((p) => (
                  <AnswerCard
                    key={p.id}
                    paper={p}
                    content={getDimContent(p, dimId, mode)}
                    variant="full"
                  />
                ))}
              </div>
              <div className="collapse-full">
                <span className="collapse-full-btn" onClick={(e) => { e.stopPropagation(); onCollapseToPreview(dimId) }}>
                  收起详细对比
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
