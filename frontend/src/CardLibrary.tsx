import { useEffect, useMemo, useState } from 'react'
import { marked } from 'marked'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from './lib/api-fetch'

type CardNote = {
  id: string
  source_bib_entry_id: string
  source_title: string | null
  source_version: 'original' | 'translated' | 'attachment'
  source_markdown_file_id: string | null
  title: string
  summary: string | null
  tags: string[]
  selected_text: string
  body_markdown: string
  created_at: string | null
  updated_at: string | null
}

function markdownHtml(raw: string) {
  return marked.parse(raw || '', { async: false }) as string
}

function formatTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

export default function CardLibrary() {
  const navigate = useNavigate()
  const [cards, setCards] = useState<CardNote[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftSummary, setDraftSummary] = useState('')
  const [draftTags, setDraftTags] = useState('')
  const [draftBody, setDraftBody] = useState('')

  const selected = cards.find((card) => card.id === selectedId) || cards[0] || null
  const tags = useMemo(() => Array.from(new Set(cards.flatMap((card) => card.tags))).sort(), [cards])

  async function loadCards() {
    setLoading(true)
    setMessage('')
    try {
      const params = new URLSearchParams()
      if (query.trim()) params.set('q', query.trim())
      if (tag.trim()) params.set('tag', tag.trim())
      const response = await apiFetch(`/api/cards${params.toString() ? `?${params}` : ''}`)
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '卡片加载失败')
      setCards(payload)
      setSelectedId((current) => (current && payload.some((card: CardNote) => card.id === current) ? current : payload[0]?.id || null))
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '卡片加载失败')
      setCards([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadCards()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tag])

  useEffect(() => {
    if (!selected) return
    setEditing(false)
    setDraftTitle(selected.title)
    setDraftSummary(selected.summary || '')
    setDraftTags(selected.tags.join(', '))
    setDraftBody(selected.body_markdown)
  }, [selected?.id])

  async function saveSelected() {
    if (!selected) return
    setMessage('')
    try {
      const response = await apiFetch(`/api/cards/${selected.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: draftTitle,
          summary: draftSummary,
          tags: draftTags.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean),
          body_markdown: draftBody,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '保存失败')
      setEditing(false)
      await loadCards()
      setMessage('卡片已保存。')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '保存失败')
    }
  }

  async function deleteSelected() {
    if (!selected) return
    if (!window.confirm('确定删除这张卡片吗？')) return
    try {
      const response = await apiFetch(`/api/cards/${selected.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || '删除失败')
      }
      setSelectedId(null)
      await loadCards()
      setMessage('卡片已删除。')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '删除失败')
    }
  }

  async function exportZip() {
    try {
      const response = await apiFetch('/api/cards/export/obsidian')
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || '导出失败')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'markdown-card-notes.zip'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '导出失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-950">Markdown 卡片库</h1>
          <p className="mt-1 text-sm text-gray-500">集中管理从原文、译文和附件中生成的原子阅读卡。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => navigate('/workspace/library')}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:border-emerald-300"
          >
            返回文献库
          </button>
          <button
            type="button"
            onClick={exportZip}
            className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            导出 Obsidian ZIP
          </button>
        </div>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void loadCards()
            }}
            className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            placeholder="搜索标题、正文、来源论文"
          />
          <select
            value={tag}
            onChange={(event) => setTag(event.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          >
            <option value="">全部标签</option>
            {tags.map((item) => (
              <option key={item} value={item}>#{item}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void loadCards()}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
          >
            搜索
          </button>
        </div>
        {message && <div className="mt-3 text-sm text-emerald-700">{message}</div>}
      </section>

      <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="min-h-[520px] rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-4 py-3 text-sm font-semibold text-gray-700">
            卡片 {cards.length}
          </div>
          <div className="max-h-[680px] divide-y divide-gray-100 overflow-y-auto">
            {loading ? (
              <div className="p-5 text-sm text-gray-400">加载中...</div>
            ) : cards.length === 0 ? (
              <div className="p-5 text-sm text-gray-400">暂无卡片。</div>
            ) : cards.map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => setSelectedId(card.id)}
                className={`block w-full px-4 py-4 text-left hover:bg-gray-50 ${
                  selected?.id === card.id ? 'bg-emerald-50' : ''
                }`}
              >
                <div className="text-sm font-semibold text-gray-900">{card.title}</div>
                {card.summary && <div className="mt-1 line-clamp-2 text-xs leading-5 text-gray-600">{card.summary}</div>}
                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-emerald-700">
                    {card.source_version === 'translated' ? '译文' : card.source_version === 'attachment' ? '附件' : '原文'}
                  </span>
                  {card.tags.slice(0, 4).map((item) => (
                    <span key={item} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-500">#{item}</span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="min-h-[520px] rounded-xl border border-gray-200 bg-white shadow-sm">
          {selected ? (
            <div>
              <div className="border-b border-gray-100 px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-emerald-700">
                      {selected.source_version === 'translated' ? '译文卡片' : selected.source_version === 'attachment' ? '附件卡片' : '原文卡片'}
                    </div>
                    <h2 className="mt-1 text-lg font-bold text-gray-950">{selected.title}</h2>
                    <p className="mt-1 text-sm text-gray-500">{selected.source_title}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const view = selected.source_version === 'attachment' && selected.source_markdown_file_id
                          ? `attachment:${selected.source_markdown_file_id}`
                          : selected.source_version
                        navigate(`/workspace/cards/reader/${selected.source_bib_entry_id}?view=${view}`)
                      }}
                      className="rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
                    >
                      回到原文
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditing((value) => !value)}
                      className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200"
                    >
                      {editing ? '预览' : '编辑'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteSelected()}
                      className="rounded-lg bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>

              {editing ? (
                <div className="space-y-4 p-5">
                  <input
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                  />
                  <input
                    value={draftSummary}
                    onChange={(event) => setDraftSummary(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    placeholder="一句话总结"
                  />
                  <input
                    value={draftTags}
                    onChange={(event) => setDraftTags(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    placeholder="标签，用逗号分隔"
                  />
                  <textarea
                    value={draftBody}
                    onChange={(event) => setDraftBody(event.target.value)}
                    rows={16}
                    className="w-full resize-y rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm focus:border-emerald-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => void saveSelected()}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                  >
                    保存卡片
                  </button>
                </div>
              ) : (
                <div className="p-5">
                  <div className="flex flex-wrap gap-2">
                    {selected.tags.map((item) => (
                      <span key={item} className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700">#{item}</span>
                    ))}
                  </div>
                  {selected.summary && <p className="mt-4 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">{selected.summary}</p>}
                  <div
                    className="mt-5 max-w-none text-sm leading-7 text-gray-800 [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-base [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:mb-3"
                    dangerouslySetInnerHTML={{ __html: markdownHtml(selected.body_markdown) }}
                  />
                  <div className="mt-6 rounded-lg border border-gray-100 bg-gray-50 p-4">
                    <div className="text-xs font-semibold text-gray-500">来源摘录</div>
                    <blockquote className="mt-2 line-clamp-6 text-sm leading-7 text-gray-700">{selected.selected_text}</blockquote>
                  </div>
                  <div className="mt-4 text-xs text-gray-400">
                    创建于 {formatTime(selected.created_at)} {selected.updated_at ? ` · 更新于 ${formatTime(selected.updated_at)}` : ''}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-6 text-sm text-gray-400">选择一张卡片查看详情。</div>
          )}
        </section>
      </div>
    </div>
  )
}
