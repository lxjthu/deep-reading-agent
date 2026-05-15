import { useEffect, useRef } from 'react'
import { marked } from 'marked'
import { useSynthesisStream } from '../../hooks/useSynthesisStream'

function md2html(raw: string): string {
  let h = marked.parse(raw || '', { async: false }) as string
  h = h.replace(/<table>/g, '<div class="table-wrapper"><table>')
  h = h.replace(/<\/table>/g, '</table></div>')
  return h
}

interface SynthesisModalProps {
  open: boolean
  onClose: () => void
  mode: string
  bibEntryIds: string[]
  selectedDimIds: string[]
  apiKey: string | null
}

export function SynthesisModal({ open, onClose, mode, bibEntryIds, selectedDimIds, apiKey }: SynthesisModalProps) {
  const { content, isStreaming, error, start, reset } = useSynthesisStream()
  const contentRef = useRef<HTMLDivElement>(null)
  const startedRef = useRef(false)

  useEffect(() => {
    if (open && apiKey && !startedRef.current) {
      startedRef.current = true
      start({
        mode,
        bib_entry_ids: bibEntryIds,
        api_key: apiKey,
        selected_dimensions: selectedDimIds,
      })
    }
    if (!open) {
      startedRef.current = false
      reset()
    }
  }, [open, apiKey, mode, bibEntryIds, selectedDimIds, start, reset])

  useEffect(() => {
    if (contentRef.current && content) {
      if (typeof (window as any).renderMathInElement === 'function') {
        ;(window as any).renderMathInElement(contentRef.current, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
            { left: '\\(', right: '\\)', display: false },
            { left: '\\[', right: '\\]', display: true },
          ],
        })
      }
    }
  }, [content])

  if (!open) return null

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.4)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff',
          borderRadius: 12,
          width: '90%',
          maxWidth: 900,
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 12px 32px rgba(45,42,38,0.15)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderBottom: '1px solid var(--border-light)' }}>
          <h3 style={{ fontFamily: 'var(--font-title)', fontSize: 18, fontWeight: 700, margin: 0 }}>AI 综述</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            {content && (
              <button className="btn btn-outline" onClick={handleCopy}>复制</button>
            )}
            <button className="btn btn-outline" onClick={onClose}>关闭</button>
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px' }}>
          {isStreaming && !content && (
            <div className="loading-state">
              <div className="spinner" />
              <span>AI 正在生成综述...</span>
            </div>
          )}
          {error && (
            <div style={{ color: 'var(--accent-coral)', padding: '20px 0', textAlign: 'center' }}>
              生成失败: {error}
            </div>
          )}
          {content && (
            <div
              ref={contentRef}
              className="md-content"
              dangerouslySetInnerHTML={{ __html: md2html(content) }}
            />
          )}
          {isStreaming && content && (
            <div className="loading-state" style={{ padding: '20px 0' }}>
              <div className="spinner" />
              <span>正在生成...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
