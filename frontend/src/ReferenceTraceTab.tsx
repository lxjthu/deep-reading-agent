import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'

type TraceEntryOption = {
  id: string
  title: string
  year: number | null
  authors: string[]
  source_file_name: string | null
  has_reference_trace: boolean
  latest_task_id: string | null
  latest_task_status: string | null
  latest_task_finished_at: string | null
}

type TraceArtifact = {
  id: number
  artifact_type: string
  filename: string
  storage_path: string
  created_at: string | null
}

type TraceSummary = {
  source_bib_entry_id: string
  reference_count: number
  matched_count: number
  imported_count: number
  unmatched_count: number
  citation_hit_count: number
  latest_task: {
    id: string
    status: string
    current_stage: string | null
    finished_at: string | null
    artifacts: TraceArtifact[]
  } | null
}

type TraceReference = {
  id: string
  reference_order: number
  raw_text: string
  title: string | null
  authors: string[]
  year: number | null
  journal: string | null
  doi: string | null
  match_method: string | null
  match_score: number | null
  citation_count: number
  matched_bib_entry_id: string | null
  matched_bib_title: string | null
}

type TraceCitation = {
  id: string
  citation_index: number
  page_label: string | null
  paragraph_label: string | null
  quote_text: string
  excerpt: string | null
  match_method: string | null
  confidence: number | null
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail =
      typeof (data as any)?.detail === 'string'
        ? (data as any).detail
        : typeof (data as any)?.message === 'string'
          ? (data as any).message
          : '请求失败。'
    throw new Error(detail)
  }
  return data as T
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function artifactLabel(type: string) {
  return (
    {
      references_excel: '参考文献表',
      references_with_citations_excel: '含正文命中表',
      citation_trace_md: '梳理报告',
      references_json: '结构化 JSON',
    }[type] || type
  )
}

export default function ReferenceTraceTab({ apiKey }: { apiKey: string }) {
  const [urlParams, setUrlParams] = useSearchParams()
  const urlSourceEntryId = urlParams.get('sourceEntryId')
  const urlRefId = urlParams.get('refId')
  const pendingRefIdRef = useRef<string | null>(urlRefId)
  const [entries, setEntries] = useState<TraceEntryOption[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [summary, setSummary] = useState<TraceSummary | null>(null)
  const [references, setReferences] = useState<TraceReference[]>([])
  const [selectedReferenceId, setSelectedReferenceId] = useState<string | null>(null)
  const [citations, setCitations] = useState<TraceCitation[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('请选择一篇带 PDF 的文献')
  const [logs, setLogs] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const clearUrlParams = useCallback(() => {
    if (urlParams.has('sourceEntryId') || urlParams.has('refId')) {
      const next = new URLSearchParams(urlParams)
      next.delete('sourceEntryId')
      next.delete('refId')
      setUrlParams(next)
    }
    pendingRefIdRef.current = null
  }, [urlParams, setUrlParams])

  const selectedEntry = useMemo(
    () => entries.find((item) => item.id === selectedId) || null,
    [entries, selectedId],
  )

  const selectedReference = useMemo(
    () => references.find((item) => item.id === selectedReferenceId) || null,
    [references, selectedReferenceId],
  )

  async function loadEntries(preferredId?: string | null) {
    setLoadingList(true)
    setMessage('')
    try {
      const response = await fetch('/api/references/entries')
      const data = await parseJsonOrThrow<TraceEntryOption[]>(response)
      setEntries(data)
      const nextId =
        preferredId && data.some((item) => item.id === preferredId)
          ? preferredId
          : selectedId && data.some((item) => item.id === selectedId)
            ? selectedId
            : data[0]?.id || null
      setSelectedId(nextId)
    } catch (error: any) {
      setEntries([])
      setSelectedId(null)
      setMessage(error.message || '加载源文献失败。')
    } finally {
      setLoadingList(false)
    }
  }

  async function loadDetail(entryId: string, pendingRefId?: string | null) {
    setLoadingDetail(true)
    setSelectedReferenceId(null)
    setCitations([])
    setLogs([])
    try {
      const [summaryRes, refsRes] = await Promise.all([
        fetch(`/api/references/entries/${encodeURIComponent(entryId)}/summary`),
        fetch(`/api/references/entries/${encodeURIComponent(entryId)}/references`),
      ])
      const [summaryData, refsData] = await Promise.all([
        parseJsonOrThrow<TraceSummary>(summaryRes),
        parseJsonOrThrow<TraceReference[]>(refsRes),
      ])
      setSummary(summaryData)
      setReferences(refsData)
      if (pendingRefId && refsData.some((r) => r.id === pendingRefId)) {
        setSelectedReferenceId(pendingRefId)
      } else if (refsData.length > 0) {
        setSelectedReferenceId(refsData[0].id)
      }
      if (summaryData.latest_task) {
        setStage(summaryData.latest_task.current_stage || '已完成')
      } else {
        setStage('尚未开始梳理')
      }
    } catch (error: any) {
      setSummary(null)
      setReferences([])
      setMessage(error.message || '加载梳理结果失败。')
    } finally {
      setLoadingDetail(false)
    }
  }

  async function loadCitations(referenceId: string) {
    try {
      const response = await fetch(`/api/references/references/${encodeURIComponent(referenceId)}/citations`)
      const data = await parseJsonOrThrow<TraceCitation[]>(response)
      setCitations(data)
    } catch (error: any) {
      setCitations([])
      setMessage(error.message || '加载正文命中失败。')
    }
  }

  useEffect(() => {
    void loadEntries(urlSourceEntryId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setSummary(null)
      setReferences([])
      return
    }
    void loadDetail(selectedId, pendingRefIdRef.current)
  }, [selectedId])

  useEffect(() => {
    if (!selectedReferenceId) {
      setCitations([])
      return
    }
    void loadCitations(selectedReferenceId)
  }, [selectedReferenceId])

  useEffect(() => {
    const refId = pendingRefIdRef.current
    if (!refId || !selectedReferenceId || selectedReferenceId !== refId) return
    const el = document.getElementById(`ref-row-${refId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    pendingRefIdRef.current = null
  }, [selectedReferenceId, references])

  async function startTrace() {
    if (!selectedId) return
    setRunning(true)
    setProgress(0)
    setLogs([])
    setStage('准备启动...')
    setMessage('')
    try {
      const response = await fetch(`/api/references/entries/${encodeURIComponent(selectedId)}/trace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...(apiKey ? { api_key: apiKey } : {}) }),
      })
      const data = await parseJsonOrThrow<{ task_id: string }>(response)
      setLogs((prev) => [...prev, `任务已创建：${data.task_id}`])
      const poll = window.setInterval(async () => {
        try {
          const statusResponse = await fetch(`/api/references/task/${encodeURIComponent(data.task_id)}/status`)
          const status = await parseJsonOrThrow<any>(statusResponse)
          setProgress(status.progress || 0)
          setStage(status.stage || '处理中...')
          if (Array.isArray(status.logs)) {
            setLogs(status.logs)
          }
          if (status.status === 'completed') {
            window.clearInterval(poll)
            setRunning(false)
            setProgress(100)
            setStage('完成')
            await loadEntries(selectedId)
            await loadDetail(selectedId)
          } else if (status.status === 'failed' || status.status === 'canceled') {
            window.clearInterval(poll)
            setRunning(false)
            setMessage(status.error || '任务失败。')
          }
        } catch (error: any) {
          window.clearInterval(poll)
          setRunning(false)
          setMessage(error.message || '轮询任务状态失败。')
        }
      }, 1000)
    } catch (error: any) {
      setRunning(false)
      setMessage(error.message || '启动任务失败。')
    }
  }

  async function importReference(referenceId: string) {
    try {
      const response = await fetch(`/api/references/references/${encodeURIComponent(referenceId)}/import`, {
        method: 'POST',
      })
      const data = await parseJsonOrThrow<{ title: string; source: string }>(response)
      setMessage(data.source === 'created' ? `已导入文献库：${data.title}` : `已关联已有文献：${data.title}`)
      if (selectedId) {
        await loadDetail(selectedId)
      }
    } catch (error: any) {
      setMessage(error.message || '导入失败。')
    }
  }

  function startEdit(item: TraceReference) {
    setEditingId(item.id)
    setEditForm({
      title: item.title || '',
      authors: item.authors.join(', '),
      year: item.year?.toString() || '',
      journal: item.journal || '',
      doi: item.doi || '',
      raw_text: item.raw_text,
    })
  }

  async function saveEdit(referenceId: string) {
    setSaving(true)
    try {
      const payload: Record<string, any> = {}
      if (editForm.title !== '') payload.title = editForm.title
      if (editForm.raw_text !== '') payload.raw_text = editForm.raw_text
      if (editForm.authors !== '') payload.authors = editForm.authors.split(/[,，;；]/).map((s) => s.trim()).filter(Boolean)
      if (editForm.year !== '') payload.year = parseInt(editForm.year, 10) || null
      if (editForm.journal !== '') payload.journal = editForm.journal
      if (editForm.doi !== '') payload.doi = editForm.doi

      const response = await fetch(`/api/references/references/${encodeURIComponent(referenceId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await parseJsonOrThrow<TraceReference>(response)
      setReferences((prev) => prev.map((r) => (r.id === referenceId ? data : r)))
      setEditingId(null)
      setMessage('已保存修改。')
    } catch (error: any) {
      setMessage(error.message || '保存失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">参考文献梳理</h2>
            <p className="mt-1 text-sm text-gray-500">对单篇已入库 PDF 执行参考文献目录抽取、正文引用命中与关系入库。</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadEntries(selectedId)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 hover:border-emerald-300 hover:text-emerald-700"
            >
              刷新源文献
            </button>
            <button
              type="button"
              onClick={() => void startTrace()}
              disabled={!selectedId || running}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {running ? '梳理中...' : '开始梳理'}
            </button>
          </div>
        </div>
        {message && <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</div>}
      </div>

      <div className="grid gap-4 2xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h3 className="text-sm font-semibold text-gray-800">源文献</h3>
            <p className="mt-1 text-xs text-gray-400">{loadingList ? '加载中...' : `共 ${entries.length} 篇带 PDF 文献`}</p>
          </div>
          <div className="overflow-y-auto">
            {entries.length === 0 && !loadingList ? (
              <div className="px-5 py-12 text-center text-sm text-gray-400">当前没有可用于梳理的 PDF 文献。</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {entries.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => { setSelectedId(item.id); clearUrlParams() }}
                    className={`w-full px-5 py-4 text-left hover:bg-emerald-50/50 ${
                      item.id === selectedId ? 'bg-emerald-50' : 'bg-white'
                    }`}
                  >
                    <div className="line-clamp-2 text-sm font-medium text-gray-900">{item.title}</div>
                    <div className="mt-2 text-xs text-gray-500">
                      {item.authors.slice(0, 3).join(', ') || '未知作者'}
                      {item.year ? ` · ${item.year}` : ''}
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-xs">
                      <span
                        className={`rounded-full px-2 py-0.5 ${
                          item.has_reference_trace ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {item.has_reference_trace ? '已梳理' : '未梳理'}
                      </span>
                      {item.latest_task_status && (
                        <span className="rounded-full bg-sky-100 px-2 py-0.5 text-sky-700">{item.latest_task_status}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-800">任务进度</h3>
                <p className="mt-1 text-xs text-gray-400">{selectedEntry?.source_file_name || '请选择源文献'}</p>
              </div>
              <span className="text-sm font-medium text-emerald-600">{progress}%</span>
            </div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm text-gray-600">{stage}</span>
              {summary?.latest_task?.finished_at && <span className="text-xs text-gray-400">{formatTime(summary.latest_task.finished_at)}</span>}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all" style={{ width: `${progress}%` }} />
            </div>
            <div className="mt-4 rounded-lg bg-gray-900 p-3 font-mono text-xs text-gray-200">
              {logs.length === 0 ? <div className="text-gray-500">等待开始...</div> : logs.map((log, idx) => <div key={idx}>{log}</div>)}
            </div>
          </div>

          <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_300px]">
            <div className="flex flex-col rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-gray-800">梳理结果</h3>
                  {summary && (
                    <>
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">参考文献 {summary.reference_count}</span>
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">已匹配 {summary.matched_count}</span>
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">正文命中 {summary.citation_hit_count}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="max-h-[62vh] overflow-auto">
                {loadingDetail ? (
                  <div className="px-5 py-12 text-center text-sm text-gray-400">加载中...</div>
                ) : references.length === 0 ? (
                  <div className="px-5 py-12 text-center text-sm text-gray-400">暂无梳理结果，先执行一次任务。</div>
                ) : (
                  <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
                    <colgroup>
                      <col style={{ width: '50px' }} />
                      <col />
                      <col style={{ width: '140px' }} />
                      <col style={{ width: '60px' }} />
                      <col style={{ width: '130px' }} />
                    </colgroup>
                    <thead className="sticky top-0 bg-white">
                      <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                        <th className="px-4 py-3">序号</th>
                        <th className="px-4 py-3">标题 / 原文</th>
                        <th className="px-4 py-3">匹配状态</th>
                        <th className="px-4 py-3">正文命中</th>
                        <th className="px-4 py-3">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {references.map((item) => (
                        <tr key={item.id} id={`ref-row-${item.id}`} className={`border-b border-gray-100 ${item.id === selectedReferenceId ? 'bg-emerald-50/50' : ''}`}>
                          {editingId === item.id ? (
                            <>
                              <td className="px-4 py-3 align-top text-gray-500">{item.reference_order}</td>
                              <td className="px-4 py-3 align-top" colSpan={4}>
                                <div className="space-y-2">
                                  <div className="grid grid-cols-[1fr_80px] gap-2">
                                    <input
                                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                      placeholder="标题"
                                      value={editForm.title ?? ''}
                                      onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))}
                                    />
                                    <input
                                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                      placeholder="年份"
                                      value={editForm.year ?? ''}
                                      onChange={(e) => setEditForm((f) => ({ ...f, year: e.target.value }))}
                                    />
                                  </div>
                                  <div className="grid grid-cols-[1fr_1fr] gap-2">
                                    <input
                                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                      placeholder="作者（逗号分隔）"
                                      value={editForm.authors ?? ''}
                                      onChange={(e) => setEditForm((f) => ({ ...f, authors: e.target.value }))}
                                    />
                                    <input
                                      className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                      placeholder="期刊"
                                      value={editForm.journal ?? ''}
                                      onChange={(e) => setEditForm((f) => ({ ...f, journal: e.target.value }))}
                                    />
                                  </div>
                                  <input
                                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                    placeholder="DOI"
                                    value={editForm.doi ?? ''}
                                    onChange={(e) => setEditForm((f) => ({ ...f, doi: e.target.value }))}
                                  />
                                  <textarea
                                    className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none"
                                    rows={2}
                                    placeholder="原文"
                                    value={editForm.raw_text ?? ''}
                                    onChange={(e) => setEditForm((f) => ({ ...f, raw_text: e.target.value }))}
                                  />
                                  <div className="flex items-center gap-2">
                                    <button
                                      type="button"
                                      disabled={saving}
                                      onClick={() => void saveEdit(item.id)}
                                      className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                                    >
                                      {saving ? '保存中...' : '保存'}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setEditingId(null)}
                                      className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                                    >
                                      取消
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="px-4 py-3 align-top text-gray-500">{item.reference_order}</td>
                              <td className="px-4 py-3 align-top">
                                <button
                                  type="button"
                                  onClick={() => { setSelectedReferenceId(item.id); clearUrlParams() }}
                                  className="text-left hover:text-emerald-700"
                                >
                                  <div className="break-words font-medium text-gray-900">{item.title || '未识别标题'}</div>
                                  <div className="mt-1 line-clamp-2 break-all text-xs text-gray-500">{item.raw_text}</div>
                                </button>
                              </td>
                              <td className="px-4 py-3 align-top">
                                <div className="break-words text-xs text-gray-700">{item.matched_bib_title || '未匹配'}</div>
                                {item.match_method && <div className="mt-1 text-xs text-gray-400">{item.match_method}</div>}
                              </td>
                              <td className="px-4 py-3 align-top text-gray-700">{item.citation_count}</td>
                              <td className="px-4 py-3 align-top">
                                <div className="flex items-center gap-1">
                                  <button
                                    type="button"
                                    onClick={() => startEdit(item)}
                                    className="rounded-lg border border-gray-200 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                                    title="编辑"
                                  >
                                    编辑
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void importReference(item.id)}
                                    className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                                  >
                                    {item.matched_bib_entry_id ? '同步到文献库' : '导入文献库'}
                                  </button>
                                </div>
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-800">正文引用详情</h3>
                {selectedReference ? (
                  <>
                    <div className="mt-2 text-sm font-medium text-gray-900">{selectedReference.title || '未识别标题'}</div>
                    <div className="mt-1 text-xs text-gray-500">{selectedReference.authors.join(', ') || '未知作者'}</div>
                  </>
                ) : (
                  <p className="mt-2 text-sm text-gray-400">请选择左侧一条参考文献。</p>
                )}
                <div className="mt-4 space-y-3">
                  {citations.length === 0 ? (
                    <div className="rounded-lg bg-gray-50 px-3 py-4 text-sm text-gray-400">暂无正文命中。</div>
                  ) : (
                    citations.map((item) => (
                      <div key={item.id} className="overflow-hidden rounded-xl border border-gray-100 bg-gray-50 p-3">
                        <div className="flex items-center justify-between text-xs text-gray-500">
                          <span>{item.page_label || '未知页'} / {item.paragraph_label || '未知段落'}</span>
                          <span>{item.confidence ? `${Math.round(item.confidence * 100)}%` : '-'}</span>
                        </div>
                        <div className="mt-2 break-words text-sm leading-6 text-gray-900">{item.excerpt || item.quote_text}</div>
                        {item.excerpt && item.quote_text && item.excerpt !== item.quote_text && (
                          <div className="mt-2 break-words text-xs leading-5 text-gray-500">命中标记：{item.quote_text}</div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-800">产物下载</h3>
                <div className="mt-3 space-y-2">
                  {summary?.latest_task?.artifacts?.length ? (
                    summary.latest_task.artifacts.map((artifact) => {
                      const canPreview = artifact.filename.toLowerCase().endsWith('.md')
                      return (
                        <div
                          key={artifact.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700"
                        >
                          <div className="min-w-0">
                            <div className="font-medium">{artifactLabel(artifact.artifact_type)}</div>
                            <div className="truncate text-xs text-gray-400">{artifact.filename}</div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            {canPreview && (
                              <button
                                type="button"
                                onClick={() =>
                                  openPreviewWithAuth(
                                    `/api/history/${encodeURIComponent(artifact.filename)}/preview`,
                                  ).catch((error) => setMessage(error.message))
                                }
                                className="rounded-lg bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-700 hover:bg-teal-100"
                              >
                                预览
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() =>
                                downloadWithAuth(
                                  `/api/download/${encodeURIComponent(artifact.storage_path)}`,
                                  artifact.filename,
                                ).catch((error) => setMessage(error.message))
                              }
                              className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                            >
                              下载
                            </button>
                          </div>
                        </div>
                      )
                    })
                  ) : (
                    <div className="rounded-lg bg-gray-50 px-3 py-4 text-sm text-gray-400">暂无可下载产物。</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
