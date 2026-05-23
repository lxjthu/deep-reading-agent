import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from './lib/api-fetch'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'

interface TranslatableEntry {
  bib_entry_id: string
  title: string
  authors: string[]
  year: number | null
  journal: string | null
  file_id: string
  file_name: string
  file_type: string
}

interface ArtifactInfo {
  id: number
  artifact_type: string
  filename: string
  storage_path: string
  size_bytes: number | null
}

const STAGE_LABELS: Record<string, string> = {
  extracting: 'PDF 文本提取',
  front_sections: '提取标题/摘要/引言',
  glossary: '生成术语词典',
  detect_level: '检测章节层级',
  chunking: '按标题切块',
  restating: '逐块重述',
  fixing_untranslated: '补译残留英文',
  saving: '保存产物',
  generating_glossary: '生成术语词典',
}

function getStageLabel(stage: string): string {
  if (!stage) return '处理中...'
  if (stage.startsWith('排队中')) return stage
  return STAGE_LABELS[stage] || stage
}

export default function TranslationTab({ apiKey }: { apiKey: string }) {
  const navigate = useNavigate()
  const [entries, setEntries] = useState<TranslatableEntry[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [maxWorkers, setMaxWorkers] = useState(5)
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState('')
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')
  const pollRef = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const loadEntries = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/translation/translatable')
      if (res.ok) {
        const data = await res.json()
        setEntries(data.entries || [])
      }
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => {
    loadEntries()
    return () => { stopPolling() }
  }, [])

  const selected = entries.find(e => e.bib_entry_id === selectedId)

  const handleSourceUpload = async (file: File | null) => {
    if (!file) return
    setUploading(true)
    setUploadMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const uploadRes = await apiFetch('/api/upload/', {
        method: 'POST',
        body: formData,
      })
      if (!uploadRes.ok) {
        const data = await uploadRes.json().catch(() => ({}))
        throw new Error(data.detail || data.message || `上传失败 (${uploadRes.status})`)
      }
      const uploadData = await uploadRes.json()
      if (!uploadData.success || !uploadData.file_id) {
        throw new Error(uploadData.message || '上传失败')
      }

      const bindRes = await apiFetch('/api/translation/bind-upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id }),
      })
      if (!bindRes.ok) {
        const data = await bindRes.json().catch(() => ({}))
        throw new Error(data.detail || `文献匹配失败 (${bindRes.status})`)
      }
      const bound = await bindRes.json()
      await loadEntries()
      setSelectedId(bound.bib_entry_id)
      setUploadMessage(`已上传并匹配到文献库：${bound.title}`)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '上传文献失败'
      setUploadMessage(message)
    } finally {
      setUploading(false)
    }
  }

  const handleStart = async () => {
    if (!selected) {
      window.alert('请先选择一篇文献')
      return
    }
    if (!apiKey) {
      window.alert('请先设置 DeepSeek API Key')
      return
    }

    setProgress(0)
    setCurrentStage('提交翻译任务...')
    setJobStatus('')
    setErrorMsg('')
    setArtifacts([])

    try {
      const res = await apiFetch('/api/translation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: selected.file_id,
          bib_entry_id: selected.bib_entry_id,
          api_key: apiKey,
          max_workers: maxWorkers,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `启动失败 (${res.status})`)
      }
      const data = await res.json()
      setJobId(data.job_id)
      setJobStatus('pending')
      setCurrentStage('翻译已启动...')
      startPolling(data.job_id)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '启动翻译失败'
      setErrorMsg(msg)
      setCurrentStage('错误')
    }
  }

  const startPolling = (jid: string) => {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await apiFetch(`/api/translation/${jid}/status`)
        if (!res.ok) return
        const data = await res.json()
        setJobStatus(data.status)
        setProgress(data.progress || 0)
        setCurrentStage(getStageLabel(data.current_stage || ''))
        setErrorMsg(data.error_msg || '')

        if (data.status === 'completed' || data.status === 'success') {
          stopPolling()
          fetchResults(jid)
        } else if (data.status === 'failed' || data.status === 'canceled') {
          stopPolling()
        }
      } catch { /* ignore poll errors */ }
    }, 2000)
  }

  const fetchResults = async (jid: string) => {
    try {
      const res = await apiFetch(`/api/translation/${jid}/result`)
      if (!res.ok) return
      const data = await res.json()
      setArtifacts(data.artifacts || [])
    } catch { /* ignore */ }
  }

  const handleCancel = async () => {
    if (!jobId) return
    try {
      await apiFetch(`/api/translation/cancel/${jobId}`, { method: 'POST' })
    } catch { /* ignore */ }
    stopPolling()
    setJobStatus('canceled')
    setCurrentStage('已取消')
  }

  const handleDownload = (artifact: ArtifactInfo) => {
    downloadWithAuth(
      `/api/download/${encodeURIComponent(artifact.storage_path)}`,
      artifact.filename,
    ).catch((error) => alert(error.message))
  }

  const handlePreview = (artifact: ArtifactInfo) => {
    openPreviewWithAuth(
      `/api/history/${encodeURIComponent(artifact.filename)}/preview`,
    ).catch((error) => alert(error.message))
  }

  const isRunning = jobStatus === 'pending' || jobStatus === 'running'

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-gray-900 mb-1">全文翻译 — DeepSeek 中文重述</h2>
        <p className="text-sm text-gray-500 mb-4">
          选择文献库中已标注为英文且绑定了 PDF 或 Markdown 原文的文献，生成术语词典和全文中文重述版本。
        </p>

        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-emerald-200 bg-emerald-50/60 px-4 py-3">
          <label className="inline-flex cursor-pointer items-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
            <input
              type="file"
              accept=".pdf,.md,.markdown,application/pdf,text/markdown"
              className="sr-only"
              disabled={uploading || isRunning}
              onChange={(event) => {
                const file = event.target.files?.[0] || null
                event.currentTarget.value = ''
                void handleSourceUpload(file)
              }}
            />
            {uploading ? '上传匹配中...' : '上传 PDF / Markdown'}
          </label>
          <p className="text-xs text-emerald-800">
            上传后会按精读链路匹配或创建文献库档案，并作为英文原文加入翻译列表。
          </p>
          {uploadMessage && (
            <p className="w-full text-xs text-emerald-900">{uploadMessage}</p>
          )}
        </div>

        <div className="flex gap-2 mb-3">
          <span className="rounded-lg bg-emerald-100 px-3 py-1.5 text-xs font-medium text-emerald-800">
            英文原文 ({entries.length})
          </span>
          <button
            onClick={loadEntries}
            className="ml-auto px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
          >
            刷新列表
          </button>
        </div>

        {loading ? (
          <div className="py-8 text-center text-sm text-gray-400">加载中...</div>
        ) : entries.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-gray-400 mb-2">暂无可翻译的文献</p>
            <p className="text-xs text-gray-400">请在文献库绑定 PDF 或 Markdown 原文，并把语言标注为英文。</p>
          </div>
        ) : (
          <div className="border border-gray-100 rounded-lg max-h-80 overflow-y-auto divide-y divide-gray-50">
            {entries.map(entry => (
              <label
                key={entry.bib_entry_id}
                className={`flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors ${
                  selectedId === entry.bib_entry_id ? 'bg-emerald-50' : ''
                }`}
              >
                <input
                  type="radio"
                  name="translation-entry"
                  value={entry.bib_entry_id}
                  checked={selectedId === entry.bib_entry_id}
                  onChange={() => setSelectedId(entry.bib_entry_id)}
                  disabled={isRunning}
                  className="mt-1 accent-emerald-600"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-800 leading-snug">{entry.title}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {entry.authors.length > 0 && <span>{entry.authors.slice(0, 3).join(', ')}{entry.authors.length > 3 ? ' et al.' : ''}</span>}
                    {entry.year && <span className="ml-2">({entry.year})</span>}
                    {entry.journal && <span className="ml-2">{entry.journal}</span>}
                  </p>
                  <p className="text-xs text-gray-300 mt-0.5">
                    {entry.file_type === 'pdf' ? '📄' : '📝'} {entry.file_name}
                  </p>
                </div>
              </label>
            ))}
          </div>
        )}

        {selected && (
          <div className="mt-4 flex items-end gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">并发数</label>
              <select
                value={maxWorkers}
                onChange={(e) => setMaxWorkers(Number(e.target.value))}
                disabled={isRunning}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none disabled:bg-gray-100"
              >
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleStart}
              disabled={isRunning || !apiKey}
              className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300 transition-colors"
            >
              {isRunning ? '翻译进行中...' : '翻译选中文献'}
            </button>
            {!apiKey && (
              <p className="text-xs text-red-500">请先设置 API Key</p>
            )}
          </div>
        )}
      </div>

      {(isRunning || (jobId && jobStatus)) && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            {selected ? selected.title : '翻译进度'}
          </h3>

          <div className="mb-2">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-gray-600">{currentStage}</span>
              <span className="font-medium text-emerald-700">{progress}%</span>
            </div>
            <div className="h-2.5 w-full rounded-full bg-gray-100">
              <div
                className="h-2.5 rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {isRunning && (
            <button
              onClick={handleCancel}
              className="mt-3 rounded-lg bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 transition-colors"
            >
              取消翻译
            </button>
          )}

          {jobStatus === 'failed' && errorMsg && (
            <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              <span className="font-semibold">错误：</span>{errorMsg}
            </div>
          )}

          {jobStatus === 'canceled' && (
            <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
              翻译已取消
            </div>
          )}
        </div>
      )}

      {artifacts.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">翻译结果</h3>
          <div className="space-y-3">
            {artifacts.map((art) => (
              <div
                key={art.id}
                className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{art.filename}</p>
                  <p className="text-xs text-gray-400">
                    {art.artifact_type === 'translation_md' ? '中文重述' : '术语词典'}
                    {art.size_bytes ? ` · ${(art.size_bytes / 1024).toFixed(1)} KB` : ''}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handlePreview(art)}
                    className="rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 transition-colors"
                  >
                    预览
                  </button>
                  <button
                    onClick={() => handleDownload(art)}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 transition-colors"
                  >
                    下载
                  </button>
                  {art.artifact_type === 'translation_md' && selected && (
                    <button
                      onClick={() => navigate(`/workspace/cards/reader/${selected.bib_entry_id}?view=translated`)}
                      className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-700 transition-colors"
                    >
                      阅读译文并制卡
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
