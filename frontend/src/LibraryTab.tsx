import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { marked } from 'marked'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'
import MetadataMatchPanel from './MetadataMatchPanel'
import RefFormatModal from './components/RefFormatModal'

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
  source_file_type: 'pdf' | 'markdown' | string | null
  markdown_source_file_id: string | null
  markdown_source_file_name: string | null
  language: 'en' | 'zh' | 'other' | null
  tags: string[]
  note: string | null
  filter_score: number | null
  has_translation: boolean
}

type LibraryEntryPageResponse = {
  items: LibraryEntrySummary[]
  total: number
  page: number
  page_size: number
  has_more: boolean
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
  abstract_cn: string | null
  keywords: string[]
  timeline: LibraryTimelineItem[]
  filter_evaluations: LibraryFilterEvaluation[]
  ai_comments: LibraryAiComment[]
  attachments: AttachmentSummary[]
}

type AttachmentSummary = {
  id: string
  file_id: string
  label: string
  sort_order: number
  file_name: string | null
  file_size: number | null
  created_at: string | null
}

type LibraryFilterEvaluation = {
  filter_job_id: string
  passed: number
  score: number | null
  reason: string | null
  abstract_translation: string | null
  created_at: string | null
}

type LibraryAiComment = {
  id: string
  source_id: string
  question: string | null
  note: string
  created_at: string | null
  updated_at: string | null
}

type FullTextCandidate = {
  url: string
  source: string
  version: string
  kind: string
  label: string
  confidence: number
}

type FullTextLookupResponse = {
  status: 'attached' | 'landing_only' | 'search_only' | string
  message: string
  attached_file_id: string | null
  attached_file_name: string | null
  attached_source_url: string | null
  doi: string | null
  pdf_candidates: FullTextCandidate[]
  landing_pages: FullTextCandidate[]
  working_paper_searches: FullTextCandidate[]
  errors: string[]
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
  language: string
}

type LibraryChatScope = 'auto' | 'library' | 'previous_results'

const LIBRARY_PAGE_SIZE = 100

type LibraryChatCitation = {
  from_id: string
  to_id: string | null
  from_title: string
  to_title: string
}

type LibraryChatIntent = {
  scope: Exclude<LibraryChatScope, 'auto'>
  core_keywords: string[]
  expanded_keywords: string[]
  journal: string | null
  year_from: number | null
  year_to: number | null
  authors: string[]
  tag_action: {
    type: 'add_tags' | 'remove_tags'
    tags: string[]
  } | null
}

type LibraryChatActionProposal = {
  type: 'add_tags' | 'remove_tags'
  tags: string[]
  entryIds: string[]
  entryTitles: string[]
  count: number
  scope: Exclude<LibraryChatScope, 'auto'>
  journal: string | null
  status: 'pending' | 'running' | 'done' | 'cancelled' | 'error'
  message: string
}

type LibraryChatTurn = {
  id: string
  question: string
  report: string
  entryIds: string[]
  entryTitles: string[]
  keywords: string[]
  resultCount: number
  scope: Exclude<LibraryChatScope, 'auto'> | null
  intent: LibraryChatIntent | null
  citations: LibraryChatCitation[]
  actionProposal: LibraryChatActionProposal | null
  commentSaveStatus: 'idle' | 'saving' | 'done' | 'error'
  commentSaveMessage: string
  historySaveStatus: 'idle' | 'saving' | 'done' | 'error'
  historySaveMessage: string
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

function markdownHtml(raw: string, entryCount = 0): string {
  const reportWithEntryLinks = (raw || '').replace(/\[(\d+)\]/g, (label, rawNumber) => {
    const entryNumber = Number(rawNumber)
    if (!Number.isInteger(entryNumber) || entryNumber < 1 || entryNumber > entryCount) {
      return label
    }
    return `<button type="button" data-chat-entry-number="${entryNumber}" title="定位到文献列表">[${entryNumber}]</button>`
  })
  let html = marked.parse(reportWithEntryLinks, { async: false }) as string
  html = html.replace(/<table>/g, '<div class="overflow-x-auto"><table>')
  html = html.replace(/<\/table>/g, '</table></div>')
  return html
}

function updateLastChatTurn(
  turns: LibraryChatTurn[],
  turnId: string,
  update: (turn: LibraryChatTurn) => LibraryChatTurn,
) {
  return turns.map((turn) => (turn.id === turnId ? update(turn) : turn))
}

function createClientId(prefix: string) {
  const randomUUID = globalThis.crypto?.randomUUID
  if (typeof randomUUID === 'function') {
    return randomUUID.call(globalThis.crypto)
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function languageLabel(language: LibraryEntrySummary['language']) {
  if (!language) return '未标注语言'
  return {
    en: '英文',
    zh: '中文',
    other: '其他语言',
  }[language]
}

function languageClass(language: LibraryEntrySummary['language']) {
  if (!language) return 'bg-rose-100 text-rose-700'
  return {
    en: 'bg-indigo-100 text-indigo-700',
    zh: 'bg-teal-100 text-teal-700',
    other: 'bg-slate-100 text-slate-700',
  }[language]
}

function sourceFileTypeLabel(fileType: LibraryEntrySummary['source_file_type']) {
  return (
    {
      pdf: 'PDF 原文',
      markdown: 'Markdown 原文',
    }[fileType || ''] || '未绑定原文'
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

function buildCnkiTitleSearchUrl(title: string) {
  const query = title.trim()
  const params = new URLSearchParams({
    kw: query,
    korder: 'TI',
  })
  return `https://kns.cnki.net/kns8s/defaultresult/index?${params.toString()}`
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
    language: detail.language || '',
  }
}

export default function LibraryTab({ apiKey }: { apiKey: string }) {
  const navigate = useNavigate()
  const markdownInputRef = useRef<HTMLInputElement | null>(null)
  const [search, setSearch] = useState('')
  const [journalFilter, setJournalFilter] = useState('')
  const [tagOptions, setTagOptions] = useState<string[]>([])
  const [tagFilterQuery, setTagFilterQuery] = useState('')
  const [tagFilters, setTagFilters] = useState<string[]>([])
  const [tagFilterOpen, setTagFilterOpen] = useState(false)
  const [readingStatus, setReadingStatus] = useState('')
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [sortBy, setSortBy] = useState('updated')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [entries, setEntries] = useState<LibraryEntrySummary[]>([])
  const [totalEntries, setTotalEntries] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [hasMorePages, setHasMorePages] = useState(false)
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
  const [refFormatOpen, setRefFormatOpen] = useState(false)
  const [editingAiCommentId, setEditingAiCommentId] = useState<string | null>(null)
  const [editingAiCommentText, setEditingAiCommentText] = useState('')
  const [aiCommentBusyId, setAiCommentBusyId] = useState<string | null>(null)
  const [aiCommentMessage, setAiCommentMessage] = useState('')
  const [batchTagsText, setBatchTagsText] = useState('')
  const [batchTagsBusy, setBatchTagsBusy] = useState(false)
  const [batchTagsMessage, setBatchTagsMessage] = useState('')
  const [translating, setTranslating] = useState(false)
  const [translateProgress, setTranslateProgress] = useState('')
  const [markdownUploading, setMarkdownUploading] = useState(false)
  const [attachmentUploading, setAttachmentUploading] = useState(false)
  const attachmentInputRef = useRef<HTMLInputElement | null>(null)
  const [fulltextSearching, setFulltextSearching] = useState(false)
  const [fulltextResult, setFulltextResult] = useState<FullTextLookupResponse | null>(null)
  // WOS 搜索：需校园网，仅本地打包版启用
  // const [wosSearching, setWosSearching] = useState(false)

  const [chatOpen, setChatOpen] = useState(false)
  const [chatQuestion, setChatQuestion] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [chatScopeMode, setChatScopeMode] = useState<LibraryChatScope>('auto')
  const [chatTurns, setChatTurns] = useState<LibraryChatTurn[]>([])
  const [chatFilteredIds, setChatFilteredIds] = useState<string[] | null>(null)
  const [pendingChatEntryId, setPendingChatEntryId] = useState<string | null>(null)

  const selectedSummary = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  )
  const hasMarkdownReaderSource = Boolean(
    detail?.markdown_source_file_id || detail?.source_file_type === 'markdown',
  )
  const hasTranslatedReaderSource = Boolean(
    detail?.timeline.some((item) =>
      item.status === 'success' &&
      item.artifacts.some((artifact) => artifact.artifact_type === 'translation_md'),
    ),
  )
  const hasAttachmentReaderSource = Boolean(detail?.attachments && detail.attachments.length > 0)
  const readerDefaultView = hasMarkdownReaderSource ? 'original' : hasTranslatedReaderSource ? 'translated' : hasAttachmentReaderSource ? `attachment:${detail?.attachments?.[0]?.file_id}` : 'original'
  const chatEntryNumberById = useMemo(
    () => new Map((chatFilteredIds || []).map((entryId, index) => [entryId, index + 1])),
    [chatFilteredIds],
  )
  const matchingTagOptions = useMemo(() => {
    const query = tagFilterQuery.trim().toLocaleLowerCase()
    return tagOptions.filter((tag) => {
      if (tagFilters.includes(tag)) return false
      return !query || tag.toLocaleLowerCase().includes(query)
    })
  }, [tagFilterQuery, tagFilters, tagOptions])

  async function loadEntries(
    preferredId?: string | null,
    filteredIds = chatFilteredIds,
    filteredTags = tagFilters,
    targetPage = currentPage,
  ) {
    setListLoading(true)
    setListError('')
    try {
      const params = new URLSearchParams()
      if (search.trim()) params.set('search', search.trim())
      if (journalFilter.trim()) params.set('journal', journalFilter.trim())
      if (filteredTags.length > 0) params.set('tags', filteredTags.join(','))
      if (readingStatus) params.set('reading_status', readingStatus)
      if (pinnedOnly) params.set('pinned_only', 'true')
      params.set('sort_by', sortBy)
      params.set('sort_order', sortOrder)

      const query = params.toString()
      const response =
        filteredIds === null
          ? await fetch(`/api/library/entries/page?${query ? `${query}&` : ''}page=${targetPage}&page_size=${LIBRARY_PAGE_SIZE}`)
          : await fetch(`/api/library/entries/by-ids${query ? `?${query}` : ''}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ entry_ids: filteredIds }),
            })
      if (filteredIds !== null && response.status === 405) {
        throw new Error('当前后端尚未加载 AI 文献列表筛选接口，请重启后端后重试。')
      }
      const data =
        filteredIds === null
          ? await parseJsonOrThrow<LibraryEntryPageResponse>(response)
          : await parseJsonOrThrow<LibraryEntrySummary[]>(response)
      const nextEntries = Array.isArray(data) ? data : data.items
      setEntries(nextEntries)
      setTotalEntries(Array.isArray(data) ? data.length : data.total)
      setCurrentPage(Array.isArray(data) ? 1 : data.page)
      setHasMorePages(Array.isArray(data) ? false : data.has_more)
      const nextId =
        preferredId && nextEntries.some((entry) => entry.id === preferredId)
          ? preferredId
          : selectedId && nextEntries.some((entry) => entry.id === selectedId)
            ? selectedId
            : nextEntries[0]?.id || null
      setSelectedId(nextId)
    } catch (error: unknown) {
      setListError(error instanceof Error ? error.message : '加载文献库失败。')
      setEntries([])
      setTotalEntries(0)
      setCurrentPage(1)
      setHasMorePages(false)
      setSelectedId(null)
    } finally {
      setListLoading(false)
    }
  }

  async function loadTagOptions() {
    try {
      const response = await fetch('/api/library/tags')
      setTagOptions(await parseJsonOrThrow<string[]>(response))
    } catch {
      setTagOptions([])
    }
  }

  function selectTagFilter(tag: string) {
    const nextTags = [...tagFilters, tag]
    setTagFilters(nextTags)
    setTagFilterQuery('')
    setTagFilterOpen(false)
    void loadEntries(undefined, chatFilteredIds, nextTags, 1)
  }

  function removeTagFilter(tag: string) {
    const nextTags = tagFilters.filter((item) => item !== tag)
    setTagFilters(nextTags)
    void loadEntries(undefined, chatFilteredIds, nextTags, 1)
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

  async function handleBatchTranslate() {
    if (!apiKey) {
      alert('请先在设置中配置 DeepSeek API Key')
      return
    }
    const ids = Array.from(selectedIds)
    if (!confirm(`确认翻译 ${ids.length} 条英文摘要？将调用 DeepSeek API。`)) return

    setTranslating(true)
    setTranslateProgress('提交翻译任务...')
    try {
      const res = await fetch('/api/library/entries/batch-translate-abstracts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_ids: ids, api_key: apiKey }),
      })
      if (!res.ok) throw new Error('Failed to start translation')
      const { job_id } = await res.json()

      const poll = setInterval(async () => {
        try {
          const sr = await fetch(`/api/library/translate-job/${job_id}/status`)
          const sd = await sr.json()
          setTranslateProgress(sd.current_stage || `${sd.progress}%`)
          if (sd.status === 'success' || sd.status === 'failed') {
            clearInterval(poll)
            setTranslating(false)
            if (sd.status === 'success') {
              const r = sd.result || {}
              alert(`翻译完成：${r.translated || 0} 条成功，${r.failed || 0} 条失败`)
            } else {
              alert('翻译任务失败：' + (sd.error || '未知错误'))
            }
            loadEntries()
          }
        } catch {
          clearInterval(poll)
          setTranslating(false)
        }
      }, 2000)
    } catch (error: unknown) {
      alert('翻译失败: ' + (error instanceof Error ? error.message : String(error)))
      setTranslating(false)
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
    } catch (error: unknown) {
      alert(`批量删除失败：${error instanceof Error ? error.message : String(error)}`)
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
    } catch (error: unknown) {
      setDetail(null)
      setDraft(null)
      setDetailError(error instanceof Error ? error.message : '加载文献详情失败。')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    void loadEntries(undefined, chatFilteredIds, tagFilters, 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readingStatus, pinnedOnly, sortBy, sortOrder])

  useEffect(() => {
    void loadTagOptions()
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setDraft(null)
      return
    }
    void loadDetail(selectedId)
  }, [selectedId])

  useEffect(() => {
    if (!pendingChatEntryId || !entries.some((entry) => entry.id === pendingChatEntryId)) {
      return
    }

    const frame = window.requestAnimationFrame(() => {
      document
        .getElementById(`library-entry-${pendingChatEntryId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setPendingChatEntryId(null)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [entries, pendingChatEntryId])

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
        language: draft.language,
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
      void loadTagOptions()
    } catch (error: unknown) {
      setSaveMessage(error instanceof Error ? error.message : '保存失败。')
    } finally {
      setSaving(false)
    }
  }

  async function handleMarkdownUpload(file: File | null) {
    if (!detail || !file) return
    setMarkdownUploading(true)
    setSaveMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/markdown`, {
        method: 'POST',
        body: formData,
      })
      const updated = await parseJsonOrThrow<LibraryEntryDetail>(response)
      setDetail(updated)
      setDraft(buildDraft(updated))
      setSaveMessage('Markdown 原文已挂载。')
      await loadEntries(updated.id)
    } catch (error: unknown) {
      setSaveMessage(error instanceof Error ? error.message : 'Markdown 原文挂载失败。')
    } finally {
      setMarkdownUploading(false)
    }
  }

  async function handleAttachmentUpload(file: File | null) {
    if (!detail || !file) return
    setAttachmentUploading(true)
    setSaveMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/attachments`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || '附件上传失败。')
      }
      const attachments: AttachmentSummary[] = await response.json()
      setDetail((prev) => prev ? { ...prev, attachments } : prev)
      setSaveMessage('附件已添加。')
    } catch (error: unknown) {
      setSaveMessage(error instanceof Error ? error.message : '附件上传失败。')
    } finally {
      setAttachmentUploading(false)
    }
  }

  async function handleAttachmentDelete(attachmentId: string) {
    if (!detail) return
    try {
      const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/attachments/${encodeURIComponent(attachmentId)}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || '删除失败。')
      }
      setDetail((prev) => prev ? { ...prev, attachments: prev.attachments.filter((a) => a.id !== attachmentId) } : prev)
      setSaveMessage('附件已删除。')
    } catch (error: unknown) {
      setSaveMessage(error instanceof Error ? error.message : '删除附件失败。')
    }
  }

  function openCnkiTitleSearch(entry: LibraryEntrySummary | LibraryEntryDetail) {
    const url = buildCnkiTitleSearchUrl(entry.title)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  // WOS 搜索：需校园网，仅本地打包版启用
  // async function handleWosSearch() {
  //   if (!detail || wosSearching) return
  //   setWosSearching(true)
  //   try {
  //     const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/wos-search`, {
  //       method: 'POST',
  //     })
  //     const data = await parseJsonOrThrow<{ url: string }>(response)
  //     window.open(data.url, '_blank', 'noopener,noreferrer')
  //   } catch (error: unknown) {
  //     alert(`WOS 搜索失败：${error instanceof Error ? error.message : String(error)}`)
  //   } finally {
  //     setWosSearching(false)
  //   }
  // }

  async function handleFullTextSearch() {
    if (!detail || fulltextSearching) return
    setFulltextSearching(true)
    setSaveMessage('')
    try {
      const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/fulltext-search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const data = await parseJsonOrThrow<FullTextLookupResponse>(response)

      if (data.status === 'attached') {
        setSaveMessage(data.message)
        await loadEntries(detail.id)
        await loadDetail(detail.id)
        if (data.attached_source_url) {
          console.info('Full text source:', data.attached_source_url)
        }
        return
      }

      setFulltextResult(data)
    } catch (error: unknown) {
      alert(`英文原文检索失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setFulltextSearching(false)
    }
  }

  async function handleBatchTags(operation: 'add' | 'remove') {
    const tags = splitCsv(batchTagsText)
    if (selectedIds.size === 0 || tags.length === 0 || batchTagsBusy) return

    setBatchTagsBusy(true)
    setBatchTagsMessage('')
    try {
      const response = await fetch('/api/library/entries/batch-tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entry_ids: Array.from(selectedIds),
          add_tags: operation === 'add' ? tags : [],
          remove_tags: operation === 'remove' ? tags : [],
        }),
      })
      const data = await parseJsonOrThrow<{
        matched: number
        changed: number
        not_found: number
      }>(response)
      setBatchTagsMessage(
        operation === 'add'
          ? `已为 ${data.changed} 篇文献添加标签。`
          : `已从 ${data.changed} 篇文献移除标签。`,
      )
      await loadEntries(selectedId)
      void loadTagOptions()
      if (selectedId) void loadDetail(selectedId)
    } catch (error: unknown) {
      setBatchTagsMessage(error instanceof Error ? error.message : '批量更新标签失败。')
    } finally {
      setBatchTagsBusy(false)
    }
  }

  async function handleChatSubmit() {
    const question = chatQuestion.trim()
    if (!question || chatLoading) return

    const history = chatTurns.map((turn) => ({
      question: turn.question,
      report: turn.report,
      entry_ids: turn.entryIds,
      entry_titles: turn.entryTitles,
      keywords: turn.keywords,
      result_count: turn.resultCount,
    }))
    const turnId = createClientId('library-chat-turn')
    const nextTurn: LibraryChatTurn = {
      id: turnId,
      question,
      report: '',
      entryIds: [],
      entryTitles: [],
      keywords: [],
      resultCount: 0,
      scope: null,
      intent: null,
      citations: [],
      actionProposal: null,
      commentSaveStatus: 'idle',
      commentSaveMessage: '',
      historySaveStatus: 'idle',
      historySaveMessage: '',
    }
    setChatTurns((turns) => [...turns, nextTurn])
    setChatQuestion('')
    setChatError('')
    setChatLoading(true)

    try {
      const response = await fetch('/api/library/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          api_key: apiKey,
          history,
          scope_mode: chatScopeMode,
        }),
      })
      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as {
          detail?: unknown
          message?: unknown
        }
        const detail =
          typeof errorData.detail === 'string'
            ? errorData.detail
            : typeof errorData.message === 'string'
              ? errorData.message
              : 'AI 查询请求失败。'
        throw new Error(detail)
      }
      if (!response.body) throw new Error('AI 查询未返回流式内容。')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const handleEvent = (event: string, data: Record<string, unknown>) => {
        const scope =
          data.scope === 'library' || data.scope === 'previous_results'
            ? data.scope
            : null
        if (event === 'intent') {
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              intent: data as LibraryChatIntent,
              scope: scope || turn.scope,
            })),
          )
        } else if (event === 'results') {
          const entryIds = Array.isArray(data.entry_ids) ? data.entry_ids : []
          const entryTitles = Array.isArray(data.entry_titles) ? data.entry_titles : []
          setChatFilteredIds(entryIds)
          void loadEntries(undefined, entryIds)
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              entryIds,
              entryTitles,
              resultCount: Number(data.count || 0),
              scope: scope || turn.scope,
            })),
          )
        } else if (event === 'citations') {
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              citations: Array.isArray(data.links) ? data.links : [],
            })),
          )
        } else if (event === 'action_proposal') {
          const actionType =
            data.type === 'add_tags' || data.type === 'remove_tags' ? data.type : null
          if (!actionType) return
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              actionProposal: {
                type: actionType,
                tags: Array.isArray(data.tags) ? data.tags : [],
                entryIds: Array.isArray(data.entry_ids) ? data.entry_ids : [],
                entryTitles: Array.isArray(data.entry_titles) ? data.entry_titles : [],
                count: Number(data.count || 0),
                scope:
                  data.scope === 'previous_results' ? 'previous_results' : 'library',
                journal: typeof data.journal === 'string' ? data.journal : null,
                status: 'pending',
                message: '',
              },
            })),
          )
        } else if (event === 'report') {
          const content = typeof data.content === 'string' ? data.content : ''
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              report: turn.report + content,
            })),
          )
        } else if (event === 'done') {
          setChatTurns((turns) =>
            updateLastChatTurn(turns, turnId, (turn) => ({
              ...turn,
              keywords: Array.isArray(data.keywords) ? data.keywords : turn.keywords,
              scope: scope || turn.scope,
            })),
          )
        } else if (event === 'error') {
          throw new Error(typeof data.message === 'string' ? data.message : 'AI 查询失败。')
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''
        for (const block of blocks) {
          const lines = block.split('\n')
          const event = lines.find((line) => line.startsWith('event: '))?.slice(7).trim()
          const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6)
          if (event && dataLine) {
            handleEvent(event, JSON.parse(dataLine) as Record<string, unknown>)
          }
        }
      }
    } catch (error: unknown) {
      setChatError(error instanceof Error ? error.message : 'AI 查询失败。')
    } finally {
      setChatLoading(false)
    }
  }

  function clearChat() {
    setChatTurns([])
    setChatFilteredIds(null)
    setChatError('')
    setChatQuestion('')
    void loadEntries(undefined, null)
  }

  function focusReportEntry(turn: LibraryChatTurn, entryNumber: number) {
    const entryId = turn.entryIds[entryNumber - 1]
    if (!entryId) return

    setChatFilteredIds(turn.entryIds)
    setSelectedId(entryId)
    setPendingChatEntryId(entryId)
    void loadEntries(entryId, turn.entryIds)
  }

  function handleReportClick(event: ReactMouseEvent<HTMLDivElement>, turn: LibraryChatTurn) {
    const target = event.target instanceof Element
      ? event.target.closest<HTMLButtonElement>('button[data-chat-entry-number]')
      : null
    if (!target) return

    const entryNumber = Number(target.dataset.chatEntryNumber)
    if (!Number.isInteger(entryNumber)) return
    focusReportEntry(turn, entryNumber)
  }

  async function executeChatProposal(turnId: string, proposal: LibraryChatActionProposal) {
    if (proposal.status !== 'pending' || proposal.count === 0) return

    setChatTurns((turns) =>
      updateLastChatTurn(turns, turnId, (turn) => ({
        ...turn,
        actionProposal: turn.actionProposal
          ? { ...turn.actionProposal, status: 'running', message: '' }
          : null,
      })),
    )
    try {
      const response = await fetch('/api/library/entries/batch-tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entry_ids: proposal.entryIds,
          add_tags: proposal.type === 'add_tags' ? proposal.tags : [],
          remove_tags: proposal.type === 'remove_tags' ? proposal.tags : [],
        }),
      })
      const data = await parseJsonOrThrow<{ changed: number }>(response)
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (turn) => ({
          ...turn,
          actionProposal: turn.actionProposal
            ? {
                ...turn.actionProposal,
                status: 'done',
                message:
                  proposal.type === 'add_tags'
                    ? `已为 ${data.changed} 篇文献添加标签。`
                    : `已从 ${data.changed} 篇文献移除标签。`,
              }
            : null,
        })),
      )
      setChatFilteredIds(proposal.entryIds)
      await loadEntries(selectedId, proposal.entryIds)
      void loadTagOptions()
      if (selectedId) void loadDetail(selectedId)
    } catch (error: unknown) {
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (turn) => ({
          ...turn,
          actionProposal: turn.actionProposal
            ? {
                ...turn.actionProposal,
                status: 'error',
                message: error instanceof Error ? error.message : '标签操作执行失败。',
              }
            : null,
        })),
      )
    }
  }

  function cancelChatProposal(turnId: string) {
    setChatTurns((turns) =>
      updateLastChatTurn(turns, turnId, (turn) => ({
        ...turn,
        actionProposal: turn.actionProposal
          ? { ...turn.actionProposal, status: 'cancelled', message: '已取消。' }
          : null,
      })),
    )
  }

  async function saveChatTurnComments(turnId: string) {
    const turnIndex = chatTurns.findIndex((turn) => turn.id === turnId)
    const turn = turnIndex >= 0 ? chatTurns[turnIndex] : null
    if (!turn || !turn.report.trim() || turn.entryIds.length === 0 || turn.commentSaveStatus === 'saving') {
      return
    }

    setChatTurns((turns) =>
      updateLastChatTurn(turns, turnId, (item) => ({
        ...item,
        commentSaveStatus: 'saving',
        commentSaveMessage: '',
      })),
    )
    try {
      const history = chatTurns.slice(0, turnIndex).map((item) => ({
        question: item.question,
        report: item.report,
        entry_ids: item.entryIds,
        entry_titles: item.entryTitles,
        keywords: item.keywords,
        result_count: item.resultCount,
      }))
      const response = await fetch('/api/library/chat/comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          turn_id: turn.id,
          question: turn.question,
          report: turn.report,
          entry_ids: turn.entryIds,
          history,
          api_key: apiKey,
        }),
      })
      const data = await parseJsonOrThrow<{
        matched: number
        saved: number
        skipped: number
      }>(response)
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (item) => ({
          ...item,
          commentSaveStatus: 'done',
          commentSaveMessage:
            data.skipped > 0
              ? `已保存 ${data.saved} 条 AI 点评，跳过 ${data.skipped} 篇不适合写入的点评。`
              : `已保存本轮 ${data.saved} 条 AI 点评。`,
        })),
      )
      if (selectedId && turn.entryIds.includes(selectedId)) {
        void loadDetail(selectedId)
      }
    } catch (error: unknown) {
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (item) => ({
          ...item,
          commentSaveStatus: 'error',
          commentSaveMessage: error instanceof Error ? error.message : '保存本轮 AI 点评失败。',
        })),
      )
    }
  }

  async function saveChatTurnReport(turnId: string) {
    const turn = chatTurns.find((t) => t.id === turnId)
    if (!turn || !turn.report.trim() || turn.historySaveStatus === 'saving') return

    setChatTurns((turns) =>
      updateLastChatTurn(turns, turnId, (item) => ({
        ...item,
        historySaveStatus: 'saving',
        historySaveMessage: '',
      })),
    )
    try {
      const response = await fetch('/api/history/library-chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: turn.question,
          report: turn.report,
          entry_ids: turn.entryIds,
          entry_titles: turn.entryTitles,
          keywords: turn.keywords,
        }),
      })
      const data = await parseJsonOrThrow<{ success: boolean; filename: string }>(response)
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (item) => ({
          ...item,
          historySaveStatus: 'done',
          historySaveMessage: `已保存到历史记录：${data.filename}`,
        })),
      )
    } catch (error: unknown) {
      setChatTurns((turns) =>
        updateLastChatTurn(turns, turnId, (item) => ({
          ...item,
          historySaveStatus: 'error',
          historySaveMessage: error instanceof Error ? error.message : '保存到历史记录失败。',
        })),
      )
    }
  }

  function startEditAiComment(comment: LibraryAiComment) {
    setEditingAiCommentId(comment.id)
    setEditingAiCommentText(comment.note)
    setAiCommentMessage('')
  }

  async function updateAiComment(commentId: string) {
    const note = editingAiCommentText.trim()
    if (!note || aiCommentBusyId) return

    setAiCommentBusyId(commentId)
    setAiCommentMessage('')
    try {
      await parseJsonOrThrow<LibraryAiComment>(
        await fetch(`/api/library/ai-comments/${encodeURIComponent(commentId)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note }),
        }),
      )
      setEditingAiCommentId(null)
      setEditingAiCommentText('')
      setAiCommentMessage('AI 点评已更新。')
      if (selectedId) await loadDetail(selectedId)
    } catch (error: unknown) {
      setAiCommentMessage(error instanceof Error ? error.message : '更新 AI 点评失败。')
    } finally {
      setAiCommentBusyId(null)
    }
  }

  async function deleteAiComment(commentId: string) {
    if (aiCommentBusyId || !confirm('确定删除这条 AI 点评吗？')) return

    setAiCommentBusyId(commentId)
    setAiCommentMessage('')
    try {
      await parseJsonOrThrow<{ ok: boolean }>(
        await fetch(`/api/library/ai-comments/${encodeURIComponent(commentId)}`, {
          method: 'DELETE',
        }),
      )
      if (editingAiCommentId === commentId) {
        setEditingAiCommentId(null)
        setEditingAiCommentText('')
      }
      setAiCommentMessage('AI 点评已删除。')
      if (selectedId) await loadDetail(selectedId)
    } catch (error: unknown) {
      setAiCommentMessage(error instanceof Error ? error.message : '删除 AI 点评失败。')
    } finally {
      setAiCommentBusyId(null)
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

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_140px_auto_auto_auto]">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-500">搜索标题 / DOI / 期刊</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void loadEntries(undefined, chatFilteredIds, tagFilters, 1)
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
                  void loadEntries(undefined, chatFilteredIds, tagFilters, 1)
                }
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="例如：American Economic Review"
            />
          </label>

          <div className="relative block">
            <span className="mb-1 block text-xs font-medium text-gray-500">按标签筛选</span>
            <div className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 focus-within:border-emerald-500">
              {tagFilters.length > 0 && (
                <div className="mb-1 flex flex-wrap gap-1">
                  {tagFilters.map((tag) => (
                    <span
                      key={`tag-filter-${tag}`}
                      className="inline-flex items-center gap-1 rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700"
                    >
                      #{tag}
                      <button
                        type="button"
                        onClick={() => removeTagFilter(tag)}
                        className="text-violet-400 hover:text-violet-700"
                        title="移除筛选标签"
                      >
                        x
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <input
                value={tagFilterQuery}
                onChange={(event) => {
                  setTagFilterQuery(event.target.value)
                  setTagFilterOpen(true)
                }}
                onFocus={() => setTagFilterOpen(true)}
                onBlur={() => window.setTimeout(() => setTagFilterOpen(false), 120)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && matchingTagOptions[0]) {
                    event.preventDefault()
                    selectTagFilter(matchingTagOptions[0])
                  }
                  if (event.key === 'Escape') setTagFilterOpen(false)
                }}
                className="w-full px-1 py-0.5 text-sm focus:outline-none"
                placeholder={tagFilters.length > 0 ? '继续搜索标签' : '搜索或选择标签'}
              />
            </div>
            {tagFilterOpen && (
              <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white p-1 shadow-lg">
                {matchingTagOptions.length > 0 ? (
                  matchingTagOptions.slice(0, 40).map((tag) => (
                    <button
                      key={`tag-option-${tag}`}
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => selectTagFilter(tag)}
                      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm text-gray-700 hover:bg-violet-50 hover:text-violet-700"
                    >
                      <span className="truncate">#{tag}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-2 py-2 text-xs text-gray-400">没有匹配标签</div>
                )}
              </div>
            )}
          </div>

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
                  {listLoading ? '加载中...' : `共 ${totalEntries} 篇`}
                  {chatFilteredIds === null && totalEntries > 0 && ` · 第 ${currentPage} 页`}
                  {selectedIds.size > 0 && ` · 已选 ${selectedIds.size} 篇`}
                </p>
              </div>
            </div>
            {selectedIds.size > 0 && (
              <div className="flex flex-wrap items-center justify-end gap-2">
                <label className="min-w-[160px]">
                  <span className="sr-only">批量标签</span>
                  <input
                    value={batchTagsText}
                    onChange={(event) => setBatchTagsText(event.target.value)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 focus:border-emerald-400 focus:outline-none"
                    placeholder="批量标签，逗号分隔"
                  />
                </label>
                <button
                  onClick={() => void handleBatchTags('add')}
                  disabled={batchTagsBusy || splitCsv(batchTagsText).length === 0}
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-40"
                  type="button"
                >
                  加标签
                </button>
                <button
                  onClick={() => void handleBatchTags('remove')}
                  disabled={batchTagsBusy || splitCsv(batchTagsText).length === 0}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-amber-200 hover:text-amber-700 disabled:opacity-40"
                  type="button"
                >
                  删标签
                </button>
                <button
                  onClick={() => void handleBatchTranslate()}
                  disabled={translating}
                  className="rounded-lg border border-purple-300 bg-purple-50 px-3 py-1.5 text-xs font-medium text-purple-700 hover:bg-purple-100 disabled:opacity-40"
                  type="button"
                >
                  {translating ? translateProgress : '翻译摘要'}
                </button>
                <button
                  onClick={() => setRefFormatOpen(true)}
                  className="rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700 hover:bg-sky-100"
                  type="button"
                >
                  生成参考文献目录
                </button>
                <button
                  onClick={() => void handleBatchDelete()}
                  className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100"
                  type="button"
                >
                  删除选中 ({selectedIds.size})
                </button>
              </div>
            )}
          </div>
          {batchTagsMessage && (
            <div className={`border-t border-gray-100 px-5 py-2 text-xs ${
              batchTagsMessage.includes('失败') ? 'text-red-600' : 'text-emerald-700'
            }`}>
              {batchTagsMessage}
            </div>
          )}

          {chatFilteredIds === null && (currentPage > 1 || hasMorePages) && (
            <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3 text-xs text-gray-500">
              <span>每页 {LIBRARY_PAGE_SIZE} 篇</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void loadEntries(selectedId, null, tagFilters, Math.max(1, currentPage - 1))}
                  disabled={listLoading || currentPage <= 1}
                  className="rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-gray-600 hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-40"
                  type="button"
                >
                  上一页
                </button>
                <button
                  onClick={() => void loadEntries(selectedId, null, tagFilters, currentPage + 1)}
                  disabled={listLoading || !hasMorePages}
                  className="rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-gray-600 hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-40"
                  type="button"
                >
                  下一页
                </button>
              </div>
            </div>
          )}

          <div className="max-h-[70vh] overflow-y-auto 2xl:max-h-[74vh]">
            {entries.length === 0 && !listLoading ? (
              <div className="px-5 py-12 text-center text-sm text-gray-400">当前筛选条件下没有文献记录。</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {entries.map((entry) => (
                  <div
                    id={`library-entry-${entry.id}`}
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
                          {chatEntryNumberById.get(entry.id) != null && (
                            <span
                              className="shrink-0 rounded-md bg-sky-100 px-1.5 py-0.5 text-[11px] font-semibold text-sky-700"
                              title="AI result number"
                            >
                              [{chatEntryNumberById.get(entry.id)}]
                            </span>
                          )}
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
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${languageClass(entry.language)}`}>
                            {languageLabel(entry.language)}
                          </span>
                          <span className="rounded-full bg-cyan-50 px-2 py-0.5 text-[11px] font-medium text-cyan-700">
                            {sourceFileTypeLabel(entry.source_file_type)}
                          </span>
                          {entry.tags.map((tag) => (
                            <span
                              key={`${entry.id}-${tag}`}
                              className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700"
                            >
                              #{tag}
                            </span>
                          ))}
                          {entry.has_translation && (
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); navigate(`/workspace/cards/reader/${entry.id}?view=translated`) }}
                              className="rounded-full bg-cyan-50 px-2 py-0.5 text-[11px] font-medium text-cyan-700 hover:bg-cyan-100 transition-colors"
                            >
                              查看翻译
                            </button>
                          )}
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
                {selectedSummary ? (
                  <>
                    {chatEntryNumberById.get(selectedSummary.id) != null && (
                      <span className="mr-1 font-semibold text-sky-700">
                        [{chatEntryNumberById.get(selectedSummary.id)}]
                      </span>
                    )}
                    {`当前查看：${selectedSummary.title}`}
                  </>
                ) : (
                  '请选择左侧文献'
                )}
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

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium text-gray-500">文献语言</span>
                    <select
                      value={draft.language}
                      onChange={(event) => setDraft({ ...draft, language: event.target.value })}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    >
                      <option value="">未标注</option>
                      <option value="en">英文</option>
                      <option value="zh">中文</option>
                      <option value="other">其他语言</option>
                    </select>
                  </label>

                  <label className="block">
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
                  <div className="min-w-0 space-y-1 text-sm text-gray-600">
                    <div>来源：{sourceDbLabel(detail.source_db)}</div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span>语言：{languageLabel(detail.language)}</span>
                      <span>{sourceFileTypeLabel(detail.source_file_type)}</span>
                    </div>
                    <div className="break-all">关联原文：{detail.source_file_name || '未绑定'}</div>
                    <div className="break-all">
                      Markdown 原文：{detail.markdown_source_file_name || (detail.source_file_type === 'markdown' ? detail.source_file_name : '未挂载')}
                    </div>
                    {hasTranslatedReaderSource && <div>译文阅读版：已生成</div>}
                    <div>任务时间线：{detail.timeline.length} 条</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      ref={markdownInputRef}
                      type="file"
                      accept=".md,.markdown,text/markdown"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0] || null
                        event.currentTarget.value = ''
                        void handleMarkdownUpload(file)
                      }}
                    />
                    <button
                      type="button"
                      disabled={markdownUploading}
                      className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                      onClick={() => markdownInputRef.current?.click()}
                    >
                      {markdownUploading ? '挂载中...' : detail.markdown_source_file_id ? '替换 Markdown' : '挂载 Markdown'}
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
                      onClick={() => openCnkiTitleSearch(detail)}
                    >
                      知网搜索
                    </button>
                    {/* WOS 搜索：需校园网环境，仅限本地打包版使用，线上版暂不启用
                    <button
                      type="button"
                      disabled={wosSearching}
                      className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                      onClick={() => void handleWosSearch()}
                    >
                      {wosSearching ? '搜索中...' : 'WOS 搜索'}
                    </button>
                    */}
                    <button
                      type="button"
                      disabled={fulltextSearching}
                      className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                      onClick={() => void handleFullTextSearch()}
                    >
                      {fulltextSearching ? '检索中...' : '英文原文'}
                    </button>
                    <button
                      type="button"
                      disabled={!hasMarkdownReaderSource && !hasTranslatedReaderSource && !hasAttachmentReaderSource}
                      className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300"
                      onClick={() => navigate(`/workspace/cards/reader/${detail.id}?view=${readerDefaultView}`)}
                    >
                      阅读并制卡
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                      onClick={() => navigate('/workspace/cards')}
                    >
                      卡片库
                    </button>
                    {detail.source_file_id && detail.source_file_name && detail.source_file_type && (
                      <>
                        <button
                          type="button"
                          className="rounded-lg border border-cyan-200 bg-white px-3 py-1.5 text-xs font-medium text-cyan-700 hover:bg-cyan-50"
                          onClick={() =>
                            openPreviewWithAuth(
                              `/api/upload/${encodeURIComponent(detail.source_file_id || '')}/preview`,
                            ).catch((error) => alert(error.message))
                          }
                        >
                          预览原文
                        </button>
                        <button
                          type="button"
                          className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-700"
                          onClick={() =>
                            downloadWithAuth(
                              `/api/upload/${encodeURIComponent(detail.source_file_id || '')}/download`,
                              detail.source_file_name || 'source-file',
                            ).catch((error) => alert(error.message))
                          }
                        >
                          下载原文
                        </button>
                      </>
                    )}
                    <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                      <input
                        checked={draft.isPinned}
                        onChange={(event) => setDraft({ ...draft, isPinned: event.target.checked })}
                        type="checkbox"
                      />
                      置顶这篇文献
                    </label>
                  </div>
                </div>

                <div className="mt-3 rounded-xl border border-violet-100 bg-violet-50/30 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-gray-800">附件管理</h4>
                    <input
                      ref={attachmentInputRef}
                      type="file"
                      accept=".md,.markdown,text/markdown"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0] || null
                        event.currentTarget.value = ''
                        void handleAttachmentUpload(file)
                      }}
                    />
                    <button
                      type="button"
                      disabled={attachmentUploading}
                      className="rounded-lg border border-violet-200 bg-white px-3 py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50"
                      onClick={() => attachmentInputRef.current?.click()}
                    >
                      {attachmentUploading ? '上传中...' : '添加 Markdown 附件'}
                    </button>
                  </div>
                  {detail.attachments && detail.attachments.length > 0 ? (
                    <div className="mt-3 space-y-1.5">
                      {detail.attachments.map((att) => (
                        <div key={att.id} className="flex items-center gap-2 rounded-lg border border-violet-100 bg-white px-3 py-2">
                          <span className="min-w-0 flex-1 truncate text-xs text-gray-700" title={att.label}>{att.label}</span>
                          <span className="text-[11px] text-gray-400">{att.file_size ? `${(att.file_size / 1024).toFixed(0)} KB` : ''}</span>
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100"
                            onClick={() => navigate(`/workspace/cards/reader/${detail.id}?view=attachment:${att.file_id}`)}
                          >
                            阅读
                          </button>
                          <button
                            type="button"
                            className="rounded px-2 py-0.5 text-[11px] font-medium text-red-600 hover:bg-red-100"
                            onClick={() => { if (window.confirm(`确定删除附件「${att.label}」？`)) void handleAttachmentDelete(att.id) }}
                          >
                            删除
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-gray-400">上传 Markdown 文件作为附件，每个附件可独立阅读并制卡。</p>
                  )}
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
                    <span className={`text-sm ${saveMessage.includes('失败') || saveMessage.includes('错误') ? 'text-red-600' : 'text-emerald-600'}`}>
                      {saveMessage}
                    </span>
                  )}
                </div>

                <div className="rounded-xl border border-gray-100 bg-emerald-50/40 px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-gray-800">AI 点评</h4>
                    {aiCommentMessage && (
                      <span
                        className={`text-xs ${
                          aiCommentMessage.includes('失败') ? 'text-red-600' : 'text-emerald-700'
                        }`}
                      >
                        {aiCommentMessage}
                      </span>
                    )}
                  </div>
                  {detail.ai_comments.length === 0 ? (
                    <div className="mt-3 rounded-lg border border-dashed border-emerald-100 bg-white px-3 py-4 text-sm text-gray-400">
                      还没有保存到这篇文献的 AI 点评。
                    </div>
                  ) : (
                    <div className="mt-3 space-y-3">
                      {detail.ai_comments.map((comment) => (
                        <div key={comment.id} className="rounded-lg bg-white px-3 py-3 shadow-sm">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                              AI 文献助手
                            </span>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs text-gray-400">{formatTime(comment.created_at)}</span>
                              <button
                                type="button"
                                onClick={() => startEditAiComment(comment)}
                                disabled={aiCommentBusyId === comment.id}
                                className="rounded-md border border-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600 hover:border-emerald-200 hover:text-emerald-700 disabled:opacity-40"
                              >
                                编辑
                              </button>
                              <button
                                type="button"
                                onClick={() => void deleteAiComment(comment.id)}
                                disabled={aiCommentBusyId === comment.id}
                                className="rounded-md border border-red-100 px-2 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40"
                              >
                                删除
                              </button>
                            </div>
                          </div>
                          {comment.question && (
                            <div className="mt-2 text-xs text-emerald-800">
                              本轮问题：{comment.question}
                            </div>
                          )}
                          {editingAiCommentId === comment.id ? (
                            <div className="mt-2 space-y-2">
                              <textarea
                                value={editingAiCommentText}
                                onChange={(event) => setEditingAiCommentText(event.target.value)}
                                rows={4}
                                className="w-full rounded-lg border border-emerald-200 px-3 py-2 text-sm leading-6 text-gray-700 focus:border-emerald-500 focus:outline-none"
                              />
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => void updateAiComment(comment.id)}
                                  disabled={!editingAiCommentText.trim() || aiCommentBusyId === comment.id}
                                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
                                >
                                  保存
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditingAiCommentId(null)
                                    setEditingAiCommentText('')
                                  }}
                                  disabled={aiCommentBusyId === comment.id}
                                  className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-800 disabled:opacity-40"
                                >
                                  取消
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-700">
                              {comment.note}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
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

                    {detail.abstract_cn && (
                      <div>
                        <div className="text-xs font-medium text-gray-500">中文摘要</div>
                        <div className="mt-1 whitespace-pre-wrap rounded-lg bg-blue-50 px-3 py-2 text-sm text-gray-700">
                          {detail.abstract_cn}
                        </div>
                      </div>
                    )}

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

      <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
        <button
          type="button"
          onClick={() => setChatOpen((open) => !open)}
          className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-900">AI 文献助手</h3>
              {chatFilteredIds !== null && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                  当前结果 {chatFilteredIds.length} 篇
                </span>
              )}
              {chatTurns.length > 0 && (
                <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700">
                  {chatTurns.length} 轮
                </span>
              )}
            </div>
          </div>
          <span className="text-sm text-gray-400">{chatOpen ? '收起' : '展开'}</span>
        </button>

        {chatOpen && (
          <div className="space-y-4 border-t border-gray-100 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
                {([
                  ['auto', '自动'],
                  ['library', '全库'],
                  ['previous_results', '当前结果'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setChatScopeMode(value)}
                    disabled={value === 'previous_results' && chatTurns.length === 0}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                      chatScopeMode === value
                        ? 'bg-white text-emerald-700 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700'
                    } disabled:cursor-not-allowed disabled:opacity-40`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {chatFilteredIds !== null && (
                  <button
                    type="button"
                    onClick={() => {
                      setChatFilteredIds(null)
                      void loadEntries(undefined, null)
                    }}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-emerald-300 hover:text-emerald-700"
                  >
                    恢复全量列表
                  </button>
                )}
                {chatTurns.length > 0 && (
                  <button
                    type="button"
                    onClick={clearChat}
                    disabled={chatLoading}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-red-200 hover:text-red-600 disabled:opacity-50"
                  >
                    清空对话
                  </button>
                )}
              </div>
            </div>

            {chatError && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">{chatError}</div>}

            {chatTurns.length > 0 && (
              <div className="space-y-4">
                {chatTurns.map((turn) => (
                  <article key={turn.id} className="rounded-xl border border-gray-100 bg-slate-50 px-4 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-gray-500">你的问题</div>
                        <div className="mt-1 whitespace-pre-wrap text-sm font-medium text-gray-900">{turn.question}</div>
                      </div>
                      <div className="flex flex-wrap gap-2 text-[11px]">
                        {turn.scope && (
                          <span className="rounded-full bg-white px-2 py-1 font-medium text-gray-600 shadow-sm">
                            {turn.scope === 'library' ? '全库检索' : '当前结果内检索'}
                          </span>
                        )}
                        <span className="rounded-full bg-white px-2 py-1 font-medium text-emerald-700 shadow-sm">
                          命中 {turn.resultCount} 篇
                        </span>
                      </div>
                    </div>

                    {turn.intent && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {[...turn.intent.core_keywords, ...turn.intent.expanded_keywords].map((keyword) => (
                          <span key={`${turn.id}-${keyword}`} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-sky-700 shadow-sm">
                            {keyword}
                          </span>
                        ))}
                      </div>
                    )}

                    {turn.actionProposal && (
                      <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-emerald-800">待确认标签操作</div>
                            <div className="mt-1 text-sm text-emerald-950">
                              {turn.actionProposal.type === 'add_tags' ? '添加' : '移除'}标签{' '}
                              {turn.actionProposal.tags.map((tag) => (
                                <span
                                  key={`${turn.id}-proposal-${tag}`}
                                  className="mx-0.5 inline-flex rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-emerald-700 shadow-sm"
                                >
                                  #{tag}
                                </span>
                              ))}
                            </div>
                            <div className="mt-1 text-xs text-emerald-800">
                              范围：{turn.actionProposal.scope === 'library' ? '全库检索结果' : '当前结果内检索'}
                              {turn.actionProposal.journal ? ` · 期刊条件：${turn.actionProposal.journal}` : ''}
                              {` · 将影响 ${turn.actionProposal.count} 篇文献`}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {turn.actionProposal.status === 'pending' && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => void executeChatProposal(turn.id, turn.actionProposal!)}
                                  disabled={turn.actionProposal.count === 0}
                                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
                                >
                                  确认执行
                                </button>
                                <button
                                  type="button"
                                  onClick={() => cancelChatProposal(turn.id)}
                                  className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                                >
                                  取消
                                </button>
                              </>
                            )}
                            {turn.actionProposal.status === 'running' && (
                              <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-emerald-700 shadow-sm">
                                执行中...
                              </span>
                            )}
                          </div>
                        </div>
                        {turn.actionProposal.entryTitles.length > 0 && (
                          <div className="mt-3 grid gap-1 text-xs text-emerald-900 md:grid-cols-2">
                            {turn.actionProposal.entryTitles.slice(0, 6).map((title, index) => (
                              <div key={`${turn.id}-proposal-title-${index}`} className="truncate rounded-md bg-white/80 px-2 py-1">
                                [{index + 1}] {title}
                              </div>
                            ))}
                          </div>
                        )}
                        {turn.actionProposal.entryTitles.length > 6 && (
                          <div className="mt-1 text-xs text-emerald-700">
                            另有 {turn.actionProposal.entryTitles.length - 6} 篇文献。
                          </div>
                        )}
                        {turn.actionProposal.message && (
                          <div className={`mt-2 text-xs ${
                            turn.actionProposal.status === 'error' ? 'text-red-600' : 'text-emerald-800'
                          }`}>
                            {turn.actionProposal.message}
                          </div>
                        )}
                      </div>
                    )}

                    {turn.report ? (
                      <div
                        className="mt-4 max-w-none overflow-x-auto rounded-lg bg-white px-4 py-4 text-sm leading-7 text-gray-700 [&_button[data-chat-entry-number]]:mx-0.5 [&_button[data-chat-entry-number]]:inline-flex [&_button[data-chat-entry-number]]:items-center [&_button[data-chat-entry-number]]:rounded-md [&_button[data-chat-entry-number]]:bg-sky-100 [&_button[data-chat-entry-number]]:px-1.5 [&_button[data-chat-entry-number]]:py-0.5 [&_button[data-chat-entry-number]]:font-semibold [&_button[data-chat-entry-number]]:leading-5 [&_button[data-chat-entry-number]]:text-sky-700 [&_button[data-chat-entry-number]]:transition-colors hover:[&_button[data-chat-entry-number]]:bg-sky-200 [&_h1]:mb-3 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-3 [&_h3]:text-sm [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ol]:space-y-1 [&_p]:mb-3 [&_table]:min-w-full [&_table]:border-collapse [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-gray-200 [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1 [&_ul]:space-y-1"
                        onClick={(event) => handleReportClick(event, turn)}
                        dangerouslySetInnerHTML={{ __html: markdownHtml(turn.report, turn.entryIds.length) }}
                      />
                    ) : (
                      <div className="mt-4 rounded-lg bg-white px-4 py-5 text-sm text-gray-400">
                        {chatLoading && turn.id === chatTurns[chatTurns.length - 1]?.id ? '正在生成报告...' : '本轮暂无报告内容。'}
                      </div>
                    )}
                    {turn.report && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void saveChatTurnReport(turn.id)}
                          disabled={turn.historySaveStatus === 'saving' || chatLoading}
                          className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-40"
                        >
                          {turn.historySaveStatus === 'saving' ? '保存中...' : '保存到历史记录'}
                        </button>
                        {turn.historySaveMessage && (
                          <span
                            className={`text-xs ${
                              turn.historySaveStatus === 'error' ? 'text-red-600' : 'text-blue-700'
                            }`}
                          >
                            {turn.historySaveMessage}
                          </span>
                        )}
                        {turn.entryIds.length > 0 && (
                          <>
                            <span className="text-gray-300">|</span>
                            <button
                              type="button"
                              onClick={() => void saveChatTurnComments(turn.id)}
                              disabled={turn.commentSaveStatus === 'saving' || chatLoading}
                              className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
                            >
                              {turn.commentSaveStatus === 'saving' ? '保存点评中...' : '保存本轮 AI 点评'}
                            </button>
                            {turn.commentSaveMessage && (
                              <span
                                className={`text-xs ${
                                  turn.commentSaveStatus === 'error' ? 'text-red-600' : 'text-emerald-700'
                                }`}
                              >
                                {turn.commentSaveMessage}
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}

            <div className="flex flex-col gap-2 md:flex-row md:items-end">
              <label className="min-w-0 flex-1">
                <span className="mb-1 block text-xs font-medium text-gray-500">继续提问</span>
                <textarea
                  value={chatQuestion}
                  onChange={(event) => setChatQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void handleChatSubmit()
                    }
                  }}
                  disabled={chatLoading}
                  rows={2}
                  className="w-full resize-y rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none disabled:bg-gray-50"
                  placeholder="例如：这批文献里，哪些研究关注平台治理？"
                />
              </label>
              <button
                type="button"
                onClick={() => void handleChatSubmit()}
                disabled={chatLoading || !chatQuestion.trim()}
                className="h-10 rounded-lg bg-emerald-600 px-4 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {chatLoading ? '分析中...' : '提问'}
              </button>
            </div>
          </div>
        )}
      </section>

      {fulltextResult && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setFulltextResult(null)}
        >
          <div
            style={{ background: '#fff', borderRadius: 12, width: '90%', maxWidth: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column', boxShadow: '0 12px 32px rgba(45,42,38,0.15)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid #e5e7eb' }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>英文原文检索结果</h3>
              <button type="button" onClick={() => setFulltextResult(null)} className="rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50">关闭</button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px', fontSize: 13 }}>
              {fulltextResult.doi && (
                <p style={{ margin: '0 0 8px', color: '#6b7280' }}>DOI: {fulltextResult.doi}</p>
              )}
              {fulltextResult.errors.length > 0 && (
                <p style={{ margin: '0 0 8px', color: '#dc2626', fontSize: 12 }}>
                  PDF 候选未能挂载：{fulltextResult.errors.slice(0, 2).join('；')}
                </p>
              )}
              {fulltextResult.pdf_candidates.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{ fontWeight: 600, margin: '0 0 6px' }}>PDF 下载链接</p>
                  {fulltextResult.pdf_candidates.map((item, i) => (
                    <a key={i} href={item.url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', padding: '4px 0', color: '#4f46e5', textDecoration: 'none', wordBreak: 'break-all' }}>
                      [{item.source}] {item.label}
                    </a>
                  ))}
                </div>
              )}
              {fulltextResult.landing_pages.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{ fontWeight: 600, margin: '0 0 6px' }}>开放访问页面</p>
                  {fulltextResult.landing_pages.map((item, i) => (
                    <a key={i} href={item.url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', padding: '4px 0', color: '#4f46e5', textDecoration: 'none', wordBreak: 'break-all' }}>
                      [{item.label}] {item.url.length > 80 ? item.url.slice(0, 77) + '...' : item.url}
                    </a>
                  ))}
                </div>
              )}
              {fulltextResult.working_paper_searches.length > 0 && (
                <div>
                  <p style={{ fontWeight: 600, margin: '0 0 6px' }}>未找到直接 PDF，可尝试以下检索入口</p>
                  {fulltextResult.working_paper_searches.slice(0, 6).map((item, i) => (
                    <a key={i} href={item.url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', padding: '4px 0', color: '#4f46e5', textDecoration: 'none' }}>
                      [{item.source}] {item.label}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {refFormatOpen && (
        <RefFormatModal
          apiKey={apiKey}
          entryIds={Array.from(selectedIds)}
          onClose={() => setRefFormatOpen(false)}
        />
      )}
    </div>
  )
}
