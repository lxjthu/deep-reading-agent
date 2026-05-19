import { useRef, useEffect, useState, useCallback } from 'react'
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

function formatAuthors(authors: string[], year: number | null, journal?: string): string {
  const auth = (authors || []).slice(0, 3).join(', ')
  const yr = year ? ` (${year})` : ''
  const j = journal ? ` · ${journal}` : ''
  return auth + yr + j
}

function findInMd(md: string, search: string, fromPlainPos: number): { start: number; end: number } | null {
  const charMap: number[] = []
  let stripped = ''
  let i = 0
  while (i < md.length) {
    if (md[i] === '*' && i + 1 < md.length && md[i + 1] === '*') { i += 2; continue }
    if (md[i] === '*') { i += 1; continue }
    if (md[i] === '#' && (i === 0 || md[i - 1] === '\n')) {
      while (i < md.length && md[i] === '#') i++
      if (i < md.length && md[i] === ' ') i++
      continue
    }
    if (md[i] === '-' && (i === 0 || md[i - 1] === '\n') && i + 1 < md.length && md[i + 1] === ' ') {
      i += 2; continue
    }
    if (md[i] === '>' && (i === 0 || md[i - 1] === '\n')) {
      i += 1; continue
    }
    if (md[i] === '`' && i + 1 < md.length && md[i + 1] === '`' && i + 2 < md.length && md[i + 2] === '`') { i += 3; continue }
    if (md[i] === '`') { i += 1; continue }
    charMap.push(i)
    stripped += md[i]
    i++
  }
  const idx = stripped.indexOf(search, fromPlainPos)
  if (idx < 0 || idx + search.length > charMap.length) return null
  return { start: charMap[idx], end: charMap[idx + search.length - 1] + 1 }
}

export type CardMode = 'normal' | 'editing' | 'annotating' | 'ai_summarizing'
export type AiDisplayMode = 'summary_only' | 'original_only' | 'both'

interface AnnotationData {
  id: string
  source_type: string
  selected_text: string | null
  note: string
  char_start: number | null
  char_end: number | null
  is_ai_generated: number
  color: string | null
  created_at: string | null
}

interface EditData {
  edited_content: string
  updated_at: string | null
}

interface AnswerCardProps {
  paper: {
    id: string
    title: string
    authors: string[]
    year: number | null
    journal?: string
  }
  content: string | null
  variant: 'preview' | 'full'
  edit?: EditData
  annotations?: AnnotationData[]
  readingItemId?: number
  cardMode?: CardMode
  onModeChange?: (mode: CardMode) => void
  isActive?: boolean
  apiKey?: string | null
  onRefresh?: () => void
}

const HIGHLIGHT_COLORS = ['#fef08a', '#bbf7d0', '#bfdbfe', '#fecaca', '#e9d5ff', '#fed7aa']

export function AnswerCard({
  paper,
  content,
  variant,
  edit,
  annotations = [],
  readingItemId,
  cardMode = 'normal',
  onModeChange,
  isActive = false,
  apiKey,
  onRefresh,
}: AnswerCardProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [editText, setEditText] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [aiDisplayMode, setAiDisplayMode] = useState<AiDisplayMode>('both')
  const [showAnnotationPopup, setShowAnnotationPopup] = useState(false)
  const [popupPos, setPopupPos] = useState({ x: 0, y: 0 })
  const [selectedText, setSelectedText] = useState('')
  const [annotationNote, setAnnotationNote] = useState('')
  const [annotationColor, setAnnotationColor] = useState(HIGHLIGHT_COLORS[0])
  const [isAiLoading, setIsAiLoading] = useState(false)

  const [editingAnnotationId, setEditingAnnotationId] = useState<string | null>(null)
  const [editAnnotationNote, setEditAnnotationNote] = useState('')

  const [undoStack, setUndoStack] = useState<string[]>([])

  const displayContent = edit ? edit.edited_content : (content || '')
  const hasContent = displayContent && displayContent.trim()
  const hasEdit = !!edit

  useEffect(() => {
    if (cardMode === 'editing' && isActive) {
      setEditText(displayContent)
      setUndoStack([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardMode, isActive])

  useEffect(() => {
    if (contentRef.current && hasContent && cardMode !== 'editing') {
      mathRender(contentRef.current)
    }
  }, [hasContent, displayContent, cardMode, aiDisplayMode, annotations])

  useEffect(() => {
    if (cardMode === 'editing' && isActive && textareaRef.current) {
      const ta = textareaRef.current
      ta.style.height = 'auto'
      ta.style.height = ta.scrollHeight + 'px'
    }
  }, [editText, cardMode, isActive])

  useEffect(() => {
    if (cardMode !== 'annotating' || !isActive) return
    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest('[data-ann-id]')
      if (!target) return
      const annId = target.getAttribute('data-ann-id')
      if (!annId) return
      const ann = annotations.find((a) => a.id === annId && a.is_ai_generated === 0)
      if (!ann) return
      e.preventDefault()
      e.stopPropagation()
      const rect = (target as HTMLElement).getBoundingClientRect()
      const container = contentRef.current?.getBoundingClientRect()
      if (!container) return
      setEditingAnnotationId(ann.id)
      setEditAnnotationNote(ann.note)
      setPopupPos({
        x: rect.left - container.left + rect.width / 2,
        y: rect.bottom - container.top + 8,
      })
      setShowAnnotationPopup(true)
      setSelectedText('')
    }
    const el = contentRef.current
    el?.addEventListener('click', handleClick)
    return () => el?.removeEventListener('click', handleClick)
  }, [cardMode, isActive, annotations])

  const handleSaveEdit = useCallback(async () => {
    if (!readingItemId) return
    setIsSaving(true)
    try {
      const res = await fetch(`/api/compare/reading-items/${readingItemId}/edit`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edited_content: editText }),
      })
      if (res.ok) {
        onRefresh?.()
      }
    } finally {
      setIsSaving(false)
    }
  }, [readingItemId, editText, onRefresh])

  const handleRevertEdit = useCallback(async () => {
    if (!readingItemId) return
    setIsSaving(true)
    try {
      const res = await fetch(`/api/compare/reading-items/${readingItemId}/edit`, {
        method: 'DELETE',
      })
      if (res.ok) {
        setEditText(content || '')
        setUndoStack([])
        onRefresh?.()
      }
    } finally {
      setIsSaving(false)
    }
  }, [readingItemId, content, onRefresh])

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    const prev = undoStack[undoStack.length - 1]
    setEditText(prev)
    setUndoStack((s) => s.slice(0, -1))
  }, [undoStack])

  const pushUndo = useCallback(
    (next: string) => {
      setUndoStack((s) => [...s, editText])
      setEditText(next)
    },
    [editText],
  )

  const handleTextSelect = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !contentRef.current?.contains(sel.anchorNode)) return
    const text = sel.toString().trim()
    if (!text) return
    setSelectedText(text)
    setEditingAnnotationId(null)
    const range = sel.getRangeAt(0)
    const rect = range.getBoundingClientRect()
    const container = contentRef.current.getBoundingClientRect()
    setPopupPos({
      x: rect.left - container.left + rect.width / 2,
      y: rect.top - container.top - 10,
    })
    setShowAnnotationPopup(true)
  }, [cardMode])

  const handleCreateAnnotation = useCallback(async () => {
    if (!readingItemId) return
    try {
      await fetch('/api/compare/annotations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_type: 'compare_card',
          source_id: String(readingItemId),
          selected_text: selectedText,
          note: annotationNote,
          color: annotationColor,
          bib_entry_id: paper.id,
        }),
      })
      setShowAnnotationPopup(false)
      setAnnotationNote('')
      setSelectedText('')
      onRefresh?.()
    } catch (_err) {
      // annotation creation failed silently
    }
  }, [readingItemId, selectedText, annotationNote, annotationColor, paper.id, onRefresh])

  const handleDeleteAnnotation = useCallback(
    async (id: string) => {
      await fetch(`/api/compare/annotations/${id}`, { method: 'DELETE' })
      setShowAnnotationPopup(false)
      setEditingAnnotationId(null)
      onRefresh?.()
    },
    [onRefresh],
  )

  const handleUpdateAnnotation = useCallback(
    async (id: string, note: string) => {
      await fetch(`/api/compare/annotations/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note }),
      })
      setShowAnnotationPopup(false)
      setEditingAnnotationId(null)
      onRefresh?.()
    },
    [onRefresh],
  )

  const handleAiSummary = useCallback(async () => {
    if (!readingItemId || !selectedText || !apiKey) return
    setIsAiLoading(true)
    try {
      const res = await fetch('/api/compare/ai-summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: selectedText,
          api_key: apiKey,
          reading_item_id: readingItemId,
          bib_entry_id: paper.id,
        }),
      })
      if (res.ok) {
        setShowAnnotationPopup(false)
        setSelectedText('')
        setAiDisplayMode('both')
        onRefresh?.()
      }
    } finally {
      setIsAiLoading(false)
    }
  }, [readingItemId, selectedText, apiKey, paper.id, onRefresh])

  const renderAnnotatedContent = useCallback(
    (text: string, filterAi: number) => {
      const filtered = annotations.filter((a) => a.is_ai_generated === filterAi)
      if (filtered.length === 0) return md2html(text)

      const result = text
      const sorted = [...filtered].sort((a, b) => (a.char_start ?? 0) - (b.char_start ?? 0))
      const parts: { text: string; annotation?: AnnotationData }[] = []
      let lastEnd = 0

      for (const ann of sorted) {
        let matchStart = -1
        let matchEnd = -1

        if (ann.char_start != null && ann.char_end != null && ann.char_end > ann.char_start) {
          matchStart = ann.char_start
          matchEnd = ann.char_end
        } else if (ann.selected_text) {
          const found = findInMd(result, ann.selected_text, 0)
          if (found) {
            matchStart = found.start
            matchEnd = found.end
          }
        }

        if (matchStart >= 0 && matchEnd > matchStart && matchStart >= lastEnd) {
          if (matchStart > lastEnd) parts.push({ text: result.slice(lastEnd, matchStart) })
          parts.push({ text: result.slice(matchStart, matchEnd), annotation: ann })
          lastEnd = matchEnd
        }
      }
      if (lastEnd < result.length) parts.push({ text: result.slice(lastEnd) })

      return parts
        .map((part) => {
          const html = md2html(part.text)
          if (part.annotation) {
            const color = part.annotation.color || HIGHLIGHT_COLORS[0]
            const noteEscaped = (part.annotation.note || '')
              .replace(/"/g, '&quot;')
              .replace(/\n/g, ' ')
            return `<span class="compare-highlight" style="background:${color};border-radius:2px;padding:0 2px;cursor:pointer" data-ann-id="${part.annotation.id}" title="${noteEscaped}">${part.text}</span>`
          }
          return html
        })
        .join('')
    },
    [annotations],
  )

  const meta = formatAuthors(paper.authors, paper.year, paper.journal)
  const titleText = paper.title || '未命名文献'

  const modeButtons =
    variant === 'full' && readingItemId ? (
      <div className="compare-card-mode-buttons">
        {cardMode === 'normal' && (
          <>
            <button
              className="compare-mode-btn"
              onClick={() => onModeChange?.('editing')}
              title="编辑"
            >
              编辑
            </button>
            <button
              className="compare-mode-btn"
              onClick={() => onModeChange?.('annotating')}
              title="点评"
            >
              点评
            </button>
            {apiKey && (
              <button
                className="compare-mode-btn"
                onClick={() => onModeChange?.('ai_summarizing')}
                title="AI总结"
              >
                AI总结
              </button>
            )}
          </>
        )}
        {cardMode !== 'normal' && (
          <button
            className="compare-mode-btn compare-mode-btn-exit"
            onClick={() => onModeChange?.('normal')}
          >
            退出{cardMode === 'editing' ? '编辑' : cardMode === 'annotating' ? '点评' : 'AI总结'}
          </button>
        )}
        {hasEdit && cardMode === 'normal' && (
          <span className="compare-edited-badge">已编辑</span>
        )}
      </div>
    ) : null

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
            dangerouslySetInnerHTML={{ __html: md2html(displayContent) }}
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
        {modeButtons}
      </div>

      {cardMode === 'editing' && isActive ? (
        <div className="compare-edit-area">
          <div className="compare-edit-top-bar">
            <button
              className="btn btn-primary btn-sm"
              onClick={handleSaveEdit}
              disabled={isSaving}
            >
              {isSaving ? '保存中...' : '保存'}
            </button>
            <button
              className="btn btn-outline btn-sm"
              onClick={handleUndo}
              disabled={undoStack.length === 0 || isSaving}
            >
              撤销
            </button>
            {hasEdit && (
              <button
                className="btn btn-outline btn-sm"
                onClick={handleRevertEdit}
                disabled={isSaving}
              >
                回退到原始
              </button>
            )}
            <button
              className="btn btn-outline btn-sm"
              onClick={() => onModeChange?.('normal')}
            >
              取消
            </button>
          </div>
          <textarea
            ref={textareaRef}
            className="compare-edit-textarea"
            value={editText}
            onChange={(e) => pushUndo(e.target.value)}
          />
        </div>
      ) : cardMode === 'annotating' && isActive ? (
        <div className="compare-annotate-wrapper">
          <div
            className="answer-card-content md-content compare-annotate-area"
            ref={contentRef}
            onMouseUp={handleTextSelect}
            dangerouslySetInnerHTML={{
              __html: hasContent ? renderAnnotatedContent(displayContent, 0) : '',
            }}
          />
          <div className="compare-annotations-list">
            {annotations
              .filter((a) => a.is_ai_generated === 0)
              .map((a) => (
                <div key={a.id} className="compare-annotation-item">
                  <span
                    className="compare-annotation-color-bar"
                    style={{ background: a.color || HIGHLIGHT_COLORS[0] }}
                  />
                  <span className="compare-annotation-item-text">{a.note}</span>
                  <button
                    className="compare-annotation-item-edit"
                    onClick={() => {
                      setEditingAnnotationId(a.id)
                      setEditAnnotationNote(a.note)
                      setPopupPos({ x: 0, y: 0 })
                      setShowAnnotationPopup(true)
                      setSelectedText('')
                    }}
                  >
                    编辑
                  </button>
                  <button
                    className="compare-annotation-item-delete"
                    onClick={() => handleDeleteAnnotation(a.id)}
                  >
                    删除
                  </button>
                </div>
              ))}
            {annotations.filter((a) => a.is_ai_generated === 0).length === 0 && (
              <div className="compare-ai-empty">选中文字后添加点评</div>
            )}
          </div>
        </div>
      ) : cardMode === 'ai_summarizing' && isActive ? (
        <div className="compare-ai-area">
          <div className="compare-ai-toggle">
            <button
              className={`compare-ai-toggle-btn${aiDisplayMode === 'summary_only' ? ' active' : ''}`}
              onClick={() => setAiDisplayMode('summary_only')}
            >
              只看总结
            </button>
            <button
              className={`compare-ai-toggle-btn${aiDisplayMode === 'original_only' ? ' active' : ''}`}
              onClick={() => setAiDisplayMode('original_only')}
            >
              只看原文
            </button>
            <button
              className={`compare-ai-toggle-btn${aiDisplayMode === 'both' ? ' active' : ''}`}
              onClick={() => setAiDisplayMode('both')}
            >
              对照
            </button>
          </div>

          {aiDisplayMode !== 'original_only' && (
            <div className="compare-ai-summaries">
              {annotations
                .filter((a) => a.is_ai_generated === 1)
                .map((a) => (
                  <div key={a.id} className="compare-ai-summary-item">
                    <div className="compare-ai-summary-text">{a.note}</div>
                    {a.selected_text && (
                      <div className="compare-ai-summary-source">
                        「{a.selected_text}」
                      </div>
                    )}
                  </div>
                ))}
              {annotations.filter((a) => a.is_ai_generated === 1).length === 0 && (
                <div className="compare-ai-empty">暂无AI总结，选中文字后点击总结按钮</div>
              )}
            </div>
          )}

          {aiDisplayMode !== 'summary_only' && (
            <div
              className="answer-card-content md-content"
              ref={contentRef}
              onMouseUp={handleTextSelect}
              dangerouslySetInnerHTML={{
                __html: hasContent ? md2html(displayContent) : '',
              }}
            />
          )}
        </div>
      ) : hasContent ? (
        <div
          ref={contentRef}
          className="answer-card-content md-content"
          dangerouslySetInnerHTML={{ __html: md2html(displayContent) }}
        />
      ) : (
        <div className="answer-card-empty">（未包含此维度）</div>
      )}

      {showAnnotationPopup && (
        <div
          className="compare-annotation-popup"
          style={{ left: popupPos.x, top: popupPos.y }}
        >
          {selectedText && (
            <div className="compare-annotation-popup-text">
              「{selectedText.slice(0, 60)}
              {selectedText.length > 60 ? '...' : ''}」
            </div>
          )}

          {cardMode === 'annotating' && editingAnnotationId ? (
            <>
              <div className="compare-annotation-popup-label">编辑点评</div>
              <textarea
                className="compare-annotation-input"
                placeholder="修改点评内容..."
                value={editAnnotationNote}
                onChange={(e) => setEditAnnotationNote(e.target.value)}
                rows={2}
              />
              <div className="compare-annotation-popup-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => handleUpdateAnnotation(editingAnnotationId, editAnnotationNote)}
                  disabled={!editAnnotationNote.trim()}
                >
                  保存
                </button>
                <button
                  className="btn btn-outline btn-sm"
                  style={{ color: 'var(--accent-coral)', borderColor: 'rgba(159,18,57,0.3)' }}
                  onClick={() => handleDeleteAnnotation(editingAnnotationId)}
                >
                  删除
                </button>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => {
                    setShowAnnotationPopup(false)
                    setEditingAnnotationId(null)
                  }}
                >
                  取消
                </button>
              </div>
            </>
          ) : cardMode === 'annotating' ? (
            <>
              <textarea
                className="compare-annotation-input"
                placeholder="输入点评（可选）..."
                value={annotationNote}
                onChange={(e) => setAnnotationNote(e.target.value)}
                rows={2}
              />
              <div className="compare-annotation-colors">
                {HIGHLIGHT_COLORS.map((c) => (
                  <span
                    key={c}
                    className={`compare-color-dot${annotationColor === c ? ' selected' : ''}`}
                    style={{ background: c }}
                    onClick={() => setAnnotationColor(c)}
                  />
                ))}
              </div>
              <div className="compare-annotation-popup-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleCreateAnnotation}
                  disabled={false}
                >
                  高亮
                </button>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => setShowAnnotationPopup(false)}
                >
                  取消
                </button>
              </div>
            </>
          ) : cardMode === 'ai_summarizing' ? (
            <div className="compare-annotation-popup-actions">
              <button
                className="btn btn-primary btn-sm"
                onClick={handleAiSummary}
                disabled={isAiLoading}
              >
                {isAiLoading ? '总结中...' : 'AI总结'}
              </button>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => setShowAnnotationPopup(false)}
              >
                取消
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
