import { useMemo } from 'react'

interface PaperSelectorProps {
  papers: Array<{
    id: string
    title: string
    authors: string[]
    year: number | null
    journal?: string
    dimensions?: Array<{ id: string; label: string; content: string; dim_set_name?: string }>
    steps?: Record<string, { label: string; subQuestions: Array<{ id: string; label: string; content: string }> }>
  }>
  selectedIds: Set<string>
  onToggle: (id: string) => void
  mode: 'long' | 'quant' | 'qual'
  allPapers: this['papers']
  filterDimSet: string
  filterJournal: string
  filterSearch: string
  onFilterDimSet: (v: string) => void
  onFilterJournal: (v: string) => void
  onFilterSearch: (v: string) => void
}

export function PaperSelector({
  papers,
  selectedIds,
  onToggle,
  mode,
  allPapers,
  filterDimSet,
  filterJournal,
  filterSearch,
  onFilterDimSet,
  onFilterJournal,
  onFilterSearch,
}: PaperSelectorProps) {
  const dimSetOptions = useMemo(() => {
    const s = new Set<string>()
    allPapers.forEach((p) =>
      (p.dimensions || []).forEach((d) => {
        if (d.dim_set_name) s.add(d.dim_set_name)
      }),
    )
    return Array.from(s).sort()
  }, [allPapers])

  const journalOptions = useMemo(() => {
    const s = new Set<string>()
    allPapers.forEach((p) => {
      const j = (p.journal || '').trim()
      s.add(j || '(未填写)')
    })
    return Array.from(s).sort()
  }, [allPapers])

  const hasFilters = filterDimSet || filterJournal || filterSearch.trim()

  const resetFilters = () => {
    onFilterDimSet('')
    onFilterJournal('')
    onFilterSearch('')
  }

  return (
    <section className="paper-bar">
      <div className="paper-bar-label">选择文献</div>

      <div className="compare-filter-bar">
        {mode === 'long' && dimSetOptions.length > 1 && (
          <select
            className="compare-filter-select"
            value={filterDimSet}
            onChange={(e) => onFilterDimSet(e.target.value)}
          >
            <option value="">全部维度集合</option>
            {dimSetOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        )}
        {journalOptions.length > 1 && (
          <select
            className="compare-filter-select"
            value={filterJournal}
            onChange={(e) => onFilterJournal(e.target.value)}
          >
            <option value="">全部期刊</option>
            {journalOptions.map((j) => (
              <option key={j} value={j}>{j}</option>
            ))}
          </select>
        )}
        <input
          type="text"
          className="compare-filter-input"
          placeholder="搜索文献名..."
          value={filterSearch}
          onChange={(e) => onFilterSearch(e.target.value)}
        />
        {hasFilters && (
          <button className="compare-filter-reset" onClick={resetFilters}>
            重置
          </button>
        )}
        <span className="compare-filter-count">
          {papers.length} 篇{allPapers.length !== papers.length ? ` / ${allPapers.length}` : ''}
        </span>
      </div>

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
        {papers.length === 0 && (
          <div className="paper-card-empty">无匹配文献</div>
        )}
      </div>
    </section>
  )
}
