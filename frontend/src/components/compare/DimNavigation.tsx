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
  activeId: string
  onSelect: (id: string) => void
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

export function DimNavigation({ dims, steps, activeId, onSelect }: DimNavigationProps) {
  if (!dims.length && (!steps || !steps.length)) return null

  if (steps && steps.length) {
    return (
      <nav className="dim-nav">
        <button
          className={`dim-pill${activeId === 'all' ? ' active' : ''}`}
          onClick={() => onSelect('all')}
        >
          全部
        </button>
        {steps.map((s) => (
          <button
            key={s.stepKey}
            className={`dim-pill${activeId === s.stepKey ? ' active' : ''}`}
            onClick={() => onSelect(s.stepKey)}
          >
            {s.shortLabel}
            <span className="dim-pill-count">{s.dims.length}</span>
          </button>
        ))}
      </nav>
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
