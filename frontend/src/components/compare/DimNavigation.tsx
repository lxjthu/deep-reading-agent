interface DimItem {
  id: string
  label: string
}

interface StepGroup {
  stepKey: string
  stepLabel: string
  shortLabel: string
  dims: DimItem[]
}

interface DimNavigationProps {
  dims: DimItem[]
  steps?: StepGroup[]
  mode: 'long' | 'quant' | 'qual'
  activeId: string
  onSelect: (id: string) => void
  expandedStep: string | null
  onExpandStep: (stepKey: string | null) => void
}

function getShortLabel(stepKey: string): string {
  const m = stepKey.match(/第([一二三四五六七])步/)
  if (!m) return stepKey
  const map: Record<string, string> = {
    '一': '①', '二': '②', '三': '③', '四': '④',
    '五': '⑤', '六': '⑥', '七': '⑦',
  }
  const rest = stepKey.replace(/^[：:　\s]*第[一二三四五六七]步[：:　\s]*/, '').replace(/[：:　\s]*$/, '')
  return `${map[m[1]] || m[1]} ${rest}`
}

export function DimNavigation({ dims, steps, mode, activeId, onSelect, expandedStep, onExpandStep }: DimNavigationProps) {
  if (!dims.length && (!steps || !steps.length)) return null

  if (mode !== 'long' && steps && steps.length) {
    return (
      <div className="dim-nav-container">
        <nav className="dim-nav">
          <button
            className={`dim-pill${activeId === 'all' ? ' active' : ''}`}
            onClick={() => { onSelect('all'); onExpandStep(null) }}
          >
            全部
          </button>
          {steps.map((s) => {
            const isExpanded = expandedStep === s.stepKey
            const isActive = !isExpanded && activeId !== 'all' && s.dims.some((d) => d.id === activeId)
            return (
              <div key={s.stepKey} className="dim-pill-group">
                <button
                  className={`dim-pill${isActive ? ' active' : ''}${isExpanded ? ' expanded' : ''}`}
                  onClick={() => onExpandStep(isExpanded ? null : s.stepKey)}
                >
                  {s.shortLabel}
                  <span className="dim-pill-arrow">{isExpanded ? '▲' : '▼'}</span>
                </button>
                {isExpanded && (
                  <div className="dim-sub-pills">
                    {s.dims.map((d) => (
                      <button
                        key={d.id}
                        className={`dim-pill dim-sub-pill${activeId === d.id ? ' active' : ''}`}
                        onClick={() => onSelect(d.id)}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </nav>
      </div>
    )
  }

  return (
    <nav className="dim-nav">
      <button
        className={`dim-pill${activeId === 'all' ? ' active' : ''}`}
        onClick={() => onSelect('all')}
      >
        全部
      </button>
      {dims.map((d) => (
        <button
          key={d.id}
          className={`dim-pill${activeId === d.id ? ' active' : ''}`}
          onClick={() => onSelect(d.id)}
        >
          {d.label}
        </button>
      ))}
    </nav>
  )
}

export type { DimItem, StepGroup }
export { getShortLabel }
