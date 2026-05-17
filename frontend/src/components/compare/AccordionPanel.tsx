import { useState, useCallback } from 'react'
import { AnswerCard } from './AnswerCard'
import type { CardMode } from './AnswerCard'

function getDimData(
  paper: {
    dimensions?: Array<{
      id: string
      label: string
      content: string
      reading_item_id?: number
      edit?: { edited_content: string; updated_at: string | null }
      annotations?: Array<any>
      dim_set_name?: string
    }>
    steps?: Record<
      string,
      {
        label: string
        subQuestions: Array<{
          id: string
          label: string
          content: string
          reading_item_id?: number
          edit?: { edited_content: string; updated_at: string | null }
          annotations?: Array<any>
        }>
      }
    >
  },
  dimId: string,
  mode: 'long' | 'quant' | 'qual',
) {
  if (mode === 'long') {
    const dim = (paper.dimensions || []).find((d) => d.id === dimId)
    return dim || null
  }
  for (const step of Object.values(paper.steps || {})) {
    for (const sq of step.subQuestions || []) {
      if (sq.id === dimId) return sq
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
    dimensions?: Array<{
      id: string
      label: string
      content: string
      reading_item_id?: number
      edit?: { edited_content: string; updated_at: string | null }
      annotations?: Array<any>
      dim_set_name?: string
    }>
    steps?: Record<
      string,
      {
        label: string
        subQuestions: Array<{
          id: string
          label: string
          content: string
          reading_item_id?: number
          edit?: { edited_content: string; updated_at: string | null }
          annotations?: Array<any>
        }>
      }
    >
  }>
  state: 'collapsed' | 'preview' | 'full'
  selected: boolean
  onToggleSelect: (dimId: string) => void
  onToggleExpand: (dimId: string) => void
  onExpandFull: (dimId: string) => void
  onCollapseToPreview: (dimId: string) => void
  mode: 'long' | 'quant' | 'qual'
  apiKey?: string | null
  onRefresh?: () => void
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
  apiKey,
  onRefresh,
}: AccordionPanelProps) {
  const isExpanded = state !== 'collapsed'
  const [cardModes, setCardModes] = useState<Record<string, CardMode>>({})

  const handleModeChange = useCallback(
    (paperId: string, newMode: CardMode) => {
      if (newMode === 'normal') {
        setCardModes((prev) => {
          const next = { ...prev }
          delete next[paperId]
          return next
        })
      } else {
        setCardModes((prev) => ({ ...prev, [paperId]: newMode }))
      }
    },
    [],
  )

  const handleDimModeChange = useCallback(
    (targetMode: CardMode) => {
      setCardModes((prev) => {
        const allInTarget = papers.every((p) => prev[p.id] === targetMode)
        if (allInTarget) {
          return {}
        }
        const next: Record<string, CardMode> = {}
        for (const p of papers) {
          next[p.id] = targetMode
        }
        return next
      })
    },
    [papers],
  )

  const activeModes = new Set(Object.values(cardModes))
  const dimMode: CardMode = activeModes.size === 1 ? ([...activeModes][0] as CardMode) : 'normal'

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
        {state === 'full' && (
          <div className="compare-dim-mode-buttons" onClick={(e) => e.stopPropagation()}>
            {dimMode === 'normal' ? (
              <>
                <button className="compare-dim-mode-btn" onClick={() => handleDimModeChange('editing')}>
                  编辑
                </button>
                <button className="compare-dim-mode-btn" onClick={() => handleDimModeChange('annotating')}>
                  点评
                </button>
                {apiKey && (
                  <button className="compare-dim-mode-btn" onClick={() => handleDimModeChange('ai_summarizing')}>
                    AI总结
                  </button>
                )}
              </>
            ) : (
              <button className="compare-dim-mode-btn active" onClick={() => handleDimModeChange(dimMode)}>
                退出{dimMode === 'editing' ? '编辑' : dimMode === 'annotating' ? '点评' : 'AI总结'}
              </button>
            )}
          </div>
        )}
        <span className="accordion-arrow">▼</span>
      </div>

      {isExpanded && (
        <div className="accordion-body" style={{ maxHeight: 'none' }}>
          {state === 'preview' && (
            <div className="accordion-preview">
              <div className="preview-cards-scroll">
                {papers.map((p) => {
                  const dimData = getDimData(p, dimId, mode)
                  return (
                    <AnswerCard
                      key={p.id}
                      paper={p}
                      content={dimData?.content || null}
                      variant="preview"
                    />
                  )
                })}
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
                {papers.map((p) => {
                  const dimData = getDimData(p, dimId, mode)
                  const isActive = !!cardModes[p.id] && cardModes[p.id] !== 'normal'
                  const currentMode = isActive ? cardModes[p.id] : 'normal'
                  return (
                    <AnswerCard
                      key={p.id}
                      paper={p}
                      content={dimData?.content || null}
                      variant="full"
                      edit={dimData?.edit}
                      annotations={dimData?.annotations}
                      readingItemId={dimData?.reading_item_id}
                      cardMode={currentMode}
                      onModeChange={(m) => handleModeChange(p.id, m)}
                      isActive={isActive}
                      apiKey={apiKey}
                      onRefresh={onRefresh}
                    />
                  )
                })}
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
