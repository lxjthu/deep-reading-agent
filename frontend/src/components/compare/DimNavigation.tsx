interface DimItem {
  id: string
  label: string
}

interface DimNavigationProps {
  dims: DimItem[]
  activeId: string
  onSelect: (id: string) => void
}

export function DimNavigation({ dims, activeId, onSelect }: DimNavigationProps) {
  if (!dims.length) return null

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
