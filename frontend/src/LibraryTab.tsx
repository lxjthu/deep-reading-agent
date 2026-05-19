import { useEffect, useMemo, useState } from 'react'
import { downloadWithAuth } from './lib/download'
import MetadataMatchPanel from './MetadataMatchPanel'

type LibraryEntrySummary = {
  id: string
  title: string
  authors: string[]
  year: number | null
  doi: string | null
  journal: string | null
  reading_status: 'none' | 'has_pdf' | 'reading' | 'read'
  metadata_completeness: 'full' | 'partial' | 'minimal'
  is_pinned: number
  source_db: string
  source_file_id: string | null
  source_file_name: string | null
  tags: string[]
  note: string | null
  filter_score: number | null
}

type LibraryArtifact = {
  id: number
  filename: string
  artifact_type: string
  storage_path: string
  created_at: string | null
}

type LibraryTimelineItem = {
  job_id: string
  job_type: string
  status: string
  created_at: string | null
  finished_at: string | null
  artifacts: LibraryArtifact[]
}

type LibraryEntryDetail = LibraryEntrySummary & {
  abstract: string | null
  keywords: string[]
  timeline: LibraryTimelineItem[]
  filter_evaluations: LibraryFilterEvaluation[]
}

type LibraryFilterEvaluation = {
  filter_job_id: string
  passed: number
  score: number | null
  reason: string | null
  abstract_translation: string | null
  created_at: string | null
}

type EditDraft = {
  title: string
  authorsText: string
  yearText: string
  doi: string
  journal: string
  abstract: string
  keywordsText: string
  tagsText: string
  note: string
  isPinned: boolean
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : typeof data?.message === 'string'
          ? data.message
          : '请求失败。'
    throw new Error(detail)
  }
  return data as T
}

function splitCsv(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function statusLabel(status: LibraryEntrySummary['reading_status']) {
  return (
    {
      none: '未进入精读',
      has_pdf: '已有关联文件',
      reading: '精读中',
      read: '已完成精读',
    } as const
  )[status]
}

function statusClass(status: LibraryEntrySummary['reading_status']) {
  return (
    {
      none: 'bg-gray-100 text-gray-600',
      has_pdf: 'bg-sky-100 text-sky-700',
      reading: 'bg-amber-100 text-amber-700',
      read: 'bg-emerald-100 text-emerald-700',
    } as const
  )[status]
}

function metadataClass(level: LibraryEntrySummary['metadata_completeness']) {
  return (
    {
      full: 'bg-emerald-100 text-emerald-700',
      partial: 'bg-amber-100 text-amber-700',
      minimal: 'bg-red-100 text-red-700',
    } as const
  )[level]
}

function metadataLabel(level: LibraryEntrySummary['metadata_completeness']) {
  return (
    {
      full: '元数据完整',
      partial: '元数据待补',
      minimal: '元数据缺失较多',
    } as const
  )[level]
}

function sourceDbLabel(sourceDb: string) {
  return (
    {
      wos: 'Web of Science',
      cnki: 'CNKI',
      scopus: 'Scopus',
      manual: '手工录入',
      pdf_extracted: 'PDF 提取',
      md_extracted: 'Markdown 提取',
      other: '其他来源',
    }[sourceDb] || sourceDb
  )
}

function artifactTypeLabel(artifactType: string) {
  return (
    {
      reading_step: '精读步骤',
      reading_final: '精读报告',
      filter_excel: '筛选报告',
      compare_md: '对比结果',
      synthesis_md: '综述结果',
    }[artifactType] || artifactType
  )
}

function jobTypeLabel(jobType: string) {
  return (
    {
      filter: '文献筛选',
      reading_long: '长文本精读',
      reading_quant: '七步精读',
      reading_qual: '四步精读',
      compare: '对比分析',
      synthesis: 'AI 综述',
    }[jobType] || jobType
  )
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function buildDraft(detail: LibraryEntryDetail): EditDraft {
  return {
    title: detail.title,
    authorsText: detail.authors.join(', '),
    yearText: detail.year ? String(detail.year) : '',
    doi: detail.doi || '',
    journal: detail.journal || '',
    abstract: detail.abstract || '',
    keywordsText: detail.keywords.join(', '),
    tagsText: detail.tags.join(', '),
    note: detail.note || '',
    isPinned: detail.is_pinned === 1,
  }
}

export default function LibraryTab({ apiKey }: { apiKey: string }) {
  const [search, setSearch] = useState('')
  const [journalFilter, setJournalFilter] = useState('')
  const [readingStatus, setReadingStatus] = useState('')
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [sortBy, setSortBy] = useState('updated')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [entries, setEntries] = useState<LibraryEntrySummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<LibraryEntryDetail | null>(null)
  const [draft, setDraft] = useState<EditDraft | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [listError, setListError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [expandedTimeline, setExpandedTimeline] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const selectedSummary = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  )

  async function loadEntries(preferredId?: string | null) {
    setListLoading(true)
    setListError('')
    try {
      const params = new URLSearchParams()
      if (search.trim()) params.set('search', search.trim())
      if (journalFilter.trim()) params.set('journal', journalFilter.trim())
      if (readingStatus) params.set('reading_status', readingStatus)
      if (pinnedOnly) params.set('pinned_only', 'true')
      params.set('sort_by', sortBy)
      params.set('sort_order', sortOrder)

      const query = params.toString()
      const response = await fetch(`/api/library/entries${query ? `?${query}` : ''}`)
      const data = await parseJsonOrThrow<LibraryEntrySummary[]>(response)
      setEntries(data)
      const nextId =
        preferredId && data.some((entry) => entry.id === preferredId)
          ? preferredId
          : selectedId && data.some((entry) => entry.id === selectedId)
            ? selectedId
            : data[0]?.id || null
      setSelectedId(nextId)
    } catch (error: any) {
      setListError(error.message || '加载文献库失败。')
      setEntries([])
      setSelectedId(null)
    } finally {
      setListLoading(false)
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selectedIds.size === entries.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(entries.map((e) => e.id)))
    }
  }

  async function handleBatchDelete() {
    if (selectedIds.size === 0) return
    if (!confirm(`确定删除选中的 ${selectedIds.size} 篇文献？此操作不可撤销。`)) return
    try {
      const res = await fetch('/api/library/entries/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_ids: Array.from(selectedIds) }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || '删除失败')
      }
      const data = await res.json()
      setSelectedIds(new Set())
      await loadEntries()
      alert(`已删除 ${data.deleted} 篇文献。`)
    } catch (e: any) {
      alert(`批量删除失败：${e.message || e}`)
    }
  }

  async function loadDetail(entryId: string) {
    setDetailLoading(true)
    setDetailError('')
    setSaveMessage('')
    setExpandedTimeline(false)
    try {
      const response = await fetch(`/api/library/entries/${encodeURIComponent(entryId)}`)
      const data = await parseJsonOrThrow<LibraryEntryDetail>(response)
      setDetail(data)
      setDraft(buildDraft(data))
    } catch (error: any) {
      setDetail(null)
      setDraft(null)
      setDetailError(error.message || '加载文献详情失败。')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadEntries()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readingStatus, pinnedOnly, sortBy, sortOrder])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setDraft(null)
      return
    }
    void loadDetail(selectedId)
  }, [selectedId])

  async function handleSave() {
    if (!detail || !draft) return
    setSaving(true)
    setSaveMessage('')
    try {
      const payload: Record<string, unknown> = {
        title: draft.title.trim() || detail.title,
        authors: splitCsv(draft.authorsText),
        doi: draft.doi,
        journal: draft.journal,
        abstract: draft.abstract,
        keywords: splitCsv(draft.keywordsText),
        tags: splitCsv(draft.tagsText),
        note: draft.note,
        is_pinned: draft.isPinned ? 1 : 0,
      }
      if (draft.yearText.trim()) {
        payload.year = Number(draft.yearText.trim())
      }

      const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const updated = await parseJsonOrThrow<LibraryEntryDetail>(response)
      setDetail(updated)
      setDraft(buildDraft(updated))
      setSaveMessage('保存成功。')
      await loadEntries(updated.id)
    } catch (error: any) {
      setSaveMessage(error.message || '保存失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">我的文献库</h2>
            <p className="mt-1 text-sm text-gray-500">围绕 `bib_entries` 浏览文献、补齐元数据、查看任务时间线。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void loadEntries(selectedId)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:border-emerald-300 hover:text-emerald-700"
              type="button"
            >
              刷新列表
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_140px_auto_auto_auto]">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">搜索标题 / DOI / 期刊</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void loadEntries()
                }
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="例如：difference-in-differences / 10.1234/abc"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">按期刊名称筛选</span>
            <input
              value={journalFilter}
              onChange={(event) => setJournalFilter(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void loadEntries()
                }
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="例如：American Economic Review"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">阅读状态</span>
            <select
              value={readingStatus}
              onChange={(event) => setReadingStatus(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            >
              <option value="">全部状态</option>
              <option value="none">未进入精读</option>
              <option value="has_pdf">已有关联文件</option>
              <option value="reading">精读中</option>
              <option value="read">已完成精读</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">排序方式</span>
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            >
              <option value="updated">更新时间</option>
              <option value="score">筛选评分</option>
              <option value="year">年份</option>
              <option value="journal">期刊</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">排序顺序</span>
            <button
              type="button"
              onClick={() => setSortOrder((v) => (v === 'desc' ? 'asc' : 'desc'))}
              className={`flex w-full items-center justify-center rounded-lg border px-3 py-2 text-sm ${
                sortOrder === 'desc'
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                  : 'border-gray-300 bg-white text-gray-600'
              }`}
            >
              {sortOrder === 'desc' ? '降序 ↓' : '升序 ↑'}
            </button>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">置顶筛选</span>
            <button
              type="button"
              onClick={() => setPinnedOnly((value) => !value)}
              className={`flex w-full items-center justify-center rounded-lg border px-3 py-2 text-sm ${
                pinnedOnly
                  ? 'border-amber-300 bg-amber-50 text-amber-700'
                  : 'border-gray-300 bg-white text-gray-600'
              }`}
            >
              {pinnedOnly ? '只看置顶' : '全部文献'}
            </button>
          </label>

          <button
            onClick={() => void loadEntries()}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            type="button"
          >
            搜索
          </button>
        </div>

        {listError && <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{listError}</div>}
      </div>

      <div className="grid gap-4 2xl:grid-cols-[minmax(380px,0.95fr)_minmax(0,1.05fr)]">
        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div className="flex items-center gap-3">
              {entries.length > 0 && (
                <input
                  type="checkbox"
                  checked={selectedIds.size === entries.length && entries.length > 0}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                  title="全选/取消全选"
                />
              )}
              <div>
                <h3 className="text-sm font-semibold text-gray-800">文献列表</h3>
                <p className="mt-1 text-xs text-gray-400">
                  {listLoading ? '加载中...' : `共 ${entries.length} 篇`}
                  {selectedIds.size > 0 && ` · 已选 ${selectedIds.size} 篇`}
                </p>
              </div>
            </div>
            {selectedIds.size > 0 && (
              <button
                onClick={() => void handleBatchDelete()}
                className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100"
                type="button"
              >
                删除选中 ({selectedIds.size})
              </button>
            )}
          </div>

          <div className="max-h-[70vh] overflow-y-auto 2xl:max-h-[74vh]">
            {entries.length === 0 && !listLoading ? (
              <div className="px-5 py-12 text-center text-sm text-gray-400">当前筛选条件下没有文献记录。</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {entries.map((entry) => (
                  <div
                    key={entry.id}
                    className={`flex items-start gap-2 px-5 py-4 transition-colors ${
                      selectedId === entry.id ? 'bg-emerald-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(entry.id)}
                      onChange={() => toggleSelect(entry.id)}
                      className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                      onClick={(e) => e.stopPropagation()}
                    />
                    <button
                      onClick={() => setSelectedId(entry.id)}
                      className="block w-full text-left"
                      type="button"
                    >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-semibold text-gray-900">{entry.title}</span>
                          {entry.is_pinned === 1 && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                              置顶
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {entry.authors.length > 0 ? entry.authors.join(', ') : '作者待补充'}
                          {entry.year ? ` · ${entry.year}` : ''}
                          {entry.journal ? ` · ${entry.journal}` : ''}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClass(entry.reading_status)}`}>
                            {statusLabel(entry.reading_status)}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${metadataClass(entry.metadata_completeness)}`}
                          >
                            {metadataLabel(entry.metadata_completeness)}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
                            {sourceDbLabel(entry.source_db)}
                          </span>
                        </div>
                      </div>
                      <div className="text-right text-xs text-gray-400">
                        {entry.filter_score != null && (
                          <div className="text-[11px] font-medium text-emerald-600">
                            评分 {entry.filter_score.toFixed(1)}
                          </div>
                        )}
                        <div>{entry.tags.length > 0 ? `${entry.tags.length} 个标签` : '无标签'}</div>
                        <div className="mt-1">{entry.source_file_name || '未绑定源文件'}</div>
                      </div>
                    </div>
                  </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">详情与时间线</h3>
              <p className="mt-1 text-xs text-gray-400">
                {selectedSummary ? `当前查看：${selectedSummary.title}` : '请选择左侧文献'}
              </p>
            </div>
            {detail && (
              <button
                onClick={() => void loadDetail(detail.id)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 hover:border-emerald-300 hover:text-emerald-700"
                type="button"
              >
                刷新详情
              </button>
            )}
          </div>

          <div className="max-h-[70vh] overflow-y-auto px-5 py-4 2xl:max-h-[74vh]">
            {detailLoading ? (
              <div className="py-10 text-sm text-gray-400">详情加载中...</div>
            ) : detailError ? (
              <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{detailError}</div>
            ) : !detail || !draft ? (
              <div className="py-10 text-sm text-gray-400">左侧选择一篇文献后，这里会显示元数据和时间线。</div>
            ) : (
              <div className="space-y-5">
                {detail.metadata_completeness !== 'full' && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    当前文献的元数据完整度为"{metadataLabel(detail.metadata_completeness)}"，建议补齐标题、作者、DOI、摘要和关键词。
                  </div>
                )}

                {(!detail.doi || !detail.journal) && (
                  <div className="mt-4">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">元数据补全</h4>
                    <MetadataMatchPanel
                      entryId={detail.id}
                      apiKey={apiKey}
                      onComplete={() => loadDetail(detail.id)}
                    />
                  </div>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium text-gray-500">标题</span>
                    <input
                      value={draft.title}
                      onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium text-gray-500">作者</span>
                    <input
                      value={draft.authorsText}
                      onChange={(event) => setDraft({ ...draft, authorsText: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                      placeholder="多个作者用逗号分隔"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium text-gray-500">年份</span>
                    <input
                      value={draft.yearText}
                      onChange={(event) => setDraft({ ...draft, yearText: event.target.value.replace(/[^\d]/g, '') })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                      placeholder="例如 2024"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium text-gray-500">DOI</span>
                    <input
                      value={draft.doi}
                      onChange={(event) => setDraft({ ...draft, doi: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    />
                  </label>

                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-gray-500">期刊 / 来源</span>
                    <input
                      value={draft.journal}
                      onChange={(event) => setDraft({ ...draft, journal: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    />
                  </label>

                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-gray-500">关键词</span>
                    <input
                      value={draft.keywordsText}
                      onChange={(event) => setDraft({ ...draft, keywordsText: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                      placeholder="多个关键词用逗号分隔"
                    />
                  </label>

                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-gray-500">标签</span>
                    <input
                      value={draft.tagsText}
                      onChange={(event) => setDraft({ ...draft, tagsText: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                      placeholder="例如：DID, 机制分析, 核心样本"
                    />
                  </label>

                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-gray-500">摘要</span>
                    <textarea
                      value={draft.abstract}
                      onChange={(event) => setDraft({ ...draft, abstract: event.target.value })}
                      rows={5}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    />
                  </label>

                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-xs font-medium text-gray-500">研究备注</span>
                    <textarea
                      value={draft.note}
                      onChange={(event) => setDraft({ ...draft, note: event.target.value })}
                      rows={4}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                      placeholder="记录你的判断、后续待做、关键引用点"
                    />
                  </label>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
                  <div className="space-y-1 text-sm text-gray-600">
                    <div>来源：{sourceDbLabel(detail.source_db)}</div>
                    <div>关联源文件：{detail.source_file_name || '未绑定'}</div>
                    <div>任务时间线：{detail.timeline.length} 条</div>
                  </div>
                  <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                    <input
                      checked={draft.isPinned}
                      onChange={(event) => setDraft({ ...draft, isPinned: event.target.checked })}
                      type="checkbox"
                    />
                    置顶这篇文献
                  </label>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => void handleSave()}
                    disabled={saving}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                    type="button"
                  >
                    {saving ? '保存中...' : '保存元数据'}
                  </button>
                  {saveMessage && (
                    <span className={`text-sm ${saveMessage === '保存成功。' ? 'text-emerald-600' : 'text-red-600'}`}>
                      {saveMessage}
                    </span>
                  )}
                </div>

                <div className="rounded-xl border border-gray-100 bg-slate-50 px-4 py-4">
                  <h4 className="text-sm font-semibold text-gray-800">筛选解析信息</h4>
                  <div className="mt-3 space-y-3">
                    <div>
                      <div className="text-xs font-medium text-gray-500">原始摘要</div>
                      <div className="mt-1 whitespace-pre-wrap rounded-lg bg-white px-3 py-2 text-sm text-gray-700">
                        {detail.abstract || '当前记录暂无摘要。'}
                      </div>
                    </div>

                    {detail.filter_evaluations.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-gray-200 bg-white px-3 py-4 text-sm text-gray-400">
                        当前还没有保存的筛选评估信息。
                      </div>
                    ) : (
                      detail.filter_evaluations.map((evaluation) => (
                        <div key={evaluation.filter_job_id} className="rounded-lg bg-white px-3 py-3 shadow-sm">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                evaluation.passed === 1
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {evaluation.passed === 1 ? '通过筛选' : '未通过筛选'}
                            </span>
                            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
                              评分：{evaluation.score ?? '-'}
                            </span>
                            <span className="text-xs text-gray-400">{formatTime(evaluation.created_at)}</span>
                          </div>
                          <div className="mt-3">
                            <div className="text-xs font-medium text-gray-500">AI 评估结果</div>
                            <div className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-gray-700">
                              {evaluation.reason || '当前未记录 AI 评估说明。'}
                            </div>
                          </div>
                          <div className="mt-3">
                            <div className="text-xs font-medium text-gray-500">摘要翻译</div>
                            <div className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-gray-700">
                              {evaluation.abstract_translation || '当前筛选产物中暂无摘要翻译。重新运行筛选后会自动保留。'}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="border-t border-gray-100 pt-4">
                  <h4 className="text-sm font-semibold text-gray-800">关联任务时间线</h4>
                  <div className="mt-3 space-y-3">
                    {detail.timeline.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-200 px-4 py-6 text-sm text-gray-400">
                        这篇文献还没有关联的筛选、精读、对比或综述任务。
                      </div>
                    ) : (() => {
                      const readingItems = detail.timeline.filter(t => t.job_type?.startsWith('reading_'))
                      const otherItems = detail.timeline.filter(t => !t.job_type?.startsWith('reading_'))
                      const displayedReading = expandedTimeline ? readingItems : readingItems.slice(0, 1)
                      const renderItem = (item: LibraryTimelineItem) => (
                        <div key={item.job_id} className="rounded-xl border border-gray-200 bg-white p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <div className="text-sm font-semibold text-gray-900">{jobTypeLabel(item.job_type)}</div>
                              <div className="mt-1 text-xs text-gray-500">
                                创建于 {formatTime(item.created_at)} {item.finished_at ? `· 完成于 ${formatTime(item.finished_at)}` : ''}
                              </div>
                            </div>
                            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                              {item.status}
                            </span>
                          </div>
                          <div className="mt-3 space-y-2">
                            {item.artifacts.length === 0 ? (
                              <div className="text-xs text-gray-400">该任务当前没有关联产物文件。</div>
                            ) : (
                              item.artifacts.map((artifact) => (
                                <div
                                  key={artifact.id}
                                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2"
                                >
                                  <div className="min-w-0">
                                    <div className="truncate text-sm text-gray-800">{artifact.filename}</div>
                                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                                      <span>{artifactTypeLabel(artifact.artifact_type)}</span>
                                      <span>{formatTime(artifact.created_at)}</span>
                                    </div>
                                  </div>
                                  <button
                                    type="button"
                                    className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                                    onClick={() =>
                                      downloadWithAuth(
                                        `/api/download/${encodeURIComponent(artifact.storage_path)}`,
                                        artifact.filename,
                                      ).catch((error) => alert(error.message))
                                    }
                                  >
                                    下载
                                  </button>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      )
                      return (
                        <>
                          {displayedReading.map(renderItem)}
                          {readingItems.length > 1 && !expandedTimeline && (
                            <button
                              onClick={() => setExpandedTimeline(true)}
                              className="text-indigo-600 text-sm hover:underline mt-2"
                            >
                              查看更多 {readingItems.length - 1} 条精读记录
                            </button>
                          )}
                          {expandedTimeline && readingItems.length > 1 && (
                            <button
                              onClick={() => setExpandedTimeline(false)}
                              className="text-gray-500 text-sm hover:underline mt-2"
                            >
                              收起
                            </button>
                          )}
                          {otherItems.map(renderItem)}
                        </>
                      )
                    })()}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
