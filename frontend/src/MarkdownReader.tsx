import { useEffect, useMemo, useRef, useState } from 'react'
import { marked } from 'marked'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from './lib/api-fetch'

type ReaderVersion = {
  version: string
  label: string
  available: boolean
}

type ReaderCard = {
  id: string
  title: string
  summary: string | null
  tags: string[]
  source_version: 'original' | 'translated' | 'attachment'
  created_at: string | null
}

type ReaderData = {
  entry: {
    id: string
    title: string
    authors: string[]
    year: number | null
    journal: string | null
    doi: string | null
    abstract: string | null
    keywords: string[]
  }
  current_version: string
  versions: ReaderVersion[]
  markdown: string
  source_markdown_file_id: string | null
  source_translation_artifact_id: number | null
  cards: ReaderCard[]
  citations: {
    outgoing: Array<{ id: string; order: number; title: string | null; raw_text: string; matched_bib_entry_id: string | null }>
    incoming: Array<{ reference_id: string; source_bib_entry_id: string; source_title: string; raw_text: string }>
  }
}

type SelectionDraft = {
  text: string
  before: string
  after: string
}

function formatTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function markdownHtml(raw: string): string {
  let html = marked.parse(raw || '', { async: false }) as string
  html = html.replace(/<table>/g, '<div class="overflow-x-auto"><table>')
  html = html.replace(/<\/table>/g, '</table></div>')
  return html
}

const CITATION_PREVIEW_LIMIT = 8

export default function MarkdownReader({ apiKey }: { apiKey: string }) {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [data, setData] = useState<ReaderData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selection, setSelection] = useState<SelectionDraft | null>(null)
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState('')
  const [expandedOutgoing, setExpandedOutgoing] = useState(false)
  const [expandedIncoming, setExpandedIncoming] = useState(false)
  const view = searchParams.get('view') || 'original'
  const entryId = useMemo(() => {
    const match = location.pathname.match(/\/workspace\/cards\/reader\/([^/?#]+)/)
    return match ? decodeURIComponent(match[1]) : ''
  }, [location.pathname])

  const html = useMemo(() => markdownHtml(data?.markdown || ''), [data?.markdown])

  async function loadReader(nextView = view) {
    if (!entryId) {
      setError('阅读器地址缺少文献 ID。')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/library/entries/${encodeURIComponent(entryId)}/reader?view=${nextView}`)
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '阅读器加载失败')
      setData(payload)
      if (payload.current_version !== nextView) {
        setSearchParams({ view: payload.current_version })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '阅读器加载失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadReader(view)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryId, view])

  function captureSelection() {
    const root = bodyRef.current
    const active = window.getSelection()
    if (!root || !active || active.rangeCount === 0) return
    const text = active.toString().trim()
    if (!text || text.length < 8) {
      setSelection(null)
      return
    }
    const range = active.getRangeAt(0)
    if (!root.contains(range.commonAncestorContainer)) return
    const fullText = root.innerText || ''
    const start = fullText.indexOf(text)
    const before = start >= 0 ? fullText.slice(Math.max(0, start - 900), start) : ''
    const after = start >= 0 ? fullText.slice(start + text.length, start + text.length + 900) : ''
    setSelection({ text, before, after })
    setMessage('')
  }

  async function generateCard() {
    if (!data || !selection) return
    if (!apiKey) {
      window.alert('请先设置 DeepSeek API Key')
      return
    }
    setGenerating(true)
    setMessage('')
    try {
      const response = await apiFetch('/api/cards/from-selection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_bib_entry_id: data.entry.id,
          source_version: data.current_version.startsWith('attachment:') ? 'attachment' : data.current_version,
          source_markdown_file_id: data.source_markdown_file_id,
          source_translation_artifact_id: data.source_translation_artifact_id,
          selected_text: selection.text,
          context_before: selection.before,
          context_after: selection.after,
          user_prompt: prompt,
          api_key: apiKey,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '制卡失败')
      setPrompt('')
      setSelection(null)
      setMessage('卡片已生成。')
      await loadReader(data.current_version)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '制卡失败')
    } finally {
      setGenerating(false)
    }
  }

  if (loading) {
    return <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500">正在打开阅读器...</div>
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-100 bg-red-50 p-6">
        <div className="text-sm font-semibold text-red-700">阅读器不可用</div>
        <div className="mt-2 text-sm text-red-600">{error}</div>
        <button className="mt-4 rounded-lg bg-white px-3 py-2 text-sm text-red-700" onClick={() => navigate('/workspace/library')}>
          返回文献库
        </button>
      </div>
    )
  }

  return (
    <div className="grid min-h-[calc(100vh-150px)] gap-5 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
      <aside className="space-y-4">
        <button
          type="button"
          onClick={() => navigate('/workspace/library')}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:border-emerald-300 hover:text-emerald-700"
        >
          返回文献库
        </button>
        <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">引用关系</h2>
          <div className="mt-4">
            <div className="text-xs font-semibold text-gray-500">引用了 ({data.citations.outgoing.length})</div>
            <div className="mt-2 space-y-2">
              {data.citations.outgoing.length === 0 ? (
                <p className="text-xs text-gray-400">暂无参考文献梳理结果。</p>
              ) : (expandedOutgoing ? data.citations.outgoing : data.citations.outgoing.slice(0, CITATION_PREVIEW_LIMIT)).map((ref) => (
                <div
                  key={ref.id}
                  className="cursor-pointer rounded-lg bg-gray-50 p-2 text-xs text-gray-600 transition-colors hover:bg-blue-50 hover:text-blue-800"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/workspace?tab=references&sourceEntryId=${encodeURIComponent(entryId)}&refId=${encodeURIComponent(ref.id)}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/workspace?tab=references&sourceEntryId=${encodeURIComponent(entryId)}&refId=${encodeURIComponent(ref.id)}`) }}
                >
                  [{ref.order}] {ref.title || ref.raw_text}
                </div>
              ))}
              {data.citations.outgoing.length > CITATION_PREVIEW_LIMIT && (
                <button
                  type="button"
                  onClick={() => setExpandedOutgoing(!expandedOutgoing)}
                  className="text-xs text-cyan-700 hover:text-cyan-800"
                >
                  {expandedOutgoing ? '收起' : `展开全部 (${data.citations.outgoing.length} 条)`}
                </button>
              )}
            </div>
          </div>
          <div className="mt-5">
            <div className="text-xs font-semibold text-gray-500">被引用 ({data.citations.incoming.length})</div>
            <div className="mt-2 space-y-2">
              {data.citations.incoming.length === 0 ? (
                <p className="text-xs text-gray-400">暂无库内反向引用。</p>
              ) : (expandedIncoming ? data.citations.incoming : data.citations.incoming.slice(0, CITATION_PREVIEW_LIMIT)).map((ref) => (
                <div
                  key={ref.reference_id}
                  className="cursor-pointer rounded-lg bg-gray-50 p-2 text-xs text-gray-600 transition-colors hover:bg-blue-50 hover:text-blue-800"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/workspace?tab=references&sourceEntryId=${encodeURIComponent(ref.source_bib_entry_id)}&refId=${encodeURIComponent(ref.reference_id)}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/workspace?tab=references&sourceEntryId=${encodeURIComponent(ref.source_bib_entry_id)}&refId=${encodeURIComponent(ref.reference_id)}`) }}
                >
                  {ref.source_title}
                </div>
              ))}
              {data.citations.incoming.length > CITATION_PREVIEW_LIMIT && (
                <button
                  type="button"
                  onClick={() => setExpandedIncoming(!expandedIncoming)}
                  className="text-xs text-cyan-700 hover:text-cyan-800"
                >
                  {expandedIncoming ? '收起' : `展开全部 (${data.citations.incoming.length} 条)`}
                </button>
              )}
            </div>
          </div>
        </section>
      </aside>

      <main className="min-w-0 rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-bold leading-snug text-gray-950">{data.entry.title}</h1>
              <p className="mt-2 text-sm text-gray-500">
                {data.entry.authors?.slice(0, 4).join(', ')}
                {data.entry.year ? ` · ${data.entry.year}` : ''}
                {data.entry.journal ? ` · ${data.entry.journal}` : ''}
              </p>
            </div>
            <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
              {data.versions.map((item) => (
                <button
                  key={item.version}
                  type="button"
                  disabled={!item.available}
                  onClick={() => setSearchParams({ view: item.version })}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                    data.current_version === item.version
                      ? 'bg-white text-emerald-700 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          {message && <div className="mt-3 text-sm text-emerald-700">{message}</div>}
        </div>

        <div className="relative">
          <div
            ref={bodyRef}
            onMouseUp={captureSelection}
            className="max-w-none px-6 py-6 text-[15px] leading-8 text-gray-800 [&_blockquote]:border-l-4 [&_blockquote]:border-emerald-200 [&_blockquote]:pl-4 [&_code]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_h1]:mb-4 [&_h1]:mt-8 [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:mb-3 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-6 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:ml-6 [&_li]:list-disc [&_ol>li]:list-decimal [&_p]:mb-4 [&_table]:min-w-full [&_table]:border-collapse [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-gray-200 [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1"
            dangerouslySetInnerHTML={{ __html: html }}
          />
          {selection && (
            <div className="sticky bottom-4 mx-6 rounded-xl border border-emerald-200 bg-white p-4 shadow-lg">
              <div className="text-xs font-semibold text-emerald-700">已选中 {selection.text.length} 字</div>
              <div className="mt-2 line-clamp-2 text-sm text-gray-700">{selection.text}</div>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={2}
                className="mt-3 w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                placeholder="可选：告诉 AI 这张卡片更关注什么"
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={generateCard}
                  disabled={generating}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {generating ? '生成中...' : 'AI 卡片'}
                </button>
                <button
                  type="button"
                  onClick={() => setSelection(null)}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      <aside className="space-y-4">
        <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-gray-900">关联卡片</h2>
            <button
              type="button"
              onClick={() => navigate('/workspace/cards')}
              className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
            >
              卡片库
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {data.cards.length === 0 ? (
              <p className="rounded-lg border border-dashed border-gray-200 p-4 text-sm text-gray-400">
                选中正文片段后即可生成卡片。
              </p>
            ) : data.cards.map((card) => (
              <article key={card.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                <div className="text-sm font-semibold text-gray-900">{card.title}</div>
                {card.summary && <p className="mt-1 text-xs leading-5 text-gray-600">{card.summary}</p>}
                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-emerald-700">
                    {card.source_version === 'translated' ? '译文' : card.source_version === 'attachment' ? '附件' : '原文'}
                  </span>
                  {card.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-500">
                      #{tag}
                    </span>
                  ))}
                </div>
                <div className="mt-2 text-[11px] text-gray-400">{formatTime(card.created_at)}</div>
              </article>
            ))}
          </div>
        </section>
      </aside>
    </div>
  )
}
