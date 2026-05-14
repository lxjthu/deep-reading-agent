import { useState, useMemo } from 'react'
import { useCompareData } from '../hooks/useCompareData'
import { PaperSelector } from './compare/PaperSelector'
import { DimNavigation, getShortLabel } from './compare/DimNavigation'
import type { StepGroup } from './compare/DimNavigation'
import { AccordionPanel } from './compare/AccordionPanel'
import { SynthesisModal } from './compare/SynthesisModal'
import './compare/compare.css'

interface DimItem {
  id: string
  label: string
  group_name?: string
}

interface Paper {
  id: string
  title: string
  authors: string[]
  year: number | null
  dimensions?: Array<{ id: string; label: string; content: string; group_name?: string }>
  steps?: Record<string, { label: string; subQuestions: Array<{ id: string; label: string; content: string }> }>
}

interface CompareViewProps {
  mode: 'long' | 'quant' | 'qual'
  apiKey: string | null
}

const MODE_LABELS: Record<string, { title: string; subtitle: string }> = {
  long: { title: '对比分析 · 长文本精读', subtitle: '选择文献与维度，横向对比长文本精读结果' },
  quant: { title: '对比分析 · 七步精读', subtitle: '选择文献与子问题，横向对比七步精读结果' },
  qual: { title: '对比分析 · 四步精读', subtitle: '选择文献与子问题，横向对比四步精读结果' },
}

function getAvailableDims(papers: Paper[], selectedIds: Set<string>): DimItem[] {
  const map = new Map<string, DimItem>()
  papers
    .filter((p) => selectedIds.has(p.id))
    .forEach((p) => {
      ;(p.dimensions || []).forEach((d) => {
        if (!map.has(d.id)) map.set(d.id, { id: d.id, label: d.label, group_name: d.group_name })
      })
    })
  return Array.from(map.values())
}

function getAvailableDimsFromSteps(papers: Paper[], selectedIds: Set<string>): DimItem[] {
  const map = new Map<string, DimItem>()
  papers
    .filter((p) => selectedIds.has(p.id))
    .forEach((p) => {
      Object.values(p.steps || {}).forEach((step) => {
        ;(step.subQuestions || []).forEach((sq) => {
          if (!map.has(sq.id)) map.set(sq.id, { id: sq.id, label: sq.label })
        })
      })
    })
  return Array.from(map.values())
}

export function CompareView({ mode, apiKey }: CompareViewProps) {
  const { papers, loading, error } = useCompareData(mode)

  const [selectedPaperIds, setSelectedPaperIds] = useState<Set<string>>(new Set())
  const [activePill, setActivePill] = useState<string>('all')
  const [selectedDimIds, setSelectedDimIds] = useState<Set<string>>(new Set())
  const [dimStates, setDimStates] = useState<Record<string, 'collapsed' | 'preview' | 'full'>>({})
  const [showSynthesis, setShowSynthesis] = useState(false)

  const availableDims = useMemo(() => {
    if (mode === 'long') return getAvailableDims(papers, selectedPaperIds)
    return getAvailableDimsFromSteps(papers, selectedPaperIds)
  }, [mode, papers, selectedPaperIds])

  const stepGroups = useMemo<StepGroup[]>(() => {
    if (mode === 'long') {
      const groupMap = new Map<string, StepGroup>()
      const ungrouped: DimItem[] = []
      availableDims.forEach((d) => {
        if (d.group_name) {
          if (!groupMap.has(d.group_name)) {
            groupMap.set(d.group_name, {
              stepKey: d.group_name,
              stepLabel: d.group_name,
              shortLabel: d.group_name,
              dims: [],
            })
          }
          groupMap.get(d.group_name)!.dims.push(d)
        } else {
          ungrouped.push(d)
        }
      })
      const groups = Array.from(groupMap.values())
      if (ungrouped.length) {
        groups.push({
          stepKey: '__ungrouped__',
          stepLabel: '其他',
          shortLabel: '其他',
          dims: ungrouped,
        })
      }
      return groups
    }

    const stepMap = new Map<string, StepGroup>()
    papers
      .filter((p) => selectedPaperIds.has(p.id))
      .forEach((p) => {
        Object.entries(p.steps || {}).forEach(([key, step]) => {
          if (!stepMap.has(key)) {
            stepMap.set(key, {
              stepKey: key,
              stepLabel: step.label || key,
              shortLabel: getShortLabel(key),
              dims: [],
            })
          }
          const group = stepMap.get(key)!
          ;(step.subQuestions || []).forEach((sq) => {
            if (!group.dims.some((d) => d.id === sq.id)) {
              group.dims.push({ id: sq.id, label: sq.label })
            }
          })
        })
      })
    return Array.from(stepMap.values())
  }, [mode, papers, selectedPaperIds, availableDims])

  const selectedPapers = useMemo(
    () => papers.filter((p) => selectedPaperIds.has(p.id)),
    [papers, selectedPaperIds],
  )

  const visibleDims = useMemo(() => {
    if (activePill === 'all') return availableDims
    const group = stepGroups.find((g) => g.stepKey === activePill)
    if (group) return group.dims
    return availableDims.filter((d) => d.id === activePill)
  }, [activePill, availableDims, stepGroups])

  const cleanedDimStates = useMemo(() => {
    const dimIdSet = new Set(availableDims.map((d) => d.id))
    const next: Record<string, 'collapsed' | 'preview' | 'full'> = {}
    for (const [k, v] of Object.entries(dimStates)) {
      if (dimIdSet.has(k)) next[k] = v
    }
    return next
  }, [availableDims, dimStates])

  const togglePaper = (id: string) => {
    setSelectedPaperIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    setDimStates({})
    setSelectedDimIds(new Set())
    setActivePill('all')
  }

  const selectPill = (id: string) => setActivePill(id)

  const toggleAccordion = (dimId: string) => {
    setDimStates((prev) => {
      const cur = prev[dimId] || 'collapsed'
      return { ...prev, [dimId]: cur === 'collapsed' ? 'preview' : 'collapsed' }
    })
  }

  const expandFull = (dimId: string) => {
    setDimStates((prev) => ({ ...prev, [dimId]: 'full' }))
  }

  const collapseToPreview = (dimId: string) => {
    setDimStates((prev) => ({ ...prev, [dimId]: 'preview' }))
  }

  const toggleSelectDim = (dimId: string) => {
    setSelectedDimIds((prev) => {
      const next = new Set(prev)
      if (next.has(dimId)) next.delete(dimId)
      else next.add(dimId)
      return next
    })
  }

  const handleSelectAll = () => {
    setSelectedDimIds(new Set(visibleDims.map((d) => d.id)))
  }

  const handleClear = () => {
    setSelectedDimIds(new Set())
  }

  const handleSynthesis = () => {
    if (selectedPaperIds.size >= 2 && selectedDimIds.size >= 1 && apiKey) {
      setShowSynthesis(true)
    }
  }

  const canSynth = selectedPaperIds.size >= 2 && selectedDimIds.size >= 1 && !!apiKey

  const { title, subtitle } = MODE_LABELS[mode] || MODE_LABELS.long

  if (loading) {
    return (
      <div className="compare-root">
      <div className="page-wrapper">
        <div className="loading-state">
          <div className="spinner" />
          <span>加载中...</span>
        </div>
      </div>
    </div>
    )
  }

  if (error) {
    return (
    <div className="compare-root">
      <div className="page-wrapper">
        <div className="error-state">加载失败: {error}</div>
      </div>
    </div>
    )
  }

  if (!papers.length) {
    return (
    <div className="compare-root">
      <div className="page-wrapper">
        <div className="empty-state">暂无论文数据，请先完成精读</div>
      </div>
    </div>
    )
  }

  return (
    <div className="compare-root">
      <div className="page-wrapper">
      <header className="page-header">
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </header>

      <PaperSelector papers={papers} selectedIds={selectedPaperIds} onToggle={togglePaper} />

      {selectedPaperIds.size > 0 && (
        <DimNavigation
          dims={availableDims}
          steps={stepGroups}
          activeId={activePill}
          onSelect={selectPill}
        />
      )}

      {selectedPaperIds.size > 0 && (
        <div className="action-bar">
          <span className="action-badge">已选 {selectedDimIds.size} / {availableDims.length} 个维度</span>
          <button className="btn btn-outline btn-sm" onClick={handleSelectAll}>全选</button>
          <button className="btn btn-outline btn-sm" onClick={handleClear}>清除</button>
          <button
            className="btn btn-primary btn-sm"
            disabled={!canSynth}
            onClick={handleSynthesis}
          >
            AI 综述
          </button>
        </div>
      )}

      <section className="accordion-section">
        {selectedPaperIds.size === 0 ? (
          <div className="empty-state">请先选择文献开始对比</div>
        ) : (
          visibleDims.map((dim) => (
            <AccordionPanel
              key={dim.id}
              dimId={dim.id}
              dimLabel={dim.label}
              papers={selectedPapers}
              state={cleanedDimStates[dim.id] || 'collapsed'}
              selected={selectedDimIds.has(dim.id)}
              onToggleSelect={toggleSelectDim}
              onToggleExpand={toggleAccordion}
              onExpandFull={expandFull}
              onCollapseToPreview={collapseToPreview}
              mode={mode}
            />
          ))
        )}
      </section>

      <SynthesisModal
        open={showSynthesis}
        onClose={() => setShowSynthesis(false)}
        mode={mode}
        bibEntryIds={Array.from(selectedPaperIds)}
        selectedDimIds={Array.from(selectedDimIds)}
        apiKey={apiKey}
      />
      </div>
    </div>
  )
}
