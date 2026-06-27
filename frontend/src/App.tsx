import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMemo } from 'react'
import { marked } from 'marked'
import './index.css'
import CardLibrary from './CardLibrary'
import LibraryTab from './LibraryTab'
import MarkdownReader from './MarkdownReader'
import ReferenceTraceTab from './ReferenceTraceTab'
import TemplateMarket from './TemplateMarket'
import TranslationTab from './TranslationTab'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'
import { apiFetch } from './lib/api-fetch'
import { useAuthStore } from './store/auth'
import { CompareView } from './components/CompareView'
import ConflictDialog from './components/ConflictDialog'
import BatchConflictDialog from './components/BatchConflictDialog'

// Tab definitions
const TABS = [
  { id: 'filter', label: '文献筛选', icon: '□' },
  { id: 'long', label: '长文本精读', icon: '➤' },
  { id: 'compare-long', label: '长文本对比', icon: '⇄' },
  { id: 'quant', label: '七步精读', icon: '△' },
  { id: 'compare-7step', label: '七步对比', icon: '⇄' },
  { id: 'qual', label: '四步精读', icon: '◉' },
  { id: 'compare-4step', label: '四步对比', icon: '⇄' },
  { id: 'translation', label: '全文翻译', icon: '文' },
  { id: 'library', label: '我的文献库', icon: '📚' },
  { id: 'references', label: '参考文献梳理', icon: '🔗' },
  { id: 'prompts', label: '提示词管理', icon: '⚙' },
  { id: 'history', label: '历史记录', icon: '📁' },
]

const CARD_TAB = { id: 'cards', label: '卡片笔记', icon: '▣' }
const AGENT_TAB = { id: 'agent', label: 'AI 助手', icon: 'AI' }
const TAB_IDS = new Set(TABS.map((tab) => tab.id))
const LEGACY_API_KEY_STORAGE = 'deepseek_api_key'
type ApiProvider = 'deepseek' | 'mimo-payg' | 'mimo-token-plan'
const AGENT_FOLDER_EXTENSIONS = new Set(['.pdf', '.md', '.markdown'])
const AGENT_FOLDER_UPLOAD_LIMIT = 200
const IMPORT_CHUNK_SIZE = 4 * 1024 * 1024

type AgentInboxBatch = {
  batch_id?: string
  total_files?: number
  succeeded?: number
  failed?: number
  status?: string
  created_at?: string
}

type AgentInboxUploadSummary = {
  batch_id?: string
  status?: string
  total_files?: number
  succeeded?: number
  failed?: number
  imported_count?: number
  deduplicated_count?: number
  matched_count?: number
  unmatched_count?: number
  error_counts?: Record<string, number>
  failed_examples?: Array<{ filename?: string; error?: string; message?: string }>
  recommendations?: string[]
  created_at?: string
}

type ProviderCheckResult = {
  ok: boolean
  provider?: string
  provider_label?: string
  base_url?: string
  model?: string
  key_prefix?: string
  explicit_provider?: string | null
  latency_ms?: number
  response_preview?: string
  checked_at?: string
}

type AgentFolderFile = File & {
  webkitRelativePath?: string
}

type ImportTaskStatus = {
  job_id: string
  mode?: 'merge_append' | 'merge_replace'
  status: 'pending' | 'running' | 'success' | 'failed'
  progress: number
  current_stage: string
  error_msg: string | null
  result: Record<string, unknown> | null
}

type ImportMode = 'merge_append' | 'merge_replace'

function getAgentFolderFilename(file: File): string {
  const folderFile = file as AgentFolderFile
  return folderFile.webkitRelativePath || file.name || ''
}

function getApiKeyStorageKey(username?: string | null) {
  const normalized = username?.trim()
  return normalized ? `deepseek_api_key:${normalized}` : null
}

function getApiProviderStorageKey(username?: string | null) {
  const normalized = username?.trim()
  return normalized ? `llm_api_provider:${normalized}` : null
}

function normalizeApiProvider(value?: string | null): ApiProvider {
  if (value === 'mimo-payg' || value === 'mimo-token-plan') return value
  return 'deepseek'
}

function formatApiKeyForProvider(apiKey: string, provider: ApiProvider): string {
  const key = apiKey.trim()
  if (!key) return ''
  if (provider === 'mimo-payg') return key.startsWith('mimo:') ? key : `mimo:${key}`
  if (provider === 'mimo-token-plan') return key.startsWith('mimo-token:') ? key : `mimo-token:${key}`
  return key
}

function getInitialTab(pathname: string, search: string): string {
  if (pathname.startsWith('/workspace/cards')) {
    return 'cards'
  }
  if (pathname.startsWith('/workspace/library')) {
    return 'library'
  }
  const fromQuery = new URLSearchParams(search).get('tab') || ''
  if (fromQuery === 'compare') {
    return 'compare-long'
  }
  if (fromQuery === 'agent') {
    return 'agent'
  }
  return TAB_IDS.has(fromQuery) && fromQuery !== 'library' ? fromQuery : 'filter'
}

function promptForApiKey(): string {
  const username = useAuthStore.getState().user?.username
  const storageKey = getApiKeyStorageKey(username)
  const providerKey = getApiProviderStorageKey(username)
  const existing = storageKey ? localStorage.getItem(storageKey) : ''
  const provider = normalizeApiProvider(providerKey ? localStorage.getItem(providerKey) : null)
  if (existing) return formatApiKeyForProvider(existing, provider)
  const key = prompt('请输入 API Key（DeepSeek/sk、小米按量/sk、小米 Token Plan/tp）：')
  if (!key || !key.trim()) return ''
  const trimmed = key.trim()
  if (storageKey) {
    localStorage.setItem(storageKey, trimmed)
  }
  return formatApiKeyForProvider(trimmed, provider)
}

type FeedbackItem = {
  id: number
  feedback_type: string
  title: string
  content: string
  status: string
  priority: string
  public_reply?: string | null
  created_at: string
  updated_at: string
}

function FeedbackDialog({
  mode,
  onClose,
}: {
  mode: 'create' | 'mine'
  onClose: () => void
}) {
  const [activeMode, setActiveMode] = useState(mode)
  const [feedbackType, setFeedbackType] = useState('bug')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [items, setItems] = useState<FeedbackItem[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadMine = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/feedback/my')
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || `加载失败（HTTP ${response.status}）`)
      setItems(Array.isArray(data) ? data : [])
    } catch (err: any) {
      setError(err.message || '加载反馈失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeMode === 'mine') {
      void loadMine()
    }
  }, [activeMode])

  const submitFeedback = async () => {
    if (!title.trim() || !content.trim()) {
      setError('请填写标题和反馈内容。')
      return
    }
    setLoading(true)
    setMessage('')
    setError('')
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feedback_type: feedbackType,
          title: title.trim(),
          content: content.trim(),
          route: `${window.location.pathname}${window.location.search}`,
          app_version: 'web',
        }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || `提交失败（HTTP ${response.status}）`)
      setTitle('')
      setContent('')
      setMessage('反馈已提交。管理员处理后会在“我的反馈”里显示回复。')
      setActiveMode('mine')
    } catch (err: any) {
      setError(err.message || '提交反馈失败。')
    } finally {
      setLoading(false)
    }
  }

  const statusLabel: Record<string, string> = {
    open: '待处理',
    triaged: '已分流',
    in_progress: '处理中',
    resolved: '已解决',
    closed: '已关闭',
    reopened: '重新打开',
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[86vh] w-full max-w-2xl flex-col rounded-2xl border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900">用户反馈</h2>
            <p className="mt-1 text-sm text-gray-500">反馈会保留给管理员排查和改进产品，不会进入 .dra 导出包。</p>
          </div>
          <button onClick={onClose} className="rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-600 hover:bg-gray-200">
            关闭
          </button>
        </div>
        <div className="border-b border-gray-100 px-5 py-3">
          <div className="inline-flex rounded-lg bg-gray-100 p-1 text-sm">
            <button
              onClick={() => setActiveMode('create')}
              className={`rounded-md px-3 py-1.5 ${activeMode === 'create' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
            >
              提交反馈
            </button>
            <button
              onClick={() => setActiveMode('mine')}
              className={`rounded-md px-3 py-1.5 ${activeMode === 'mine' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
            >
              我的反馈
            </button>
          </div>
        </div>
        <div className="overflow-y-auto px-5 py-4">
          {(message || error) && (
            <div className="mb-4 space-y-2">
              {message && <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</div>}
              {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
            </div>
          )}
          {activeMode === 'create' ? (
            <div className="space-y-4">
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-gray-700">类型</span>
                <select
                  value={feedbackType}
                  onChange={(event) => setFeedbackType(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                >
                  <option value="bug">问题/报错</option>
                  <option value="reading_quality">精读质量</option>
                  <option value="translation">翻译质量</option>
                  <option value="data_issue">数据/文献库问题</option>
                  <option value="feature">功能建议</option>
                  <option value="question">使用疑问</option>
                  <option value="other">其他</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-gray-700">标题</span>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  maxLength={160}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                  placeholder="一句话描述问题或建议"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-gray-700">内容</span>
                <textarea
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  rows={7}
                  maxLength={5000}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                  placeholder="请描述你遇到的情况、期望结果、实际结果。当前页面路径会自动附带。"
                />
              </label>
              <button
                onClick={() => void submitFeedback()}
                disabled={loading}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {loading ? '提交中...' : '提交反馈'}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {loading && <div className="py-8 text-center text-sm text-gray-400">加载中...</div>}
              {!loading && items.length === 0 && <div className="py-8 text-center text-sm text-gray-400">还没有反馈记录。</div>}
              {items.map((item) => (
                <div key={item.id} className="rounded-xl border border-gray-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-gray-900">{item.title}</div>
                      <div className="mt-1 text-xs text-gray-500">
                        #{item.id} · {statusLabel[item.status] || item.status} · {new Date(item.updated_at).toLocaleString()}
                      </div>
                    </div>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{item.priority}</span>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm text-gray-600">{item.content}</p>
                  {item.public_reply && (
                    <div className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                      <span className="font-medium">管理员回复：</span>{item.public_reply}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [activeTab, setActiveTab] = useState(() => getInitialTab(location.pathname, location.search))
  const [apiKey, setApiKey] = useState('')
  const [apiProvider, setApiProvider] = useState<ApiProvider>('deepseek')
  const [showKeyInput, setShowKeyInput] = useState(false)
  const [tempKey, setTempKey] = useState('')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<Record<string, unknown> | null>(null)
  const [importStatus, setImportStatus] = useState<ImportTaskStatus | null>(null)
  const [selectedImportFile, setSelectedImportFile] = useState<File | null>(null)
  const [importMode, setImportMode] = useState<ImportMode>('merge_append')
  const [canShutdownApp, setCanShutdownApp] = useState(false)
  const [agentTabVisible, setAgentTabVisible] = useState(false)
  const [agentInboxBatch, setAgentInboxBatch] = useState<AgentInboxBatch | null>(null)
  const [agentInboxSummary, setAgentInboxSummary] = useState<AgentInboxUploadSummary | null>(null)
  const [agentFolderFiles, setAgentFolderFiles] = useState<File[]>([])
  const [agentFolderSkippedCount, setAgentFolderSkippedCount] = useState(0)
  const [agentFolderUploading, setAgentFolderUploading] = useState(false)
  const [agentFolderStatus, setAgentFolderStatus] = useState('')
  const [agentFolderInputKey, setAgentFolderInputKey] = useState(0)
  const [feedbackDialogMode, setFeedbackDialogMode] = useState<'create' | 'mine' | null>(null)
  const [providerCheckResult, setProviderCheckResult] = useState<ProviderCheckResult | null>(null)
  const [providerCheckError, setProviderCheckError] = useState<AgentStructuredError | null>(null)
  const [checkingProvider, setCheckingProvider] = useState(false)

  const cardTabVisible = activeTab === 'cards' || location.pathname.startsWith('/workspace/cards')
  const visibleTabs = useMemo(() => {
    const tabs = cardTabVisible ? [...TABS, CARD_TAB] : TABS
    return agentTabVisible ? [...tabs, AGENT_TAB] : tabs
  }, [agentTabVisible, cardTabVisible])

  useEffect(() => {
    const storageKey = getApiKeyStorageKey(user?.username)
    if (!storageKey) {
      setApiKey('')
      setTempKey('')
      setApiProvider('deepseek')
      setProviderCheckResult(null)
      setProviderCheckError(null)
      setAgentInboxBatch(null)
      setAgentInboxSummary(null)
      return
    }
    const providerKey = getApiProviderStorageKey(user?.username)
    const saved = localStorage.getItem(storageKey)
    const savedProvider = providerKey ? localStorage.getItem(providerKey) : null
    setApiKey(saved || '')
    setApiProvider(normalizeApiProvider(savedProvider))
    setTempKey('')
    setProviderCheckResult(null)
    setProviderCheckError(null)
  }, [user?.username])

  const requestApiKey = useMemo(
    () => formatApiKeyForProvider(apiKey, apiProvider),
    [apiKey, apiProvider],
  )

  useEffect(() => {
    const nextTab = getInitialTab(location.pathname, location.search)
    if (nextTab === 'agent') {
      setAgentTabVisible(true)
    }
    setActiveTab(nextTab)
  }, [location.pathname, location.search])

  useEffect(() => {
    let ignore = false
    fetch('/api/deploy/runtime')
      .then((response) => response.ok ? response.json() : null)
      .then((data) => {
        if (!ignore) setCanShutdownApp(Boolean(data?.can_shutdown))
      })
      .catch(() => {
        if (!ignore) setCanShutdownApp(false)
      })
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    let ignore = false
    apiFetch('/api/agent/settings')
      .then((response) => response.ok ? response.json() : null)
      .then((data) => {
        if (ignore || !data) return
        setAgentInboxBatch(data.inbox_batch || null)
        setAgentInboxSummary(data.inbox_upload_summary || null)
      })
      .catch(() => {})
    return () => {
      ignore = true
    }
  }, [user?.username])

  const handleTabChange = (tabId: string) => {
    setActiveTab(tabId)
    if (tabId === 'library') {
      if (location.pathname !== '/workspace/library') {
        navigate('/workspace/library')
      }
      return
    }
    if (tabId === 'cards') {
      if (location.pathname !== '/workspace/cards') {
        navigate('/workspace/cards')
      }
      return
    }
    const params = new URLSearchParams(location.search)
    params.set('tab', tabId)
    const nextSearch = params.toString()
    const nextUrl = nextSearch ? `/workspace?${nextSearch}` : '/workspace'
    if (`${location.pathname}${location.search}` !== nextUrl) {
      navigate(nextUrl)
    }
  }

  const handleSaveKey = () => {
    const storageKey = getApiKeyStorageKey(user?.username)
    const providerKey = getApiProviderStorageKey(user?.username)
    if (!storageKey || !tempKey.trim()) return
    const key = tempKey.trim()
    setApiKey(key)
    localStorage.setItem(storageKey, key)
    if (providerKey) {
      localStorage.setItem(providerKey, apiProvider)
    }
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    setProviderCheckResult(null)
    setProviderCheckError(null)
    setShowKeyInput(false)
    setTempKey('')
  }

  const handleDeleteKey = () => {
    const storageKey = getApiKeyStorageKey(user?.username)
    const providerKey = getApiProviderStorageKey(user?.username)
    setApiKey('')
    setTempKey('')
    if (storageKey) {
      localStorage.removeItem(storageKey)
    }
    if (providerKey) {
      localStorage.removeItem(providerKey)
    }
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    setProviderCheckResult(null)
    setProviderCheckError(null)
    setShowKeyInput(false)
  }

  const handleCheckProvider = async () => {
    const candidateKey = (tempKey.trim() || apiKey).trim()
    if (!candidateKey || checkingProvider) return
    setCheckingProvider(true)
    setProviderCheckResult(null)
    setProviderCheckError(null)
    try {
      const response = await apiFetch('/api/agent/provider-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: formatApiKeyForProvider(candidateKey, apiProvider) }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        const structuredError = normalizeAgentErrorPayload(data?.detail ?? data)
        if (structuredError) {
          setProviderCheckError(structuredError)
          return
        }
        throw new Error(data?.detail || `测试连接失败（HTTP ${response.status}）`)
      }
      setProviderCheckResult(data)
    } catch (err) {
      const structuredError = normalizeAgentErrorPayload(err)
      if (structuredError) {
        setProviderCheckError(structuredError)
      } else {
        setProviderCheckError({
          code: 'provider_check_failed',
          message: err instanceof Error ? err.message : '测试连接失败。',
          stage: 'provider_probe',
          retryable: true,
          severity: 'error',
        })
      }
    } finally {
      setCheckingProvider(false)
    }
  }

  const handleOpenAgent = () => {
    setAgentTabVisible(true)
    setShowKeyInput(false)
    handleTabChange('agent')
  }

  const handleAgentFolderSelection = (fileList: FileList | null) => {
    const selected = Array.from(fileList || [])
    const supported = selected.filter((file) => {
      const filename = getAgentFolderFilename(file).toLowerCase()
      const dotIndex = filename.lastIndexOf('.')
      const extension = dotIndex >= 0 ? filename.slice(dotIndex) : ''
      return AGENT_FOLDER_EXTENSIONS.has(extension)
    })
    setAgentFolderFiles(supported.slice(0, AGENT_FOLDER_UPLOAD_LIMIT))
    setAgentFolderSkippedCount(selected.length - supported.length + Math.max(0, supported.length - AGENT_FOLDER_UPLOAD_LIMIT))
    if (selected.length && !supported.length) {
      setAgentFolderStatus('这个文件夹里没有可上传的 PDF/Markdown 文件。')
    } else if (supported.length > AGENT_FOLDER_UPLOAD_LIMIT) {
      setAgentFolderStatus(`一次最多上传 ${AGENT_FOLDER_UPLOAD_LIMIT} 个 PDF/Markdown 文件，已自动截取前 ${AGENT_FOLDER_UPLOAD_LIMIT} 个。`)
    } else {
      setAgentFolderStatus('')
    }
  }

  const handleUploadAgentFolder = async () => {
    if (!agentFolderFiles.length || agentFolderUploading) return
    setAgentFolderUploading(true)
    setAgentFolderStatus('上传中...')
    try {
      const formData = new FormData()
      agentFolderFiles.forEach((file) => {
        formData.append('files', file, getAgentFolderFilename(file))
      })
      const response = await apiFetch('/api/agent/inbox/upload-folder', { method: 'POST', body: formData })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || `上传失败（HTTP ${response.status}）`)
      }
      setAgentInboxBatch(data.settings?.inbox_batch || {
        batch_id: data.batch_id,
        total_files: data.total,
        succeeded: data.succeeded,
        failed: data.failed,
        status: data.failed ? 'partial' : 'success',
      })
      setAgentInboxSummary(data.summary || data.settings?.inbox_upload_summary || null)
      setAgentFolderFiles([])
      setAgentFolderSkippedCount(0)
      setAgentFolderInputKey((value) => value + 1)
      setAgentFolderStatus(`已上传 ${data.succeeded || 0} 个文件，失败 ${data.failed || 0} 个。AI 助手现在会扫描这批文件。`)
    } catch (err) {
      setAgentFolderStatus(err instanceof Error ? err.message : '上传失败。')
    } finally {
      setAgentFolderUploading(false)
    }
  }

  const roleBadgeClass =
    user?.role === 'admin'
      ? 'bg-violet-100 text-violet-700'
      : user?.role === 'vip'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-gray-100 text-gray-600'

  const roleLabel =
    user?.role === 'admin' ? 'ADMIN' : user?.role === 'vip' ? 'VIP' : 'NORMAL'

  const handleLogout = async () => {
    setShowUserMenu(false)
    await logout()
    navigate('/login', { replace: true })
  }

  const accessToken = useAuthStore((state) => state.accessToken)

  const handleShutdownApp = async () => {
    const confirmed = window.confirm('确定要退出 Deep Reading Agent 吗？本地服务会停止，当前浏览器页面将无法继续使用。')
    if (!confirmed) return
    setShowUserMenu(false)
    try {
      const response = await fetch('/api/deploy/shutdown', {
        method: 'POST',
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `退出失败（HTTP ${response.status}）`)
      }
      window.alert('Deep Reading Agent 正在退出。可以关闭这个浏览器页面。')
    } catch (err: any) {
      window.alert(err.message || '退出应用失败')
    }
  }

  const handleExport = async () => {
    const confirmed = window.confirm(
      user?.role === 'normal'
        ? `将导出您的全部数据（文献库、精读结果、源文件、提示词等），可能需要数分钟。\n\n⚠ 您的数据将在每天 0 点自动清理，建议尽快导出备份。`
        : '将导出您的全部数据（文献库、精读结果、源文件、提示词等），可能需要数分钟。'
    )
    if (!confirmed) return
    setExporting(true)
    setShowUserMenu(false)
    try {
      const response = await fetch('/api/data/export', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `导出失败（HTTP ${response.status}）`)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
      a.download = `export_${timestamp}_${user?.username}.dra`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      window.alert(err.message || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const handleImportClick = () => {
    setShowUserMenu(false)
    setImportDialogOpen(true)
    setSelectedImportFile(null)
    setImportResult(null)
    setImportStatus(null)
    setImportMode('merge_append')
  }

  const handleImport = async (file: File, mode: ImportMode) => {
    setImporting(true)
    setImportResult(null)
    setImportStatus(null)
    try {
      const totalChunks = Math.ceil(file.size / IMPORT_CHUNK_SIZE)
      const initForm = new FormData()
      initForm.append('filename', file.name)
      initForm.append('total_size', String(file.size))
      initForm.append('total_chunks', String(totalChunks))
      initForm.append('mode', mode)

      setImportStatus({
        job_id: '',
        status: 'pending',
        progress: 0,
        current_stage: '正在创建分片上传会话...',
        error_msg: null,
        result: null,
      })

      const initResponse = await fetch('/api/data/import/chunk/init', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: initForm,
      })
      const initData = await initResponse.json().catch(() => null)
      if (!initResponse.ok) {
        throw new Error(initData?.detail || `创建上传会话失败（HTTP ${initResponse.status}）`)
      }

      const uploadId = initData?.upload_id
      if (!uploadId) throw new Error('创建上传会话失败：后端未返回 upload_id。')

      for (let index = 0; index < totalChunks; index += 1) {
        const start = index * IMPORT_CHUNK_SIZE
        const end = Math.min(file.size, start + IMPORT_CHUNK_SIZE)
        const chunkForm = new FormData()
        chunkForm.append('upload_id', uploadId)
        chunkForm.append('chunk_index', String(index))
        chunkForm.append('chunk', file.slice(start, end), `${file.name}.part${index}`)
        const chunkResponse = await fetch('/api/data/import/chunk', {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
          body: chunkForm,
        })
        const chunkData = await chunkResponse.json().catch(() => null)
        if (!chunkResponse.ok) {
          throw new Error(chunkData?.detail || `上传第 ${index + 1} 个分片失败（HTTP ${chunkResponse.status}）`)
        }
        setImportStatus({
          job_id: '',
          status: 'pending',
          progress: Math.min(20, Math.round(((index + 1) / totalChunks) * 20)),
          current_stage: `正在上传导入包分片 ${index + 1}/${totalChunks}...`,
          error_msg: null,
          result: null,
        })
      }

      const completeForm = new FormData()
      completeForm.append('upload_id', uploadId)
      setImportStatus({
        job_id: '',
        status: 'pending',
        progress: 20,
        current_stage: '正在组装导入包并启动后台任务...',
        error_msg: null,
        result: null,
      })

      const completeResponse = await fetch('/api/data/import/chunk/complete', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: completeForm,
      })
      const data = await completeResponse.json().catch(() => null)
      if (!completeResponse.ok) {
        throw new Error(data?.detail || `启动导入任务失败（HTTP ${completeResponse.status}）`)
      }

      const jobId = data?.job_id
      if (!jobId) throw new Error('导入任务创建失败：后端未返回任务 ID。')

      setImportStatus({
        job_id: jobId,
        status: data.status || 'pending',
        progress: 0,
        current_stage: data.message || '导入任务已开始。',
        error_msg: null,
        result: null,
      })

      let finalStatus: ImportTaskStatus | null = null
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
        const statusResponse = await fetch(`/api/data/import/${encodeURIComponent(jobId)}/status`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        const statusData = await statusResponse.json().catch(() => null)
        if (!statusResponse.ok) {
          throw new Error(statusData?.detail || `查询导入进度失败（HTTP ${statusResponse.status}）`)
        }
        finalStatus = statusData as ImportTaskStatus
        setImportStatus(finalStatus)
        if (finalStatus.status === 'success' || finalStatus.status === 'failed') {
          break
        }
      }

      if (finalStatus?.status === 'failed') {
        throw new Error(finalStatus.error_msg || finalStatus.current_stage || '导入失败。')
      }

      const result = finalStatus?.result || {}
      setImportResult(result)
      const modeLabel = mode === 'merge_replace' ? '覆盖导入' : '追加导入'
      window.alert(`${modeLabel}成功！已恢复 ${result.files_restored || 0} 个文件。页面即将刷新。`)
      window.location.reload()
    } catch (err: any) {
      console.error('[import error]', err)
      window.alert(err.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const shellInnerClass = 'mx-auto min-w-0 w-full max-w-[1800px] flex-1 px-3 py-4 sm:px-4 sm:py-5 lg:px-6 lg:py-6 xl:px-8'

  return (
    <div className="min-h-screen flex flex-col bg-white text-gray-900">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex w-full max-w-[1800px] items-start justify-between gap-3 px-3 py-3 sm:px-4 sm:py-4 lg:px-6 xl:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="shrink-0 text-2xl">❤️‍🔥</span>
            <div>
              <h1 className="text-lg font-bold text-gray-900 sm:text-xl">Deep Reading Agent</h1>
              <p className="text-xs text-gray-500 sm:text-sm">学术论文深度精读系统</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700 sm:inline-flex">
              {apiProvider === 'deepseek' ? 'DeepSeek' : 'MiMo'} ✓
            </span>
            <div className="relative">
              <button
                onClick={() => setShowUserMenu((value) => !value)}
                className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm hover:border-emerald-300"
              >
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-sm font-semibold text-emerald-700">
                  {user?.username?.slice(0, 1).toUpperCase() || 'U'}
                </span>
                <div className="text-left">
                  <div className="text-sm font-medium text-gray-800">{user?.username || '未登录'}</div>
                  <div className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${roleBadgeClass}`}>
                    {roleLabel}
                  </div>
                </div>
              </button>

              {showUserMenu && (
                <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-gray-200 bg-white p-3 shadow-lg">
                  <div className="border-b border-gray-100 px-1 pb-3">
                    <div className="text-sm font-semibold text-gray-800">{user?.username}</div>
                    <div className="mt-1 text-xs text-gray-500">{user?.email || '未设置邮箱'}</div>
                  </div>

                  <div className="mt-3 space-y-2">
                    {user?.role === 'admin' && (
                      <button
                        onClick={() => {
                          setShowUserMenu(false)
                          navigate('/admin')
                        }}
                        className="flex w-full items-center justify-between rounded-lg bg-violet-50 px-3 py-2 text-sm text-violet-700 hover:bg-violet-100"
                      >
                        <span>管理员后台</span>
                        <span>↗</span>
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setShowKeyInput((value) => !value)
                        setShowUserMenu(false)
                      }}
                      className="flex w-full items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <span>{apiKey ? '管理 API Key' : '设置 API Key'}</span>
                      <span className={apiKey ? 'text-emerald-600' : 'text-gray-400'}>{apiKey ? '已设置' : '未设置'}</span>
                    </button>
                    <button
                      onClick={handleOpenAgent}
                      className="flex w-full items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 hover:bg-emerald-100"
                    >
                      <span>唤起 AI 助手</span>
                      <span>AI</span>
                    </button>
                    <button
                      onClick={() => {
                        setFeedbackDialogMode('create')
                        setShowUserMenu(false)
                      }}
                      className="flex w-full items-center justify-between rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 hover:bg-rose-100"
                    >
                      <span>反馈问题</span>
                      <span>!</span>
                    </button>
                    <button
                      onClick={() => {
                        setFeedbackDialogMode('mine')
                        setShowUserMenu(false)
                      }}
                      className="flex w-full items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <span>我的反馈</span>
                      <span>≡</span>
                    </button>
                    <button
                      onClick={handleExport}
                      disabled={exporting}
                      className="flex w-full items-center justify-between rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                    >
                      <span>{exporting ? '正在导出...' : '导出我的数据'}</span>
                      <span>↓</span>
                    </button>
                    <button
                      onClick={handleImportClick}
                      disabled={importing}
                      className="flex w-full items-center justify-between rounded-lg bg-teal-50 px-3 py-2 text-sm text-teal-700 hover:bg-teal-100 disabled:opacity-50"
                    >
                      <span>{importing ? '正在导入...' : '导入数据'}</span>
                      <span>↑</span>
                    </button>
                    <button
                      onClick={handleLogout}
                      className="flex w-full items-center justify-between rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700 hover:bg-amber-100"
                    >
                      <span>切换账号</span>
                      <span>→</span>
                    </button>
                    <button
                      onClick={handleLogout}
                      className="flex w-full items-center justify-between rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 hover:bg-red-100"
                    >
                      <span>退出登录</span>
                      <span>×</span>
                    </button>
                    {canShutdownApp && (
                      <button
                        onClick={handleShutdownApp}
                        className="flex w-full items-center justify-between rounded-lg bg-gray-900 px-3 py-2 text-sm text-white hover:bg-gray-800"
                      >
                        <span>退出应用</span>
                        <span>⏻</span>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {showKeyInput && (
        <div className="border-b border-emerald-100 bg-emerald-50/70">
          <div className="mx-auto w-full max-w-[1800px] px-3 py-3 sm:px-4 sm:py-4 lg:px-6 xl:px-8">
            <div className="max-w-xl rounded-xl border border-emerald-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">LLM API Key</h3>
              <select
                value={apiProvider}
                onChange={(e) => {
                  const provider = normalizeApiProvider(e.target.value)
                  setApiProvider(provider)
                  setProviderCheckResult(null)
                  setProviderCheckError(null)
                  const providerKey = getApiProviderStorageKey(user?.username)
                  if (providerKey) localStorage.setItem(providerKey, provider)
                }}
                className="mb-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              >
                <option value="deepseek">DeepSeek（sk-）</option>
                <option value="mimo-payg">小米 MiMo 按量付费（sk-，中国集群）</option>
                <option value="mimo-token-plan">小米 MiMo Token Plan（tp-，中国集群）</option>
              </select>
              <input
                type="password"
                value={tempKey}
                onChange={(e) => {
                  setTempKey(e.target.value)
                  setProviderCheckResult(null)
                  setProviderCheckError(null)
                }}
                placeholder={apiKey ? '••••••••••••••••' : apiProvider === 'mimo-token-plan' ? 'tp-...' : 'sk-...'}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-gray-400">仅保存在当前账号对应的浏览器 localStorage 中，不会与其他账号共用；小米模式固定使用中国集群</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleSaveKey}
                  disabled={!tempKey.trim()}
                  className="flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300 transition-colors"
                >
                  保存
                </button>
                <button
                  onClick={() => void handleCheckProvider()}
                  disabled={checkingProvider || !(tempKey.trim() || apiKey)}
                  className="rounded-lg bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700 hover:bg-sky-100 disabled:bg-gray-100 disabled:text-gray-400 transition-colors"
                >
                  {checkingProvider ? '检测中...' : '测试连接'}
                </button>
                {apiKey && (
                  <button
                    onClick={handleDeleteKey}
                    className="rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-100 transition-colors"
                  >
                    删除
                  </button>
                )}
                <button
                  onClick={() => setShowKeyInput(false)}
                  className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-medium text-gray-600 hover:bg-gray-200 transition-colors"
                >
                  收起
                </button>
              </div>
              {providerCheckResult && (
                <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 text-sm text-emerald-900">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-semibold">连接测试成功</div>
                    <span className="rounded-full border border-emerald-200 bg-white px-2 py-0.5 text-xs font-medium text-emerald-700">
                      {providerCheckResult.provider || 'unknown'}
                    </span>
                  </div>
                  <div className="mt-2 grid gap-2 text-xs text-emerald-900 md:grid-cols-2">
                    <div>Provider：{providerCheckResult.provider_label || providerCheckResult.provider || '-'}</div>
                    <div>模型：{providerCheckResult.model || '-'}</div>
                    <div className="break-all">Base URL：{providerCheckResult.base_url || '-'}</div>
                    <div>耗时：{typeof providerCheckResult.latency_ms === 'number' ? `${providerCheckResult.latency_ms} ms` : '-'}</div>
                  </div>
                  {providerCheckResult.response_preview && (
                    <div className="mt-2 rounded-md border border-emerald-100 bg-white px-3 py-2 text-xs text-gray-700">
                      返回预览：{providerCheckResult.response_preview}
                    </div>
                  )}
                </div>
              )}
              {providerCheckError && (
                <div className="mt-3">
                  <AgentErrorCard error={providerCheckError} />
                </div>
              )}

              <div className="mt-5 border-t border-gray-100 pt-4">
                <h3 className="mb-2 text-sm font-semibold text-gray-700">上传文件夹给 AI 助手</h3>
                <input
                  key={agentFolderInputKey}
                  type="file"
                  multiple
                  ref={(element) => {
                    element?.setAttribute('webkitdirectory', '')
                    element?.setAttribute('directory', '')
                  }}
                  onChange={(event) => {
                    handleAgentFolderSelection(event.target.files)
                  }}
                  className="block w-full text-sm text-gray-500 file:mr-4 file:rounded-lg file:border-0 file:bg-emerald-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-emerald-700 hover:file:bg-emerald-100"
                />
                <p className="mt-1 text-xs text-gray-400">
                  在线版不会读取本地路径。只有你主动选择并上传的 PDF/Markdown 会进入 AI 助手可扫描的临时文件夹。
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={() => void handleUploadAgentFolder()}
                    disabled={!agentFolderFiles.length || agentFolderUploading}
                    className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:bg-gray-300"
                  >
                    {agentFolderUploading ? '上传中...' : `上传文件夹${agentFolderFiles.length ? `（${agentFolderFiles.length} 个支持文件）` : ''}`}
                  </button>
                  {agentFolderFiles.length > 0 && (
                    <button
                      onClick={() => {
                        setAgentFolderFiles([])
                        setAgentFolderSkippedCount(0)
                        setAgentFolderStatus('')
                        setAgentFolderInputKey((value) => value + 1)
                      }}
                      className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-200"
                    >
                      清空选择
                    </button>
                  )}
                  <button
                    onClick={handleOpenAgent}
                    className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-100"
                  >
                    打开 AI 助手
                  </button>
                </div>
                {agentFolderStatus && (
                  <div className="mt-2 text-xs text-gray-600">{agentFolderStatus}</div>
                )}
                {!agentFolderStatus && (agentFolderFiles.length > 0 || agentFolderSkippedCount > 0) && (
                  <div className="mt-2 text-xs text-gray-600">
                    已选择 {agentFolderFiles.length} 个 PDF/Markdown
                    {agentFolderSkippedCount ? `，跳过 ${agentFolderSkippedCount} 个不支持或超出上限的文件` : ''}
                  </div>
                )}
                {agentInboxBatch && !agentFolderStatus && (
                  <div className="mt-2 text-xs text-emerald-700">
                    当前可扫描文件夹：已上传 {agentInboxBatch.total_files ?? 0} 个文件
                    {agentInboxBatch.created_at ? `，创建于 ${new Date(agentInboxBatch.created_at).toLocaleString()}` : ''}
                  </div>
                )}
                {agentInboxSummary && (
                  <div className="mt-4">
                    <AgentInboxSummaryCard summary={agentInboxSummary} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {user?.warning_msg && (
        <div className="border-b border-red-200 bg-red-50">
          <div className="mx-auto w-full max-w-[1800px] px-3 py-3 text-sm text-red-700 sm:px-4 lg:px-6 xl:px-8">
            <span className="font-semibold">⚠ 试用提醒：</span>
            <span>{user.warning_msg}</span>
          </div>
        </div>
      )}

      {/* Import Dialog */}
      {importDialogOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-gray-900">导入数据</h2>
            <div className="mt-3 space-y-3 text-sm text-gray-600">
              <p className="rounded-lg bg-red-50 p-3 text-red-700">
                <span className="font-semibold">⚠ 警告：</span>
                本次导入支持<span className="font-bold">追加</span>或<span className="font-bold">覆盖</span>模式，
                不会再先清空您当前的全部工作区数据。请根据需要选择模式。
              </p>
              <p>请选择 .dra 格式的导出包文件：</p>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="text-sm font-medium text-gray-800">导入模式</div>
                <label className="mt-2 flex cursor-pointer items-start gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    name="importMode"
                    checked={importMode === 'merge_append'}
                    onChange={() => setImportMode('merge_append')}
                  />
                  <span>追加导入：保留现有数据，重复项会按规则跳过或复用。</span>
                </label>
                <label className="mt-2 flex cursor-pointer items-start gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    name="importMode"
                    checked={importMode === 'merge_replace'}
                    onChange={() => setImportMode('merge_replace')}
                  />
                  <span>覆盖导入：仅替换与导入包冲突的数据，不会清空整个工作区。</span>
                </label>
              </div>
              <input
                type="file"
                accept=".dra"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null
                  setSelectedImportFile(file)
                }}
                className="block w-full text-sm text-gray-500 file:mr-4 file:rounded-lg file:border-0 file:bg-emerald-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-emerald-700 hover:file:bg-emerald-100"
              />
              {selectedImportFile && (
                <div className="rounded-lg bg-gray-50 p-2 text-sm text-gray-600">
                  已选择：{selectedImportFile.name}
                </div>
              )}
              {importStatus && (
                <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3 text-sm text-emerald-800">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">
                      {importStatus.status === 'failed' ? '导入失败' : importStatus.status === 'success' ? '导入完成' : '正在导入'}
                    </span>
                    <span>{Math.max(0, Math.min(100, importStatus.progress || 0))}%</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-emerald-600 transition-all"
                      style={{ width: `${Math.max(0, Math.min(100, importStatus.progress || 0))}%` }}
                    />
                  </div>
                  <div className="mt-2 text-xs">{importStatus.current_stage || '等待导入进度...'}</div>
                </div>
              )}
            </div>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setImportDialogOpen(false)}
                disabled={importing}
                className="flex-1 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={() => {
                  if (!selectedImportFile) {
                    window.alert('请先选择 .dra 文件')
                    return
                  }
                  const confirmed = window.confirm(
                    importMode === 'merge_replace'
                      ? '确定要以“覆盖导入”模式继续吗？系统只会替换与导入包冲突的数据，不会先清空整个工作区。'
                      : '确定要以“追加导入”模式继续吗？系统会保留现有数据，并尽量复用或跳过重复项。'
                  )
                  if (!confirmed) return
                  handleImport(selectedImportFile, importMode)
                }}
                disabled={importing || !selectedImportFile}
                className="flex-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {importing ? '正在导入...' : '确认导入'}
              </button>
            </div>
            {importResult && (
              <div className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
                <div className="font-semibold">导入结果</div>
                <div className="mt-1">
                  模式：{(importResult.mode as string) === 'merge_replace' ? '覆盖导入' : '追加导入'}
                </div>
                <div className="mt-1">
                  已恢复 {(importResult.files_restored as number) || 0} 个文件，缺失 {(importResult.files_missing as number) || 0} 个
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {feedbackDialogMode && (
        <FeedbackDialog
          mode={feedbackDialogMode}
          onClose={() => setFeedbackDialogMode(null)}
        />
      )}

      {/* Tab Navigation */}
      <nav className="border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="mx-auto w-full max-w-[1800px] px-2 sm:px-3 lg:px-6 xl:px-8">
          <div className="no-scrollbar flex gap-1 overflow-x-auto py-1">
            {visibleTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`whitespace-nowrap rounded-t-xl px-3 py-3 text-sm font-medium border-b-2 transition-colors sm:px-4 ${
                  activeTab === tab.id
                    ? 'border-emerald-500 text-emerald-700'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <span className="mr-1.5">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex flex-1 min-h-0">
        <div className={shellInnerClass}>
          {activeTab === 'filter' && <FilterTab apiKey={requestApiKey} />}
          {activeTab === 'long' && <LongTab apiKey={requestApiKey} />}
          {activeTab === 'quant' && <QuantTab apiKey={requestApiKey} />}
          {activeTab === 'qual' && <QualTab apiKey={requestApiKey} />}
          {activeTab === 'compare-long' && <CompareView mode="long" apiKey={requestApiKey || null} />}
          {activeTab === 'compare-7step' && <CompareView mode="quant" apiKey={requestApiKey || null} />}
          {activeTab === 'compare-4step' && <CompareView mode="qual" apiKey={requestApiKey || null} />}
          {activeTab === 'translation' && <TranslationTab apiKey={requestApiKey} />}
          {activeTab === 'agent' && <AgentTab apiKey={requestApiKey} />}
          {activeTab === 'library' && <LibraryTab apiKey={requestApiKey} />}
          {activeTab === 'cards' && location.pathname.includes('/reader') && <MarkdownReader apiKey={requestApiKey} />}
          {activeTab === 'cards' && !location.pathname.includes('/reader') && <CardLibrary />}
          {activeTab === 'references' && <ReferenceTraceTab apiKey={requestApiKey} />}
          {activeTab === 'prompts' && <PromptsTab apiKey={requestApiKey} />}
          {activeTab === 'history' && <HistoryTab />}
        </div>
      </main>
    </div>
  )
}

async function handleProtectedDownload(downloadPath: string, fallbackFilename: string) {
  await downloadWithAuth(`/api/download/${encodeURIComponent(downloadPath)}`, fallbackFilename)
}

type ReadingTaskKind = 'long' | 'quant' | 'qual'

function getReadingTaskStorageKey(kind: ReadingTaskKind) {
  return `dra_reading_task_${kind}`
}

function persistReadingTaskId(kind: ReadingTaskKind, taskId: string | null) {
  if (taskId) {
    localStorage.setItem(getReadingTaskStorageKey(kind), taskId)
  } else {
    localStorage.removeItem(getReadingTaskStorageKey(kind))
  }
}

function restoreReadingTaskId(kind: ReadingTaskKind): string | null {
  return localStorage.getItem(getReadingTaskStorageKey(kind))
}

function computeReadingStep(progress: number, stepCount: number) {
  if (stepCount <= 0 || progress <= 0) return 0
  const ratio = 100 / stepCount
  return Math.min(stepCount, Math.max(1, Math.ceil(progress / ratio)))
}

function useReadingTaskTracker(kind: ReadingTaskKind, stepCount = 0) {
  const [taskId, setTaskId] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待上传...')
  const [logs, setLogs] = useState<string[]>([])
  const [preview, setPreview] = useState('')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [currentStep, setCurrentStep] = useState(0)
  const pollRef = useRef<number | null>(null)
  const peakProgressRef = useRef(0)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const resetTaskState = () => {
    stopPolling()
    persistReadingTaskId(kind, null)
    setTaskId(null)
    setIsRunning(false)
    setProgress(0)
    peakProgressRef.current = 0
    setStage('等待上传...')
    setLogs([])
    setPreview('')
    setDownloadUrl('')
    setCurrentStep(0)
  }

  const cancelTask = async () => {
    if (taskId) {
      try {
        await fetch(`/api/reading/task/${taskId}/cancel`, { method: 'POST' })
      } catch {
        // Ignore network failures and still clear local UI state.
      }
    }
    resetTaskState()
    setStage('已取消')
    setLogs((prev) => [...prev, '⚠ 用户取消了精读任务'])
  }

  const applyStatus = (statusData: any) => {
    const rawProgress = statusData.progress || 0
    const nextProgress = statusData.status === 'completed'
      ? 100
      : Math.max(rawProgress, peakProgressRef.current)
    peakProgressRef.current = nextProgress

    if (statusData.status === 'queued') {
      setProgress(0)
      setStage(statusData.stage || '排队中...')
      setIsRunning(true)
      if (Array.isArray(statusData.logs) && statusData.logs.length > 0) {
        setLogs(statusData.logs)
      }
      return
    }

    setProgress(nextProgress)
    setStage(statusData.stage || '处理中...')
    if (Array.isArray(statusData.logs) && statusData.logs.length > 0) {
      setLogs(statusData.logs)
    }
    if (statusData.result?.preview) {
      setPreview(statusData.result.preview)
    }
    if (statusData.result?.output_path) {
      setDownloadUrl(statusData.result.output_path)
    }
    if (stepCount > 0) {
      setCurrentStep(
        statusData.status === 'completed' ? stepCount : computeReadingStep(nextProgress, stepCount),
      )
    }

    if (statusData.status === 'completed') {
      stopPolling()
      persistReadingTaskId(kind, null)
      setIsRunning(false)
      setProgress(100)
      if (stepCount > 0) setCurrentStep(stepCount)
    } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
      stopPolling()
      persistReadingTaskId(kind, null)
      setIsRunning(false)
    } else {
      setIsRunning(true)
    }
  }

  const fetchStatus = async (runningTaskId: string) => {
    const statusRes = await fetch(`/api/reading/task/${runningTaskId}/status`)
    const statusData = await statusRes.json()
    applyStatus(statusData)
    return statusData
  }

  const startTrackingTask = async (nextTaskId: string) => {
    setTaskId(nextTaskId)
    persistReadingTaskId(kind, nextTaskId)
    setIsRunning(true)
    await fetchStatus(nextTaskId)
    stopPolling()
    pollRef.current = window.setInterval(() => {
      void fetchStatus(nextTaskId).catch((error) => {
        stopPolling()
        setIsRunning(false)
        setStage('错误')
        setLogs((prev) => [...prev, `❌ ${error.message || '读取任务状态失败'}`])
      })
    }, 1000)
  }

  useEffect(() => {
    const savedTaskId = restoreReadingTaskId(kind)
    if (savedTaskId) {
      void startTrackingTask(savedTaskId).catch(() => {
        persistReadingTaskId(kind, null)
      })
    }
    return stopPolling
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    taskId,
    isRunning,
    progress,
    stage,
    logs,
    preview,
    downloadUrl,
    currentStep,
    setLogs,
    setStage,
    setProgress,
    setPreview,
    setDownloadUrl,
    setCurrentStep,
    startTrackingTask,
    resetTaskState,
    cancelTask,
    setIsRunning,
  }
}

interface BatchTaskItem {
  task_id: string | null
  file_name: string
  status: string
  progress: number
  stage: string
  download_url: string
  error?: string
}

interface BatchState {
  batchId: string | null
  total: number
  completed: number
  failed: number
  running: number
  queued: number
  tasks: BatchTaskItem[]
  isBatchRunning: boolean
}

type ReadingBatchKind = 'long' | 'quant' | 'qual'

function getBatchTaskStorageKey(kind: ReadingBatchKind) {
  return `dra_batch_task_id_${kind}`
}

function persistBatchId(kind: ReadingBatchKind, batchId: string | null) {
  const storageKey = getBatchTaskStorageKey(kind)
  if (batchId) {
    localStorage.setItem(storageKey, batchId)
  } else {
    localStorage.removeItem(storageKey)
  }
}

function restoreBatchId(kind: ReadingBatchKind): string | null {
  return localStorage.getItem(getBatchTaskStorageKey(kind))
}

function useBatchReadingTracker(kind: ReadingBatchKind) {
  const [state, setState] = useState<BatchState>({
    batchId: null, total: 0, completed: 0, failed: 0, running: 0, queued: 0, tasks: [], isBatchRunning: false,
  })
  const pollRef = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const resetBatch = () => {
    stopPolling()
    persistBatchId(kind, null)
    setState({
      batchId: null, total: 0, completed: 0, failed: 0, running: 0, queued: 0, tasks: [], isBatchRunning: false,
    })
  }

  const startBatchTracking = (batchId: string) => {
    persistBatchId(kind, batchId)
    setState(prev => ({ ...prev, batchId, isBatchRunning: true }))
    const poll = async () => {
      try {
        const res = await fetch(`/api/reading/batch/${batchId}/status`)
        if (!res.ok) {
          resetBatch()
          return
        }
        const data = await res.json()
        if (!Array.isArray(data.tasks)) {
          resetBatch()
          return
        }
        const allDone = data.completed + data.failed >= data.total
        setState(prev => ({
          ...prev,
          total: data.total,
          completed: data.completed,
          failed: data.failed,
          running: data.running,
          queued: data.queued,
          tasks: data.tasks,
          isBatchRunning: !allDone,
        }))
        if (allDone) {
          stopPolling()
          persistBatchId(kind, null)
        }
      } catch {
        stopPolling()
        setState(prev => ({ ...prev, isBatchRunning: false }))
      }
    }
    void poll()
    stopPolling()
    pollRef.current = window.setInterval(() => void poll(), 2000)
  }

  useEffect(() => {
    const savedBatchId = restoreBatchId(kind)
    if (savedBatchId) {
      startBatchTracking(savedBatchId)
    }
    return () => stopPolling()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { ...state, startBatchTracking, resetBatch }
}

// Tab 0: 文献筛选
function FilterTab({ apiKey: _apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState('explorer')
  const [topic, setTopic] = useState('')
  const [minYear, setMinYear] = useState(2015)
  const [keywords, setKeywords] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待上传...')
  const [logs, setLogs] = useState<string[]>([])
  const [results, setResults] = useState<any[]>([])
  const [downloadUrl, setDownloadUrl] = useState('')
  const [importing, setImporting] = useState(false)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const handleStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) {
      alert('请先设置 DeepSeek API Key')
      return
    }
    if (!file) {
      alert('请先上传文献题录文件')
      return
    }
    if (!topic.trim()) {
      alert('请输入研究主题')
      return
    }

    setIsRunning(true)
    setProgress(0)
    setStage('上传文件中...')
    setLogs([])
    setResults([])

    try {
      // Step 1: Upload file
      const formData = new FormData()
      formData.append('file', file)

      let uploadRes
      try {
        uploadRes = await fetch('/api/upload/', {
          method: 'POST',
          body: formData,
        })
      } catch (e: any) {
        throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
      }
      
      // Handle non-JSON responses (e.g., Cloudflare timeout HTML)
      const contentType = uploadRes.headers.get('content-type') || ''
      if (!contentType.includes('application/json')) {
        const text = await uploadRes.text()
        if (text.includes('Bad gateway') || text.includes('timeout') || text.includes('504')) {
          throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
        }
        throw new Error('服务器返回异常响应，请刷新后重试。')
      }
      
      const uploadData = await uploadRes.json()

      if (!uploadData.success) {
        throw new Error(uploadData.message || '上传失败')
      }

      setProgress(10)
      setStage('解析文献题录...')
      addLog('✓ 文件上传成功')

      // Step 2: Start filter task
      const startRes = await fetch('/api/filter/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: uploadData.file_id,
          mode,
          topic,
          min_year: minYear,
          keywords: keywords || undefined,
          ...(effectiveKey ? { api_key: effectiveKey } : {}),
        }),
      })
      const startData = await startRes.json()
      const taskId = startData.task_id

      addLog(`✓ 任务已创建: ${taskId}`)

      // Step 3: Poll for progress
      let pollInProgress = false
      const pollInterval = setInterval(async () => {
        if (pollInProgress) return
        pollInProgress = true
        try {
          const controller = new AbortController()
          const timer = setTimeout(() => controller.abort(), 15000)
          const statusRes = await fetch(`/api/filter/task/${taskId}/status`, { signal: controller.signal })
          clearTimeout(timer)
          const statusData = await statusRes.json()

          setProgress(statusData.progress || 0)
          setStage(statusData.stage || '处理中...')

          if (statusData.logs && statusData.logs.length > 0) {
            setLogs(statusData.logs)
          }

          if (statusData.status === 'completed') {
            clearInterval(pollInterval)
            setIsRunning(false)
            setProgress(100)
            setStage('完成')
            addLog('✅ 全部完成！')

            if (statusData.result?.preview) {
              setResults(statusData.result.preview)
            }
            if (statusData.result?.output_path) {
              setDownloadUrl(statusData.result.output_path)
            }
          } else if (statusData.status === 'failed') {
            clearInterval(pollInterval)
            setIsRunning(false)
            setStage('错误')
            addLog(`❌ ${statusData.error || '任务失败'}`)
          } else if (statusData.status === 'cancelled') {
            clearInterval(pollInterval)
            setIsRunning(false)
            setStage('已取消')
            addLog('⚠ 用户取消了筛选')
          }
        } catch {
          // skip this poll, will retry next interval
        } finally {
          pollInProgress = false
        }
      }, 2000)

    } catch (error: any) {
      setIsRunning(false)
      setStage('错误')
      addLog(`❌ ${error.message}`)
    }
  }

  const handleCancel = () => {
    // Best effort cancel
    setIsRunning(false)
    setStage('已取消')
    addLog('⚠ 用户取消了筛选')
  }

  async function handleDirectImport() {
    if (!file) return
    setImporting(true)
    setLogs([])
    setResults([])
    try {
      const fd = new FormData()
      fd.append('file', file)
      const uploadRes = await fetch('/api/upload/', { method: 'POST', body: fd })
      if (!uploadRes.ok) throw new Error('Upload failed')
      const uploadData = await uploadRes.json()
      if (!uploadData.success) throw new Error(uploadData.message || 'Upload failed')
      const res = await fetch('/api/filter/direct-import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Import failed')
      }
      const data = await res.json()
      setLogs([`✅ 成功导入 ${data.count} 条题录到文献库`])
    } catch (e: any) {
      setLogs([`❌ 导入失败: ${e.message}`])
    } finally {
      setImporting(false)
    }
  }

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, msg])
  }

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] 2xl:gap-6">
      {/* Left Sidebar */}
      <div className="space-y-4">
        {/* Upload */}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span>□</span> 上传文献题录
          </h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".txt" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 .txt 文件</span>
            {file && (
              <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>
            )}
          </label>
          <p className="mt-2 text-xs text-gray-400">Web of Science 或 CNKI 导出文件</p>
        </div>

        {/* Settings */}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span>★</span> 筛选设置
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">筛选模式</label>
              <div className="space-y-1.5">
                {[
                  { value: 'explorer', label: '探索者模式', desc: '找入门/奠基文献' },
                  { value: 'reviewer', label: '评审者模式', desc: '找综述价值大的' },
                  { value: 'empiricist', label: '实证主义者模式', desc: '找因果识别严谨的' },
                ].map((m) => (
                  <label key={m.value} className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name="mode"
                      value={m.value}
                      checked={mode === m.value}
                      onChange={(e) => setMode(e.target.value)}
                      className="text-emerald-600"
                    />
                    <div>
                      <div className="text-sm font-medium text-gray-700">{m.label}</div>
                      <div className="text-xs text-gray-400">{m.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">研究主题 *</label>
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="如：数字普惠金融"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">最小年份</label>
              <input
                type="number"
                value={minYear}
                onChange={(e) => setMinYear(parseInt(e.target.value) || 0)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <p className="mt-1 text-xs text-gray-400">0 = 不限制</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">关键词过滤</label>
              <input
                type="text"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="逗号分隔（可选）"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={handleStart}
            disabled={isRunning}
            className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isRunning ? '处理中...' : '开始筛选'}
          </button>
          <button
            onClick={handleCancel}
            disabled={!isRunning}
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            停止
          </button>
          <button
            onClick={handleDirectImport}
            disabled={!file || importing || isRunning}
            className="flex-1 rounded-lg bg-gradient-to-r from-green-600 to-green-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-green-700 hover:to-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {importing ? '导入中...' : '直接导入（跳过AI）'}
          </button>
        </div>
      </div>

      {/* Right Content */}
      <div className="space-y-4 min-w-0">
        {/* Progress */}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span>■</span> 处理进度
          </h3>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm text-gray-600">{stage}</span>
            <span className="text-sm font-medium text-emerald-600">{progress}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Logs */}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span>■</span> 运行日志
          </h3>
          <div className="rounded-lg bg-gray-900 p-3 h-48 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? (
              <span className="text-gray-500">等待开始...</span>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="text-gray-300 py-0.5">{log}</div>
              ))
            )}
          </div>
        </div>

        {/* Results */}
        {results.length > 0 && (
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <span>★</span> 筛选结果
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 font-medium text-gray-600">标题</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">作者</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">期刊</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">年份</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">评分</th>
                    <th className="text-left py-2 px-3 font-medium text-gray-600">理由</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, i) => (
                    <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 px-3 text-gray-800 max-w-xs truncate">{row.Title || '-'}</td>
                      <td className="py-2 px-3 text-gray-600 max-w-[150px] truncate">{row.Authors || '-'}</td>
                      <td className="py-2 px-3 text-gray-600">{row.Journal || '-'}</td>
                      <td className="py-2 px-3 text-gray-600">{row.Year || '-'}</td>
                      <td className="py-2 px-3">
                        <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          {row.score || '-'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-gray-600 max-w-[200px] truncate">{row.reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-gray-400">共 {results.length} 篇，按评分降序排列</p>
            {downloadUrl && (
              <button
                type="button"
                onClick={() =>
                  handleProtectedDownload(
                    downloadUrl,
                    downloadUrl.split('/').pop() || 'filter-report.xlsx',
                  ).catch((error) => alert(error.message))
                }
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100 transition-colors"
              >
                <span>↓</span> 下载筛选报告 (Excel)
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Tab 1: 长文本精读
function LongTab({ apiKey: _apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [dims, setDims] = useState<string[]>(["研究问题", "理论框架", "识别策略"])
  const [customQ, setCustomQ] = useState('')
  const [extraction, _setExtraction] = useState('full')
  const [dimensionSetId, setDimensionSetId] = useState<number | null>(null)
  const [dimensionItems, setDimensionItems] = useState<any[]>([])
  const [dimSets, setDimSets] = useState<any[]>([])
  const [editingDim, setEditingDim] = useState<any>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editPrompt, setEditPrompt] = useState('')
  const [editQuestion, setEditQuestion] = useState('')
  const [showAddDim, setShowAddDim] = useState(false)
  const [addName, setAddName] = useState('')
  const [addDesc, setAddDesc] = useState('')
  const [addPrompt, setAddPrompt] = useState('')
  const [addQuestion, setAddQuestion] = useState('')
  const [dimMessage, setDimMessage] = useState('')
  const [showSaveAsSet, setShowSaveAsSet] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [showBatchPreview, setShowBatchPreview] = useState(false)
  const [conflictInfo, setConflictInfo] = useState<any>(null)
  const pendingFileIdRef = useRef<string | null>(null)
  const [batchConflictInfo, setBatchConflictInfo] = useState<any>(null)
  const pendingBatchFileIdsRef = useRef<string[]>([])
  const pendingBatchKeyRef = useRef<string>('')
  const batchTracker = useBatchReadingTracker('long')
  const {
    cancelTask,
    isRunning,
    progress,
    stage,
    logs,
    preview,
    downloadUrl,
    setLogs,
    setStage,
    setProgress,
    setPreview,
    setDownloadUrl,
    setIsRunning,
    startTrackingTask,
  } = useReadingTaskTracker('long')

  const ALL_DIMS = [
    "研究问题", "理论框架", "识别策略", "数据来源", "变量度量",
    "识别假设", "统计结果", "机制分析", "稳健性检验", "外部有效性",
    "贡献与局限", "写作质量"
  ]

  const toggleDim = (dim: string) => {
    setDims(prev => prev.includes(dim) ? prev.filter(d => d !== dim) : [...prev, dim])
  }

  const reloadItems = async (setId: number) => {
    const res = await fetch(`/api/dimensions/sets/${setId}/items`)
    if (res.ok) setDimensionItems(await res.json())
  }

  const reloadSets = async (availableOnly = false) => {
    const res = await fetch(availableOnly ? '/api/dimensions/sets?available_only=true' : '/api/dimensions/sets')
    if (res.ok) return await res.json()
    return []
  }

  useEffect(() => {
    const fetchActiveSet = async () => {
      try {
        const sets = await reloadSets(true)
        setDimSets(sets)
        const active = sets.find((s: any) => s.is_default) || sets[0]
        if (!active) return
        setDimensionSetId(active.id)
        const itemsRes = await fetch(`/api/dimensions/sets/${active.id}/items`)
        if (!itemsRes.ok) return
        const items = await itemsRes.json()
        setDimensionItems(items)
        if (items.length > 0) {
          setDims(items.slice(0, Math.min(3, items.length)).map((i: any) => i.dim_name))
        }
      } catch {}
    }
    fetchActiveSet()
  }, [])

  const switchDimSet = async (setId: number) => {
    setDimensionSetId(setId)
    setEditingDim(null)
    await reloadItems(setId)
    const res = await fetch(`/api/dimensions/sets/${setId}/items`)
    if (res.ok) {
      const items = await res.json()
      setDims(items.slice(0, Math.min(3, items.length)).map((i: any) => i.dim_name))
    }
    await fetch('/api/dimensions/sets/' + setId + '/activate', { method: 'POST' })
    const sets = await reloadSets(true)
    setDimSets(sets)
  }

  const currentDimSet = dimSets.find((s: any) => s.id === dimensionSetId)

  const removeCurrentDimSetFromReading = async () => {
    if (!dimensionSetId) return
    if (currentDimSet?.is_system) {
      setDimMessage('❌ 系统默认集合不能移出长文本精读')
      setTimeout(() => setDimMessage(''), 2000)
      return
    }
    const label = currentDimSet?.name || '当前集合'
    if (!confirm(`确定将「${label}」移出长文本精读下拉框？集合仍会保留在模板市场，可随时重新导入。`)) return
    try {
      const res = await fetch(`/api/dimensions/sets/${dimensionSetId}/reading-availability`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_available_for_reading: false }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '移出失败')
      const sets = await reloadSets(true)
      setDimSets(sets)
      const next = sets.find((s: any) => s.is_default) || sets[0]
      if (next) {
        await switchDimSet(next.id)
      } else {
        setDimensionSetId(null)
        setDimensionItems([])
        setDims([])
      }
      setDimMessage(`✓ 「${label}」已移回模板市场`)
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const startEditDim = (item: any) => {
    setEditingDim(item)
    setEditName(item.dim_name)
    setEditDesc(item.description || '')
    setEditPrompt(item.prompt_content || '')
    setEditQuestion(item.default_question || '')
    setShowAddDim(false)
  }

  const saveEditDim = async () => {
    if (!editingDim || !dimensionSetId) return
    try {
      const res = await fetch(`/api/dimensions/sets/${dimensionSetId}/items/${editingDim.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dim_name: editName.trim(), description: editDesc.trim() || null, prompt_content: editPrompt, default_question: editQuestion }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '保存失败')
      const oldName = editingDim.dim_name
      if (editName.trim() !== oldName) {
        setDims(prev => prev.map(d => d === oldName ? editName.trim() : d))
      }
      setEditingDim(null)
      await reloadItems(dimensionSetId)
      setDimMessage('✓ 维度已更新')
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const deleteDim = async (item: any) => {
    if (!confirm('确定删除维度「' + item.dim_name + '」？') || !dimensionSetId) return
    try {
      const res = await fetch(`/api/dimensions/sets/${dimensionSetId}/items/${item.id}`, { method: 'DELETE' })
      if (!res.ok) {
        let detail = '删除失败'
        try { detail = (await res.json()).detail || detail } catch {}
        throw new Error(detail)
      }
      setDims(prev => prev.filter(d => d !== item.dim_name))
      if (editingDim?.id === item.id) setEditingDim(null)
      await reloadItems(dimensionSetId)
      setDimMessage('✓ 维度已删除')
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const addDimension = async () => {
    if (!addName.trim() || !dimensionSetId) return
    try {
      const res = await fetch(`/api/dimensions/sets/${dimensionSetId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dim_name: addName.trim(), description: addDesc.trim() || null, prompt_content: addPrompt, default_question: addQuestion }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '添加失败')
      setShowAddDim(false); setAddName(''); setAddDesc(''); setAddPrompt(''); setAddQuestion('')
      await reloadItems(dimensionSetId)
      const sets = await reloadSets()
      setDimSets(sets)
      setDimMessage('✓ 维度已添加')
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const saveAsNewSet = async () => {
    if (!saveAsName.trim() || !dimensionSetId) return
    try {
      const res = await fetch('/api/dimensions/sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: saveAsName.trim(), clone_from_set_id: dimensionSetId }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '创建失败')
      const created = await res.json()
      setShowSaveAsSet(false); setSaveAsName('')
      await switchDimSet(created.id)
      setDimMessage('✓ 已保存为新集合并切换')
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const createNewEmptySet = async () => {
    const name = prompt('请输入新集合名称：')
    if (!name?.trim()) return
    try {
      const body: any = { name: name.trim() }
      if (dimensionSetId) body.clone_from_set_id = dimensionSetId
      const res = await fetch('/api/dimensions/sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '创建失败')
      const created = await res.json()
      await switchDimSet(created.id)
      setDimMessage('✓ 新集合已创建')
      setTimeout(() => setDimMessage(''), 2000)
    } catch (e: unknown) {
      setDimMessage(`❌ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const getCurrentDimItems = () => (
    dimensionItems.length > 0
      ? dimensionItems
      : ALL_DIMS.map((name, i) => ({ id: -(i + 1), dim_name: name, is_builtin: true }))
  )

  const selectAllDims = () => {
    setDims(getCurrentDimItems().map((item: any) => item.dim_name))
  }

  const clearAllDims = () => {
    setDims([])
  }

  const getDimItemIndex = (target: any) => {
    return dimensionItems.findIndex((item: any) => item.id === target.id)
  }

  const getDimDragClass = (idx: number) => (
    `rounded transition-colors ${dragIdx !== null && dragIdx === idx ? 'opacity-40' : ''} ${overIdx !== null && overIdx === idx && dragIdx !== idx ? 'border-t-2 border-emerald-400' : ''}`
  )

  const onDragEnd = async () => {
    if (dragIdx === null || overIdx === null || dragIdx === overIdx || !dimensionSetId) {
      setDragIdx(null); setOverIdx(null)
      return
    }
    const reordered = [...dimensionItems]
    const [moved] = reordered.splice(dragIdx, 1)
    reordered.splice(overIdx, 0, moved)
    setDimensionItems(reordered)
    setDragIdx(null); setOverIdx(null)
    try {
      await fetch(`/api/dimensions/sets/${dimensionSetId}/items/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orders: reordered.map((it, i) => ({ id: it.id, sort_order: i })) }),
      })
    } catch {}
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0])
  }

  const handleStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (!file) { alert('请先上传文件'); return }
    if (dims.length === 0 && !customQ.trim()) { alert('请至少选择一个分析维度或输入自定义问题'); return }

    setIsRunning(true); setProgress(0); setStage('上传文件中...'); setLogs([]); setPreview(''); setDownloadUrl('')

    try {
      const formData = new FormData()
      formData.append('file', file)
      let uploadRes
      try {
        uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
      } catch (e: any) {
        throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
      }
      const ct = uploadRes.headers.get('content-type') || ''
      if (!ct.includes('application/json')) {
        const text = await uploadRes.text()
        if (text.includes('Bad gateway') || text.includes('timeout') || text.includes('504')) {
          throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
        }
        throw new Error('服务器返回异常响应，请刷新后重试。')
      }
      const uploadData = await uploadRes.json()
      if (!uploadData.success) throw new Error(uploadData.message)

      setStage('解析 PDF...'); addLog('✓ 文件上传成功')
      pendingFileIdRef.current = uploadData.file_id

      const startRes = await fetch('/api/reading/long/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, analysis_dims: dims, dimension_set_id: dimensionSetId || undefined, custom_question: customQ || undefined, extraction_method: extraction, api_key: effectiveKey })
      })
      if (startRes.status === 409) {
        const checkRes = await fetch('/api/reading/check-conflict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_id: uploadData.file_id,
            mode: 'long',
            analysis_dims: dims,
          }),
        })
        const conflict = await checkRes.json()
        if (conflict.has_conflict) {
          setConflictInfo(conflict)
          setStage('等待选择...')
          setIsRunning(false)
          return
        }
      }
      if (!startRes.ok) {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || `启动失败 (${startRes.status})`
        throw new Error(errMsg)
      }
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
    }
  }

  const handleConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
    setConflictInfo(null)
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { setStage('未设置 API Key'); return }
    const selectedDims = dims.length > 0 ? dims : ALL_DIMS
    setIsRunning(true)
    setStage('启动中...')
    try {
      const startRes = await fetch('/api/reading/long/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: pendingFileIdRef.current,
          analysis_dims: selectedDims,
          dimension_set_id: dimensionSetId || undefined,
          custom_question: customQ || undefined,
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      if (startRes.ok) {
        const data = await startRes.json()
        startTrackingTask(data.task_id)
      } else {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || '未知错误'
        setStage(`启动失败: ${errMsg}`)
        setIsRunning(false)
      }
    } catch (e: any) {
      setStage(`错误: ${e.message}`)
      setIsRunning(false)
    }
  }

  const handleFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const allowed = ['.pdf', '.md', '.markdown']
    const filtered = Array.from(e.target.files).filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase()
      return allowed.includes(ext)
    })
    if (filtered.length === 0) { alert('文件夹中没有找到 PDF 或 Markdown 文件'); return }
    setBatchFiles(filtered)
    setShowBatchPreview(true)
  }

  const removeBatchFile = (idx: number) => {
    setBatchFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleBatchStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (batchFiles.length === 0) { alert('没有可处理的文件'); return }

    setIsRunning(true); setProgress(0); setStage('批量上传文件中...'); setLogs([]); setPreview(''); setDownloadUrl('')
    batchTracker.resetBatch()

    try {
      const fileIds: string[] = []
      const failedUploads: string[] = []
      for (let i = 0; i < batchFiles.length; i++) {
        const f = batchFiles[i]
        setStage(`上传文件 ${i + 1}/${batchFiles.length}: ${f.name}`)
        try {
          const formData = new FormData()
          formData.append('file', f)
          const uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
          const uploadData = await uploadRes.json()
          if (uploadData.success) {
            fileIds.push(uploadData.file_id)
          } else {
            failedUploads.push(f.name)
          }
        } catch {
          failedUploads.push(f.name)
        }
      }

      if (fileIds.length === 0) throw new Error('所有文件上传失败')
      if (failedUploads.length > 0) {
        addLog(`⚠ ${failedUploads.length} 个文件上传失败: ${failedUploads.join(', ')}`)
      }
      addLog(`✓ ${fileIds.length} 个文件上传成功`)

      setStage('检查冲突...')
      const checkRes = await fetch('/api/reading/batch/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds, mode: 'long', analysis_dims: dims }),
      })
      const checkData = await checkRes.json()
      if (checkData.conflict_count > 0) {
        setBatchConflictInfo(checkData)
        pendingBatchFileIdsRef.current = fileIds
        pendingBatchKeyRef.current = effectiveKey
        setStage('等待选择...')
        setIsRunning(false)
        return
      }

      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'long',
          analysis_dims: dims,
          dimension_set_id: dimensionSetId || undefined,
          custom_question: customQ || undefined,
          extraction_method: extraction,
          api_key: effectiveKey,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'skip' | 'incremental') => {
    setBatchConflictInfo(null)
    const fileIds = pendingBatchFileIdsRef.current
    const effectiveKey = pendingBatchKeyRef.current
    setIsRunning(true)
    setStage('启动批量精读...')
    try {
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'long',
          analysis_dims: dims,
          dimension_set_id: dimensionSetId || undefined,
          custom_question: customQ || undefined,
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      const skippedCount = startData.skipped_count || 0
      if (queuedCount === 0 && skippedCount > 0 && errorCount === 0) {
        addLog(`ℹ ${skippedCount} 个文件已有结果，已全部跳过`)
        setStage('批量精读已跳过')
        setShowBatchPreview(false)
        setIsRunning(false)
        return
      }
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if (skippedCount > 0) addLog(`ℹ ${skippedCount} 个文件已有结果已跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] 2xl:gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf,.md,.markdown" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF / Markdown</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 cursor-pointer hover:bg-blue-100 transition-colors">
              <input type="file" {...{ webkitdirectory: 'true' }} onChange={handleFolderChange} className="hidden" />
              上传文件夹
            </label>
            {batchFiles.length > 0 && (
              <span className="text-xs text-blue-600">{batchFiles.length} 个文件待处理</span>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            PDF 文件过大无法上传？可前往
            <a href="https://aistudio.baidu.com/paddleocr" target="_blank" rel="noopener noreferrer" className="text-emerald-600 hover:text-emerald-700 underline mx-0.5">百度 PaddleOCR</a>
            将 PDF 转换为 Markdown 后上传
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">★ 分析维度</h3>
            <div className="flex items-center gap-1.5">
              {dimensionSetId && (
                <button onClick={() => { setShowSaveAsSet(true); setSaveAsName('') }} className="rounded-lg bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-200 transition-colors" title="另存为新集合">另存为</button>
              )}
              <button onClick={createNewEmptySet} className="rounded-lg bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-200 transition-colors">+ 新集合</button>
            </div>
          </div>

          {dimSets.length > 0 && (
            <div className="mb-3">
              <div className="flex gap-2">
                <select
                  value={dimensionSetId ?? ''}
                  onChange={e => { if (e.target.value) switchDimSet(Number(e.target.value)) }}
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
                >
                  {dimSets.map((s: any) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.item_count} 维度){s.is_default ? ' ●' : ''}</option>
                  ))}
                </select>
                <button
                  onClick={removeCurrentDimSetFromReading}
                  disabled={!dimensionSetId || currentDimSet?.is_system}
                  className="shrink-0 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                  title="只从长文本精读下拉框移出，不删除集合"
                >
                  移出
                </button>
              </div>
            </div>
          )}

          {showSaveAsSet && (
            <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50/50 p-2">
              <input value={saveAsName} onChange={e => setSaveAsName(e.target.value)} placeholder="新集合名称" className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none" onKeyDown={e => { if (e.key === 'Enter') saveAsNewSet() }} />
              <button onClick={saveAsNewSet} className="rounded bg-emerald-600 px-2 py-1 text-xs text-white hover:bg-emerald-700">保存</button>
              <button onClick={() => setShowSaveAsSet(false)} className="rounded bg-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-300">取消</button>
            </div>
          )}

          {dimMessage && <div className={`mb-2 text-xs ${dimMessage.startsWith('✓') ? 'text-emerald-600' : 'text-red-600'}`}>{dimMessage}</div>}

          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
              已选 {dims.length} / {getCurrentDimItems().length}
            </span>
            <button onClick={selectAllDims} className="rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">全选</button>
            <button onClick={clearAllDims} className="rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">全不选</button>
          </div>

          {(() => {
            const allItems = getCurrentDimItems()
            const hasGroups = dimensionItems.length > 0 && dimensionItems.some((it: any) => it.group_name)
            if (!hasGroups) {
              return (
                <div className="space-y-0.5">
                  {allItems.map((item: any, idx: number) => (
                    <div
                      key={item.id || item.dim_name}
                      draggable={dimensionItems.length > 0}
                      onDragStart={() => setDragIdx(idx)}
                      onDragOver={e => { e.preventDefault(); setOverIdx(idx) }}
                      onDragLeave={() => setOverIdx(null)}
                      onDrop={onDragEnd}
                      className={getDimDragClass(idx)}
                    >
                      <div className="flex items-center gap-1.5 p-1.5 hover:bg-gray-50 text-sm group cursor-grab active:cursor-grabbing">
                        <span className="text-gray-300 text-[10px] select-none">⠿</span>
                        <input type="checkbox" checked={dims.includes(item.dim_name)} onChange={() => toggleDim(item.dim_name)} className="rounded text-emerald-600 shrink-0" />
                        <span className="text-gray-700 flex-1 truncate">{item.dim_name}</span>
                        {dimensionItems.length > 0 && (
                          <div className="flex items-center gap-0.5 shrink-0">
                            <button onClick={() => startEditDim(item)} className="rounded px-1 py-0.5 text-[10px] text-blue-500 hover:bg-blue-50" title="编辑">✏</button>
                            <button onClick={() => deleteDim(item)} className="rounded px-1 py-0.5 text-[10px] text-red-400 hover:bg-red-50" title="删除">✕</button>
                          </div>
                        )}
                      </div>
                      {editingDim?.id === item.id && (
                        <div className="ml-6 mt-1 mb-2 rounded-lg border border-amber-200 bg-amber-50/30 p-3 space-y-2">
                          <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="维度名称" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                          <input value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="描述（可选）" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                          <input value={editQuestion} onChange={e => setEditQuestion(e.target.value)} placeholder="默认问题" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                          <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} placeholder="提示词内容" rows={4} className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-mono focus:border-emerald-500 focus:outline-none" />
                          <div className="flex gap-2">
                            <button onClick={saveEditDim} className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700">保存</button>
                            <button onClick={() => setEditingDim(null)} className="rounded bg-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-300">取消</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )
            }
            const groupMap: Record<string, any[]> = {}
            const groupOrder: string[] = []
            dimensionItems.forEach((item: any) => {
              const g = item.group_name || '其他'
              if (!groupMap[g]) { groupMap[g] = []; groupOrder.push(g) }
              groupMap[g].push(item)
            })
            return (
              <div className="space-y-3">
                {groupOrder.map(group => (
                  <div key={group} className="rounded-lg border border-gray-200 p-2">
                    <div className="mb-1.5 text-xs font-medium text-gray-500">{group}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-0.5">
                      {groupMap[group].map((item: any) => {
                        const itemIdx = getDimItemIndex(item)
                        return (
                        <div
                          key={item.id || item.dim_name}
                          draggable={itemIdx >= 0}
                          onDragStart={() => setDragIdx(itemIdx)}
                          onDragOver={e => { e.preventDefault(); setOverIdx(itemIdx) }}
                          onDragLeave={() => setOverIdx(null)}
                          onDrop={onDragEnd}
                          className={itemIdx >= 0 ? getDimDragClass(itemIdx) : 'rounded'}
                        >
                          <div className="flex items-center gap-1.5 p-1.5 hover:bg-gray-50 rounded text-sm group cursor-grab active:cursor-grabbing">
                            <span className="text-gray-300 text-[10px] select-none">⠿</span>
                            <input type="checkbox" checked={dims.includes(item.dim_name)} onChange={() => toggleDim(item.dim_name)} className="rounded text-emerald-600 shrink-0" />
                            <span className="text-gray-700 flex-1 truncate">{item.dim_name}</span>
                            <div className="flex items-center gap-0.5 shrink-0">
                              <button onClick={() => startEditDim(item)} className="rounded px-1 py-0.5 text-[10px] text-blue-500 hover:bg-blue-50" title="编辑">✏</button>
                              <button onClick={() => deleteDim(item)} className="rounded px-1 py-0.5 text-[10px] text-red-400 hover:bg-red-50" title="删除">✕</button>
                            </div>
                          </div>
                          {editingDim?.id === item.id && (
                            <div className="ml-4 mt-1 mb-2 rounded-lg border border-amber-200 bg-amber-50/30 p-3 space-y-2">
                              <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="维度名称" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                              <input value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="描述（可选）" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                              <input value={editQuestion} onChange={e => setEditQuestion(e.target.value)} placeholder="默认问题" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
                              <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} placeholder="提示词内容" rows={4} className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-mono focus:border-emerald-500 focus:outline-none" />
                              <div className="flex gap-2">
                                <button onClick={saveEditDim} className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700">保存</button>
                                <button onClick={() => setEditingDim(null)} className="rounded bg-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-300">取消</button>
                              </div>
                            </div>
                          )}
                        </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )
          })()}

          {dimensionItems.length > 0 && (
            <button
              onClick={() => { setShowAddDim(!showAddDim); setAddName(''); setAddDesc(''); setAddPrompt(''); setAddQuestion('') }}
              className="mt-2 w-full rounded-lg border border-dashed border-gray-300 py-1.5 text-xs text-gray-500 hover:border-emerald-400 hover:text-emerald-600 transition-colors"
            >+ 添加维度</button>
          )}

          {showAddDim && (
            <div className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 space-y-2">
              <input value={addName} onChange={e => setAddName(e.target.value)} placeholder="维度名称 *" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
              <input value={addDesc} onChange={e => setAddDesc(e.target.value)} placeholder="描述（可选）" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
              <input value={addQuestion} onChange={e => setAddQuestion(e.target.value)} placeholder="默认问题" className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none" />
              <textarea value={addPrompt} onChange={e => setAddPrompt(e.target.value)} placeholder="提示词内容" rows={3} className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-mono focus:border-emerald-500 focus:outline-none" />
              <div className="flex gap-2">
                <button onClick={addDimension} className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700">添加</button>
                <button onClick={() => setShowAddDim(false)} className="rounded bg-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-300">取消</button>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">✉ 自定义问题</h3>
          <textarea
            value={customQ}
            onChange={(e) => setCustomQ(e.target.value)}
            placeholder="可选：输入你特别想了解的方面"
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>

        <div className="flex gap-2">
          <button onClick={handleStart} disabled={isRunning} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : '开始精读'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>

      <div className="space-y-4 min-w-0">
        {batchTracker.batchId && (
          <div className="rounded-xl border border-blue-200 bg-white p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-blue-700">批量精读进度</h3>
              <span className="text-xs text-gray-500">
                {batchTracker.completed + batchTracker.failed}/{batchTracker.total} 完成
                {batchTracker.failed > 0 && <span className="text-red-500 ml-1">({batchTracker.failed} 失败)</span>}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${batchTracker.total > 0 ? ((batchTracker.completed + batchTracker.failed) / batchTracker.total * 100) : 0}%` }}
              />
            </div>
            {batchTracker.isBatchRunning && (
              <p className="text-xs text-blue-600 animate-pulse mb-3">
                正在处理第 {batchTracker.completed + batchTracker.running + 1}/{batchTracker.total} 篇...
              </p>
            )}
            {!batchTracker.isBatchRunning && batchTracker.total > 0 && (
              <p className="text-xs text-emerald-600 mb-3">
                批量精读完成！成功 {batchTracker.completed} 篇，失败 {batchTracker.failed} 篇。
              </p>
            )}
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {batchTracker.tasks.map((t, i) => (
                <div key={t.task_id || i} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-xs bg-gray-50">
                  <span className="truncate text-gray-700 max-w-[200px]">{t.file_name}</span>
                  <span className={
                    t.status === 'completed' ? 'text-emerald-600 font-medium' :
                    t.status === 'failed' || t.status === 'canceled' ? 'text-red-500' :
                    t.status === 'running' ? 'text-blue-600 animate-pulse' :
                    'text-gray-400'
                  }>
                    {t.status === 'completed' ? '✓ 完成' :
                     t.status === 'failed' ? '✗ 失败' :
                     t.status === 'running' ? `⟳ ${t.progress}%` :
                     t.status === 'canceled' ? '⚠ 取消' :
                     '○ 排队'}
                  </span>
                  {t.status === 'completed' && t.download_url && (
                    <button
                      type="button"
                      onClick={() => handleProtectedDownload(t.download_url, t.download_url.split('/').pop() || 'reading-report.md').catch(err => alert(err.message || '下载失败'))}
                      className="text-blue-500 hover:underline ml-2"
                    >
                      下载
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">■ 处理进度</h3>
          {stage && stage.startsWith('排队中') && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-blue-600 font-medium">⏳ 排队中</span>
              </div>
              <div className="text-sm text-blue-600">{stage}</div>
              <div className="mt-2 h-2 bg-blue-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full animate-pulse" style={{ width: '30%' }} />
              </div>
            </div>
          )}
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm text-gray-600">{stage}</span>
            <span className="text-sm font-medium text-emerald-600">{progress}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">■ 运行日志</h3>
          <div className="rounded-lg bg-gray-900 p-3 h-48 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? <span className="text-gray-500">等待开始...</span> : logs.map((log, i) => <div key={i} className="text-gray-300 py-0.5">{log}</div>)}
          </div>
        </div>

        {preview && (
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">★ 分析结果</h3>
            <div className="prose prose-sm max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 p-4 rounded-lg">{preview}</pre>
            </div>
            {downloadUrl && (
              <button
                type="button"
                onClick={() =>
                  handleProtectedDownload(
                    downloadUrl,
                    downloadUrl.split('/').pop() || 'reading-report.md',
                  ).catch((error) => alert(error.message))
                }
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100 transition-colors"
              >
                ↓ 下载完整报告
              </button>
            )}
          </div>
        )}

        {showBatchPreview && batchFiles.length > 0 && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
              <h3 className="text-base font-semibold text-gray-800 mb-3">批量精读文件列表（{batchFiles.length} 篇）</h3>
              <div className="flex-1 overflow-y-auto space-y-1 mb-4">
                {batchFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg px-3 py-1.5 hover:bg-gray-50 text-sm">
                    <span className="truncate text-gray-700">{f.name}</span>
                    <button onClick={() => removeBatchFile(i)} className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0">移除</button>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => { setShowBatchPreview(false); setBatchFiles([]) }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                <button onClick={handleBatchStart} disabled={isRunning} className="rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 px-4 py-2 text-sm font-medium text-white hover:from-blue-700 hover:to-blue-600 disabled:opacity-50">
                  {isRunning ? '上传中...' : `开始批量精读 (${batchFiles.length} 篇)`}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      {conflictInfo && (
        <ConflictDialog
          conflict={conflictInfo}
          mode="long"
          onResolve={handleConflictResolve}
          onCancel={() => { setConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
        />
      )}
      {batchConflictInfo && (
        <BatchConflictDialog
          conflicts={batchConflictInfo.conflicts.filter((c: any) => c.has_conflict)}
          noConflictCount={batchConflictInfo.total - batchConflictInfo.conflict_count}
          mode="long"
          onResolve={handleBatchConflictResolve}
          onCancel={() => { setBatchConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
        />
      )}
    </div>
  )
}

// Tab 2: 七步精读
function QuantTab({ apiKey: _apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [extraction, setExtraction] = useState('full')
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [showBatchPreview, setShowBatchPreview] = useState(false)
  const [conflictInfo, setConflictInfo] = useState<any>(null)
  const pendingFileIdRef = useRef<string | null>(null)
  const [batchConflictInfo, setBatchConflictInfo] = useState<any>(null)
  const pendingBatchFileIdsRef = useRef<string[]>([])
  const pendingBatchKeyRef = useRef<string>('')
  const batchTracker = useBatchReadingTracker('quant')
  const {
    cancelTask,
    isRunning,
    progress,
    stage,
    logs,
    currentStep,
    setLogs,
    setStage,
    setProgress,
    setCurrentStep,
    setIsRunning,
    startTrackingTask,
  } = useReadingTaskTracker('quant', 7)

  const STEPS = [
    { num: 1, name: "研究概览", icon: "①" },
    { num: 2, name: "理论机制", icon: "②" },
    { num: 3, name: "数据说明", icon: "③" },
    { num: 4, name: "变量与度量", icon: "④" },
    { num: 5, name: "识别策略", icon: "⑤" },
    { num: 6, name: "结果呈现", icon: "⑥" },
    { num: 7, name: "批判性评估", icon: "⑦" },
  ]

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0])
  }

  const handleStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (!file) { alert('请先上传文件'); return }
    setIsRunning(true); setProgress(0); setStage('上传文件中...'); setLogs([]); setCurrentStep(0)
    try {
      const formData = new FormData()
      formData.append('file', file)
      let uploadRes
      try {
        uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
      } catch (e: any) {
        throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
      }
      const ct = uploadRes.headers.get('content-type') || ''
      if (!ct.includes('application/json')) {
        const text = await uploadRes.text()
        if (text.includes('Bad gateway') || text.includes('timeout') || text.includes('504')) {
          throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
        }
        throw new Error('服务器返回异常响应，请刷新后重试。')
      }
      const uploadData = await uploadRes.json()
      if (!uploadData.success) throw new Error(uploadData.message)
      pendingFileIdRef.current = uploadData.file_id
      setStage('解析 PDF...'); addLog('✓ 文件上传成功')

      const startRes = await fetch('/api/reading/quant/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, extraction_method: extraction, api_key: effectiveKey })
      })
      if (startRes.status === 409) {
        const checkRes = await fetch('/api/reading/check-conflict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_id: uploadData.file_id,
            mode: 'quant',
          }),
        })
        const conflict = await checkRes.json()
        if (conflict.has_conflict) {
          setConflictInfo(conflict)
          setStage('等待选择...')
          setIsRunning(false)
          return
        }
      }
      if (!startRes.ok) {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || `启动失败 (${startRes.status})`
        throw new Error(errMsg)
      }
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) { setStage('错误'); addLog(`❌ ${error.message}`) }
  }

  const handleConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
    setConflictInfo(null)
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { setStage('未设置 API Key'); return }
    setIsRunning(true)
    setStage('启动中...')
    try {
      const startRes = await fetch('/api/reading/quant/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: pendingFileIdRef.current,
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      if (startRes.ok) {
        const data = await startRes.json()
        startTrackingTask(data.task_id)
      } else {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || '未知错误'
        setStage(`启动失败: ${errMsg}`)
        setIsRunning(false)
      }
    } catch (e: any) {
      setStage(`错误: ${e.message}`)
      setIsRunning(false)
    }
  }

  const handleFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const allowed = ['.pdf', '.md', '.markdown']
    const filtered = Array.from(e.target.files).filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase()
      return allowed.includes(ext)
    })
    if (filtered.length === 0) { alert('文件夹中没有找到 PDF 或 Markdown 文件'); return }
    setBatchFiles(filtered)
    setShowBatchPreview(true)
  }

  const removeBatchFile = (idx: number) => {
    setBatchFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleBatchStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (batchFiles.length === 0) { alert('没有可处理的文件'); return }

    setIsRunning(true); setProgress(0); setStage('批量上传文件中...'); setLogs([]); setCurrentStep(0)
    batchTracker.resetBatch()

    try {
      const fileIds: string[] = []
      const failedUploads: string[] = []
      for (let i = 0; i < batchFiles.length; i++) {
        const f = batchFiles[i]
        setStage(`上传文件 ${i + 1}/${batchFiles.length}: ${f.name}`)
        try {
          const formData = new FormData()
          formData.append('file', f)
          const uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
          const uploadData = await uploadRes.json()
          if (uploadData.success) fileIds.push(uploadData.file_id)
          else failedUploads.push(f.name)
        } catch { failedUploads.push(f.name) }
      }
      if (fileIds.length === 0) throw new Error('所有文件上传失败')
      if (failedUploads.length > 0) addLog(`⚠ ${failedUploads.length} 个文件上传失败`)
      addLog(`✓ ${fileIds.length} 个文件上传成功`)

      setStage('检查冲突...')
      const checkRes = await fetch('/api/reading/batch/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds, mode: 'quant' }),
      })
      const checkData = await checkRes.json()
      if (checkData.conflict_count > 0) {
        setBatchConflictInfo(checkData)
        pendingBatchFileIdsRef.current = fileIds
        pendingBatchKeyRef.current = effectiveKey
        setStage('等待选择...')
        setIsRunning(false)
        return
      }

      setStage('启动批量精读...')
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'quant',
          extraction_method: extraction,
          api_key: effectiveKey,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'skip' | 'incremental') => {
    setBatchConflictInfo(null)
    const fileIds = pendingBatchFileIdsRef.current
    const effectiveKey = pendingBatchKeyRef.current
    setIsRunning(true)
    setStage('启动批量精读...')
    try {
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'quant',
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      const skippedCount = startData.skipped_count || 0
      if (queuedCount === 0 && skippedCount > 0 && errorCount === 0) {
        addLog(`ℹ ${skippedCount} 个文件已有结果，已全部跳过`)
        setStage('批量精读已跳过')
        setShowBatchPreview(false)
        setIsRunning(false)
        return
      }
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if (skippedCount > 0) addLog(`ℹ ${skippedCount} 个文件已有结果已跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] 2xl:gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf,.md,.markdown" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF / Markdown</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 cursor-pointer hover:bg-blue-100 transition-colors">
              <input type="file" {...{ webkitdirectory: 'true' }} onChange={handleFolderChange} className="hidden" />
              上传文件夹
            </label>
            {batchFiles.length > 0 && (
              <span className="text-xs text-blue-600">{batchFiles.length} 个文件待处理</span>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            PDF 文件过大无法上传？可前往
            <a href="https://aistudio.baidu.com/paddleocr" target="_blank" rel="noopener noreferrer" className="text-emerald-600 hover:text-emerald-700 underline mx-0.5">百度 PaddleOCR</a>
            将 PDF 转换为 Markdown 后上传
          </p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">★ 提取方式</h3>
          <div className="space-y-2">
            <label className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
              <input type="radio" checked={extraction === 'full'} onChange={() => setExtraction('full')} className="text-emerald-600" />
              <div><div className="text-sm font-medium text-gray-700">完整文本提取</div><div className="text-xs text-gray-400">最准确但较慢</div></div>
            </label>
            <label className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
              <input type="radio" checked={extraction === 'preview'} onChange={() => setExtraction('preview')} className="text-emerald-600" />
              <div><div className="text-sm font-medium text-gray-700">快速预览</div><div className="text-xs text-gray-400">仅前 10 页，速度快</div></div>
            </label>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleStart} disabled={isRunning} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : '开始精读'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>
      <div className="space-y-4 min-w-0">
        {batchTracker.batchId && (
          <div className="rounded-xl border border-blue-200 bg-white p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-blue-700">批量精读进度</h3>
              <span className="text-xs text-gray-500">
                {batchTracker.completed + batchTracker.failed}/{batchTracker.total} 完成
                {batchTracker.failed > 0 && <span className="text-red-500 ml-1">({batchTracker.failed} 失败)</span>}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${batchTracker.total > 0 ? ((batchTracker.completed + batchTracker.failed) / batchTracker.total * 100) : 0}%` }}
              />
            </div>
            {batchTracker.isBatchRunning && (
              <p className="text-xs text-blue-600 animate-pulse mb-3">
                正在处理第 {batchTracker.completed + batchTracker.running + 1}/{batchTracker.total} 篇...
              </p>
            )}
            {!batchTracker.isBatchRunning && batchTracker.total > 0 && (
              <p className="text-xs text-emerald-600 mb-3">
                批量精读完成！成功 {batchTracker.completed} 篇，失败 {batchTracker.failed} 篇。
              </p>
            )}
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {batchTracker.tasks.map((t, i) => (
                <div key={t.task_id || i} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-xs bg-gray-50">
                  <span className="truncate text-gray-700 max-w-[200px]">{t.file_name}</span>
                  <span className={
                    t.status === 'completed' ? 'text-emerald-600 font-medium' :
                    t.status === 'failed' || t.status === 'canceled' ? 'text-red-500' :
                    t.status === 'running' ? 'text-blue-600 animate-pulse' :
                    'text-gray-400'
                  }>
                    {t.status === 'completed' ? '✓ 完成' :
                     t.status === 'failed' ? '✗ 失败' :
                     t.status === 'running' ? `⟳ ${t.progress}%` :
                     t.status === 'canceled' ? '⚠ 取消' :
                     '○ 排队'}
                  </span>
                  {t.status === 'completed' && t.download_url && (
                    <button
                      type="button"
                      onClick={() => handleProtectedDownload(t.download_url, t.download_url.split('/').pop() || 'reading-report.md').catch(err => alert(err.message || '下载失败'))}
                      className="text-blue-500 hover:underline ml-2"
                    >
                      下载
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">△ 七步进度</h3>
          {stage && stage.startsWith('排队中') && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-blue-600 font-medium">⏳ 排队中</span>
              </div>
              <div className="text-sm text-blue-600">{stage}</div>
              <div className="mt-2 h-2 bg-blue-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full animate-pulse" style={{ width: '30%' }} />
              </div>
            </div>
          )}
          <div className="mb-4 overflow-x-auto">
            <div className="flex min-w-max items-center gap-1">
            {STEPS.map((s, i) => (
              <div key={s.num} className="flex items-center">
                <div className={`flex flex-col items-center ${i < currentStep ? 'text-emerald-600' : i === currentStep && isRunning ? 'text-emerald-500 animate-pulse' : 'text-gray-300'}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 ${i < currentStep ? 'bg-emerald-50 border-emerald-500' : i === currentStep && isRunning ? 'bg-emerald-50 border-emerald-400' : 'bg-gray-50 border-gray-200'}`}>
                    {i < currentStep ? '✓' : s.icon}
                  </div>
                  <span className="text-xs mt-1">{s.name}</span>
                </div>
                {i < STEPS.length - 1 && <div className={`w-6 h-0.5 mx-1 ${i < currentStep ? 'bg-emerald-400' : 'bg-gray-200'}`} />}
              </div>
            ))}
            </div>
          </div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm text-gray-600">{stage}</span>
            <span className="text-sm font-medium text-emerald-600">{progress}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">■ 运行日志</h3>
          <div className="rounded-lg bg-gray-900 p-3 h-64 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? <span className="text-gray-500">等待开始...</span> : logs.map((log, i) => <div key={i} className="text-gray-300 py-0.5">{log}</div>)}
          </div>
        </div>

        {showBatchPreview && batchFiles.length > 0 && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
              <h3 className="text-base font-semibold text-gray-800 mb-3">批量精读文件列表（{batchFiles.length} 篇）</h3>
              <div className="flex-1 overflow-y-auto space-y-1 mb-4">
                {batchFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg px-3 py-1.5 hover:bg-gray-50 text-sm">
                    <span className="truncate text-gray-700">{f.name}</span>
                    <button onClick={() => removeBatchFile(i)} className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0">移除</button>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => { setShowBatchPreview(false); setBatchFiles([]) }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                <button onClick={handleBatchStart} disabled={isRunning} className="rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 px-4 py-2 text-sm font-medium text-white hover:from-blue-700 hover:to-blue-600 disabled:opacity-50">
                  {isRunning ? '上传中...' : `开始批量精读 (${batchFiles.length} 篇)`}
                </button>
              </div>
            </div>
          </div>
        )}
        {conflictInfo && (
          <ConflictDialog
            conflict={conflictInfo}
            mode="quant"
            onResolve={handleConflictResolve}
            onCancel={() => { setConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
          />
        )}
        {batchConflictInfo && (
          <BatchConflictDialog
            conflicts={batchConflictInfo.conflicts.filter((c: any) => c.has_conflict)}
            noConflictCount={batchConflictInfo.total - batchConflictInfo.conflict_count}
            mode="quant"
            onResolve={handleBatchConflictResolve}
            onCancel={() => { setBatchConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
          />
        )}
      </div>
    </div>
  )
}

// Tab 3: 四步精读
function QualTab({ apiKey: _apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [extraction, setExtraction] = useState('full')
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [showBatchPreview, setShowBatchPreview] = useState(false)
  const [conflictInfo, setConflictInfo] = useState<any>(null)
  const pendingFileIdRef = useRef<string | null>(null)
  const [batchConflictInfo, setBatchConflictInfo] = useState<any>(null)
  const pendingBatchFileIdsRef = useRef<string[]>([])
  const pendingBatchKeyRef = useRef<string>('')
  const batchTracker = useBatchReadingTracker('qual')
  const {
    cancelTask,
    isRunning,
    progress,
    stage,
    logs,
    currentStep,
    setLogs,
    setStage,
    setProgress,
    setCurrentStep,
    setIsRunning,
    startTrackingTask,
  } = useReadingTaskTracker('qual', 4)

  const STEPS = [
    { num: 1, name: "背景与语境", icon: "①" },
    { num: 2, name: "理论框架", icon: "②" },
    { num: 3, name: "论证逻辑", icon: "③" },
    { num: 4, name: "价值与启示", icon: "④" },
  ]

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0])
  }

  const handleStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (!file) { alert('请先上传文件'); return }
    setIsRunning(true); setProgress(0); setStage('上传文件中...'); setLogs([]); setCurrentStep(0)
    try {
      const formData = new FormData()
      formData.append('file', file)
      let uploadRes
      try {
        uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
      } catch (e: any) {
        throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
      }
      const ct = uploadRes.headers.get('content-type') || ''
      if (!ct.includes('application/json')) {
        const text = await uploadRes.text()
        if (text.includes('Bad gateway') || text.includes('timeout') || text.includes('504')) {
          throw new Error('上传超时。文件可能过大（建议 <5MB），请压缩后重试。')
        }
        throw new Error('服务器返回异常响应，请刷新后重试。')
      }
      const uploadData = await uploadRes.json()
      if (!uploadData.success) throw new Error(uploadData.message)
      pendingFileIdRef.current = uploadData.file_id
      setStage('解析 PDF...'); addLog('✓ 文件上传成功')

      const startRes = await fetch('/api/reading/qual/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, extraction_method: extraction, api_key: effectiveKey })
      })
      if (startRes.status === 409) {
        const checkRes = await fetch('/api/reading/check-conflict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_id: uploadData.file_id,
            mode: 'qual',
          }),
        })
        const conflict = await checkRes.json()
        if (conflict.has_conflict) {
          setConflictInfo(conflict)
          setStage('等待选择...')
          setIsRunning(false)
          return
        }
      }
      if (!startRes.ok) {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || `启动失败 (${startRes.status})`
        throw new Error(errMsg)
      }
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) { setStage('错误'); addLog(`❌ ${error.message}`) }
  }

  const handleConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
    setConflictInfo(null)
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { setStage('未设置 API Key'); return }
    setIsRunning(true)
    setStage('启动中...')
    try {
      const startRes = await fetch('/api/reading/qual/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: pendingFileIdRef.current,
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      if (startRes.ok) {
        const data = await startRes.json()
        startTrackingTask(data.task_id)
      } else {
        const err = await startRes.json()
        const errMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || '未知错误'
        setStage(`启动失败: ${errMsg}`)
        setIsRunning(false)
      }
    } catch (e: any) {
      setStage(`错误: ${e.message}`)
      setIsRunning(false)
    }
  }

  const handleFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const allowed = ['.pdf', '.md', '.markdown']
    const filtered = Array.from(e.target.files).filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase()
      return allowed.includes(ext)
    })
    if (filtered.length === 0) { alert('文件夹中没有找到 PDF 或 Markdown 文件'); return }
    setBatchFiles(filtered)
    setShowBatchPreview(true)
  }

  const removeBatchFile = (idx: number) => {
    setBatchFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleBatchStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (batchFiles.length === 0) { alert('没有可处理的文件'); return }

    setIsRunning(true); setProgress(0); setStage('批量上传文件中...'); setLogs([]); setCurrentStep(0)
    batchTracker.resetBatch()

    try {
      const fileIds: string[] = []
      const failedUploads: string[] = []
      for (let i = 0; i < batchFiles.length; i++) {
        const f = batchFiles[i]
        setStage(`上传文件 ${i + 1}/${batchFiles.length}: ${f.name}`)
        try {
          const formData = new FormData()
          formData.append('file', f)
          const uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
          const uploadData = await uploadRes.json()
          if (uploadData.success) fileIds.push(uploadData.file_id)
          else failedUploads.push(f.name)
        } catch { failedUploads.push(f.name) }
      }
      if (fileIds.length === 0) throw new Error('所有文件上传失败')
      if (failedUploads.length > 0) addLog(`⚠ ${failedUploads.length} 个文件上传失败`)
      addLog(`✓ ${fileIds.length} 个文件上传成功`)

      setStage('检查冲突...')
      const checkRes = await fetch('/api/reading/batch/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds, mode: 'qual' }),
      })
      const checkData = await checkRes.json()
      if (checkData.conflict_count > 0) {
        setBatchConflictInfo(checkData)
        pendingBatchFileIdsRef.current = fileIds
        pendingBatchKeyRef.current = effectiveKey
        setStage('等待选择...')
        setIsRunning(false)
        return
      }

      setStage('启动批量精读...')
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'qual',
          extraction_method: extraction,
          api_key: effectiveKey,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'skip' | 'incremental') => {
    setBatchConflictInfo(null)
    const fileIds = pendingBatchFileIdsRef.current
    const effectiveKey = pendingBatchKeyRef.current
    setIsRunning(true)
    setStage('启动批量精读...')
    try {
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'qual',
          extraction_method: extraction,
          api_key: effectiveKey,
          conflict_resolution: resolution,
        }),
      })
      const startData = await startRes.json()
      if (!startRes.ok || !startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')
      const queuedCount = (startData.tasks || []).filter((t: any) => t.status === 'queued').length
      const errorCount = (startData.tasks || []).filter((t: any) => t.status === 'error').length
      const skippedCount = startData.skipped_count || 0
      if (queuedCount === 0 && skippedCount > 0 && errorCount === 0) {
        addLog(`ℹ ${skippedCount} 个文件已有结果，已全部跳过`)
        setStage('批量精读已跳过')
        setShowBatchPreview(false)
        setIsRunning(false)
        return
      }
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if (skippedCount > 0) addLog(`ℹ ${skippedCount} 个文件已有结果已跳过`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }

  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)] 2xl:gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf,.md,.markdown" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF / Markdown</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 cursor-pointer hover:bg-blue-100 transition-colors">
              <input type="file" {...{ webkitdirectory: 'true' }} onChange={handleFolderChange} className="hidden" />
              上传文件夹
            </label>
            {batchFiles.length > 0 && (
              <span className="text-xs text-blue-600">{batchFiles.length} 个文件待处理</span>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            PDF 文件过大无法上传？可前往
            <a href="https://aistudio.baidu.com/paddleocr" target="_blank" rel="noopener noreferrer" className="text-emerald-600 hover:text-emerald-700 underline mx-0.5">百度 PaddleOCR</a>
            将 PDF 转换为 Markdown 后上传
          </p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">★ 提取方式</h3>
          <div className="space-y-2">
            <label className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
              <input type="radio" checked={extraction === 'full'} onChange={() => setExtraction('full')} className="text-emerald-600" />
              <div><div className="text-sm font-medium text-gray-700">完整文本提取</div><div className="text-xs text-gray-400">最准确但较慢</div></div>
            </label>
            <label className="flex items-center gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
              <input type="radio" checked={extraction === 'preview'} onChange={() => setExtraction('preview')} className="text-emerald-600" />
              <div><div className="text-sm font-medium text-gray-700">快速预览</div><div className="text-xs text-gray-400">仅前 10 页，速度快</div></div>
            </label>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleStart} disabled={isRunning} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : '开始精读'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>
      <div className="space-y-4 min-w-0">
        {batchTracker.batchId && (
          <div className="rounded-xl border border-blue-200 bg-white p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-blue-700">批量精读进度</h3>
              <span className="text-xs text-gray-500">
                {batchTracker.completed + batchTracker.failed}/{batchTracker.total} 完成
                {batchTracker.failed > 0 && <span className="text-red-500 ml-1">({batchTracker.failed} 失败)</span>}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${batchTracker.total > 0 ? ((batchTracker.completed + batchTracker.failed) / batchTracker.total * 100) : 0}%` }}
              />
            </div>
            {batchTracker.isBatchRunning && (
              <p className="text-xs text-blue-600 animate-pulse mb-3">
                正在处理第 {batchTracker.completed + batchTracker.running + 1}/{batchTracker.total} 篇...
              </p>
            )}
            {!batchTracker.isBatchRunning && batchTracker.total > 0 && (
              <p className="text-xs text-emerald-600 mb-3">
                批量精读完成！成功 {batchTracker.completed} 篇，失败 {batchTracker.failed} 篇。
              </p>
            )}
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {batchTracker.tasks.map((t, i) => (
                <div key={t.task_id || i} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-xs bg-gray-50">
                  <span className="truncate text-gray-700 max-w-[200px]">{t.file_name}</span>
                  <span className={
                    t.status === 'completed' ? 'text-emerald-600 font-medium' :
                    t.status === 'failed' || t.status === 'canceled' ? 'text-red-500' :
                    t.status === 'running' ? 'text-blue-600 animate-pulse' :
                    'text-gray-400'
                  }>
                    {t.status === 'completed' ? '✓ 完成' :
                     t.status === 'failed' ? '✗ 失败' :
                     t.status === 'running' ? `⟳ ${t.progress}%` :
                     t.status === 'canceled' ? '⚠ 取消' :
                     '○ 排队'}
                  </span>
                  {t.status === 'completed' && t.download_url && (
                    <button
                      type="button"
                      onClick={() => handleProtectedDownload(t.download_url, t.download_url.split('/').pop() || 'reading-report.md').catch(err => alert(err.message || '下载失败'))}
                      className="text-blue-500 hover:underline ml-2"
                    >
                      下载
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">◉ 四步进度</h3>
          {stage && stage.startsWith('排队中') && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-blue-600 font-medium">⏳ 排队中</span>
              </div>
              <div className="text-sm text-blue-600">{stage}</div>
              <div className="mt-2 h-2 bg-blue-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full animate-pulse" style={{ width: '30%' }} />
              </div>
            </div>
          )}
          <div className="mb-4 overflow-x-auto">
            <div className="flex min-w-max items-center gap-1">
            {STEPS.map((s, i) => (
              <div key={s.num} className="flex items-center">
                <div className={`flex flex-col items-center ${i < currentStep ? 'text-emerald-600' : i === currentStep && isRunning ? 'text-emerald-500 animate-pulse' : 'text-gray-300'}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 ${i < currentStep ? 'bg-emerald-50 border-emerald-500' : i === currentStep && isRunning ? 'bg-emerald-50 border-emerald-400' : 'bg-gray-50 border-gray-200'}`}>
                    {i < currentStep ? '✓' : s.icon}
                  </div>
                  <span className="text-xs mt-1">{s.name}</span>
                </div>
                {i < STEPS.length - 1 && <div className={`w-6 h-0.5 mx-1 ${i < currentStep ? 'bg-emerald-400' : 'bg-gray-200'}`} />}
              </div>
            ))}
            </div>
          </div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm text-gray-600">{stage}</span>
            <span className="text-sm font-medium text-emerald-600">{progress}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">■ 运行日志</h3>
          <div className="rounded-lg bg-gray-900 p-3 h-64 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? <span className="text-gray-500">等待开始...</span> : logs.map((log, i) => <div key={i} className="text-gray-300 py-0.5">{log}</div>)}
          </div>
        </div>

        {showBatchPreview && batchFiles.length > 0 && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
              <h3 className="text-base font-semibold text-gray-800 mb-3">批量精读文件列表（{batchFiles.length} 篇）</h3>
              <div className="flex-1 overflow-y-auto space-y-1 mb-4">
                {batchFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg px-3 py-1.5 hover:bg-gray-50 text-sm">
                    <span className="truncate text-gray-700">{f.name}</span>
                    <button onClick={() => removeBatchFile(i)} className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0">移除</button>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => { setShowBatchPreview(false); setBatchFiles([]) }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
                <button onClick={handleBatchStart} disabled={isRunning} className="rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 px-4 py-2 text-sm font-medium text-white hover:from-blue-700 hover:to-blue-600 disabled:opacity-50">
                  {isRunning ? '上传中...' : `开始批量精读 (${batchFiles.length} 篇)`}
                </button>
              </div>
            </div>
          </div>
        )}
        {conflictInfo && (
          <ConflictDialog
            conflict={conflictInfo}
            mode="qual"
            onResolve={handleConflictResolve}
            onCancel={() => { setConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
          />
        )}
        {batchConflictInfo && (
          <BatchConflictDialog
            conflicts={batchConflictInfo.conflicts.filter((c: any) => c.has_conflict)}
            noConflictCount={batchConflictInfo.total - batchConflictInfo.conflict_count}
            mode="qual"
            onResolve={handleBatchConflictResolve}
            onCancel={() => { setBatchConflictInfo(null); setStage('已取消'); setIsRunning(false) }}
          />
        )}
      </div>
    </div>
  )
}

type AgentChatEvent = {
  id: string
  type: 'tool_call' | 'tool_result' | 'answer' | 'error' | 'proposal' | 'notice'
  title: string
  body: string
  payload?: unknown
}

type AgentChatTurn = {
  role: 'user' | 'assistant'
  content: string
}

type AgentProposal = {
  proposal_id: string
  action_type: string
  status: string
  preview?: any
  arguments?: any
}

type AgentRuntimeNotice = {
  code?: string
  message?: string
  severity?: string
  tool?: string
  blocked_tool?: string
  suggested_tools?: string[]
  recommendations?: string[]
  intent?: string
  result_set_count?: number
  budget_snapshot?: Record<string, unknown>
}

type AgentStructuredError = {
  code?: string
  message?: string
  severity?: string
  stage?: string
  retryable?: boolean
  status_code?: number
  provider?: string
  tool?: string
  details?: unknown
  recommendations?: string[]
}

type AgentToolTraceEntry = {
  tool?: string
  status?: string
  blocked?: boolean
  empty?: boolean
  hit?: boolean
  arguments_summary?: Record<string, unknown>
  result_summary?: string
  code?: string | null
  message?: string | null
}

type AgentWorkingNote = {
  kind?: string
  topic?: string
  batch_index?: number
  processed_count?: number
  total_count?: number
  summary?: string
  top_clusters?: Array<{ label?: string; count?: number }>
  priority_candidates?: Array<{ title?: string; journal?: string; year?: number; priority_score?: number }>
}

type AgentSessionState = {
  active_task_frame?: Record<string, unknown> | null
  last_result_set?: {
    result_set_id?: string
    query_summary?: string
    count?: number
    entries?: Array<{ entry_id?: string; title?: string }>
  } | null
  selected_entries?: Array<{ entry_id?: string; title?: string }>
  last_evidence_pack?: {
    evidence_pack_id?: string
    question?: string
    count?: number
    tier_summary?: Record<string, number>
  } | null
  last_sufficiency?: {
    status?: string
    can_answer?: boolean
    needs_external_consent?: boolean
    evidence_count?: number
    tier_summary?: Record<string, number>
    message?: string
  } | null
  budget_snapshot?: {
    tool_counts?: Record<string, number>
    empty_tool_counts?: Record<string, number>
  } | null
  recent_tool_trace?: AgentToolTraceEntry[]
  last_runtime_notice?: AgentRuntimeNotice | null
  last_stop_summary?: AgentRuntimeNotice | null
  last_agent_error?: AgentStructuredError | null
  last_scan_summary?: {
    source?: string
    topic?: string
    batch_id?: string | null
    scanned?: number
    candidate_count?: number
    relevant_count?: number
    library_counts?: Record<string, number>
    skipped_count?: number
    skipped_reasons?: Record<string, number>
    skipped_examples?: Array<{ filename?: string; reason?: string; message?: string }>
    scan_plan?: {
      batch_size?: number
      offset?: number
      next_offset?: number | null
      processed_total?: number
      total_available?: number
      remaining_count?: number
      has_next_batch?: boolean
      next_tool?: string | null
      workflow_steps?: string[]
    }
    recommendations?: string[]
  } | null
  working_notes?: AgentWorkingNote[]
  last_analysis_summary?: {
    topic?: string
    count?: number
    clusters?: Array<{ label?: string; count?: number }>
    journal_tier_distribution?: Array<{ label?: string; count?: number }>
    priority_candidates?: Array<{
      entry_id?: string
      title?: string
      journal?: string
      year?: number
      citation_count?: number
      priority_score?: number
      local_rule_reasons?: string[]
      journal_quality?: { label?: string; matched_name?: string } | null
      model_hint?: string
    }>
  } | null
  analysis_cache_summary?: {
    cache_id?: string
    topic?: string
    entry_count?: number
    source_scope?: string
    reused_from_cache_id?: string | null
    parent_cache_id?: string | null
  } | null
  pending_proposal?: Record<string, unknown> | null
  last_execution?: {
    proposal_id?: string
    action_type?: string
    status?: string
    job_id?: string
    batch_id?: string
    mode?: string
    selected_count?: number
    tasks?: Array<{ job_id?: string; file_name?: string; status?: string }>
  } | null
}

function tryParseJson(text: string): unknown | null {
  const trimmed = text.trim()
  if (!trimmed || !['{', '['].includes(trimmed[0])) return null
  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
}

function formatJsonScalar(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return String(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isAgentRuntimeNotice(value: unknown): value is AgentRuntimeNotice {
  return isRecord(value) && (typeof value.code === 'string' || typeof value.message === 'string')
}

function isAgentStructuredError(value: unknown): value is AgentStructuredError {
  return isRecord(value) && (
    typeof value.code === 'string'
    || typeof value.message === 'string'
    || typeof value.stage === 'string'
  )
}

function getSufficiencyTitle(status?: string) {
  if (status === 'sufficient') return '证据充分'
  if (status === 'p2_only') return '主要依据 AI 笔记'
  if (status === 'needs_external_consent') return '需要联网授权'
  if (status === 'external_only') return '仅有外部线索'
  if (status === 'insufficient') return '证据不足'
  return '证据状态'
}

function getSufficiencyStyle(status?: string) {
  if (status === 'sufficient') return {
    border: 'border-emerald-200',
    bg: 'bg-emerald-50/70',
    text: 'text-emerald-900',
    badge: 'border-emerald-200 bg-white text-emerald-700',
    bar: 'bg-emerald-600',
  }
  if (status === 'needs_external_consent') return {
    border: 'border-amber-200',
    bg: 'bg-amber-50/80',
    text: 'text-amber-900',
    badge: 'border-amber-200 bg-white text-amber-700',
    bar: 'bg-amber-500',
  }
  if (status === 'p2_only') return {
    border: 'border-violet-200',
    bg: 'bg-violet-50/70',
    text: 'text-violet-900',
    badge: 'border-violet-200 bg-white text-violet-700',
    bar: 'bg-violet-500',
  }
  return {
    border: 'border-gray-200',
    bg: 'bg-gray-50',
    text: 'text-gray-900',
    badge: 'border-gray-200 bg-white text-gray-700',
    bar: 'bg-gray-400',
  }
}

function getAgentErrorTitle(error: AgentStructuredError, fallback = '错误'): string {
  if (error.code === 'invalid_api_key') return 'API Key 无效'
  if (error.code === 'llm_auth_error') return '模型认证失败'
  if (error.code === 'llm_rate_limited') return '模型请求被限流'
  if (error.code === 'llm_timeout') return '模型响应超时'
  if (error.code === 'llm_connection_error') return '模型连接失败'
  if (error.code === 'llm_bad_request') return '模型请求不合法'
  if (error.code === 'llm_upstream_error') return '模型服务异常'
  if (error.code === 'tool_execution_error') return '工具执行失败'
  if (error.code === 'resource_not_found') return '对象不存在'
  if (error.code === 'permission_denied') return '权限不足'
  if (error.code === 'http_error') return '请求失败'
  if (error.code === 'agent_runtime_error') return '运行时异常'
  if (error.code === 'consent_required') return '需要授权'
  if (error.code === 'budget_exhausted') return '工具调用预算耗尽'
  if (error.code === 'context_resolution_failed') return '上下文解析失败'
  if (error.code === 'upload_error') return '上传失败'
  if (error.code === 'db_error') return '数据库错误'
  return fallback
}

function getAgentErrorStyle(error: AgentStructuredError): { icon: string; borderClass: string; bgClass: string; textClass: string } {
  const code = error.code || ''
  if (code === 'invalid_api_key' || code === 'llm_auth_error') {
    return { icon: '🔑', borderClass: 'border-red-300', bgClass: 'bg-red-50/60', textClass: 'text-red-700' }
  }
  if (code === 'llm_connection_error') {
    return { icon: '🔌', borderClass: 'border-orange-200', bgClass: 'bg-orange-50/60', textClass: 'text-orange-700' }
  }
  if (code === 'llm_timeout') {
    return { icon: '⏱️', borderClass: 'border-orange-200', bgClass: 'bg-orange-50/60', textClass: 'text-orange-700' }
  }
  if (code === 'llm_rate_limited') {
    return { icon: '🚦', borderClass: 'border-yellow-200', bgClass: 'bg-yellow-50/60', textClass: 'text-yellow-700' }
  }
  if (code === 'llm_upstream_error') {
    return { icon: '⚠️', borderClass: 'border-red-200', bgClass: 'bg-red-50/60', textClass: 'text-red-700' }
  }
  if (code === 'tool_execution_error') {
    return { icon: '🔧', borderClass: 'border-orange-200', bgClass: 'bg-orange-50/60', textClass: 'text-orange-700' }
  }
  if (code === 'consent_required') {
    return { icon: '🔐', borderClass: 'border-blue-200', bgClass: 'bg-blue-50/60', textClass: 'text-blue-700' }
  }
  if (code === 'budget_exhausted') {
    return { icon: '🔋', borderClass: 'border-yellow-200', bgClass: 'bg-yellow-50/60', textClass: 'text-yellow-700' }
  }
  return { icon: '❌', borderClass: 'border-red-200', bgClass: 'bg-red-50/60', textClass: 'text-red-700' }
}

function getAgentErrorMessage(error: AgentStructuredError | null | undefined, fallback = 'AI 助手执行失败。'): string {
  return error?.message || fallback
}

function normalizeAgentErrorPayload(value: unknown): AgentStructuredError | null {
  if (isAgentStructuredError(value)) return value
  if (isRecord(value) && isAgentStructuredError(value.detail)) return value.detail
  return null
}

function stringifyUnknownError(value: unknown, fallback = 'AI 助手请求失败。'): string {
  if (typeof value === 'string' && value.trim()) return value
  if (value instanceof Error && value.message.trim()) return value.message
  if (isRecord(value)) {
    if (typeof value.message === 'string' && value.message.trim()) return value.message
    if (typeof value.detail === 'string' && value.detail.trim()) return value.detail
    try {
      return JSON.stringify(value)
    } catch {
      return fallback
    }
  }
  return fallback
}

function getRuntimeNoticeTitle(notice: AgentRuntimeNotice, fallback = '运行时提示'): string {
  if (notice.code === 'max_tool_rounds_reached') return '工具调用轮次已用完'
  if (notice.code === 'continuation_context_required') return '需要先确认上一轮对象'
  if (notice.code === 'prefer_result_set_tools' || notice.code === 'prefer_contextual_result_set') return '已阻止低效工具路径'
  if (notice.code === 'external_consent_required') return '需要联网授权'
  if (notice.code === 'duplicate_tool_call_blocked' || notice.code === 'search_library_budget_exhausted') return '已阻止预算空转'
  if (notice.code === 'analysis_cache_required') return '需要先执行批量分析'
  if (notice.code === 'prefer_analysis_cache_filter') return '建议使用缓存筛选'
  if (notice.code === 'prefer_batch_analysis_tool') return '建议使用批量分析工具'
  return fallback
}

function JsonHtmlView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-xs text-gray-400">空列表</span>
    }
    const compactCards = value.every((item) => isRecord(item))
    return (
      <div className={compactCards ? 'grid gap-2 md:grid-cols-2' : 'space-y-2'}>
        {value.map((item, index) => (
          <div key={index} className="rounded-md border border-gray-200 bg-gray-50/70 p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">#{index + 1}</div>
            <JsonHtmlView value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }

  if (isRecord(value)) {
    const entries = Object.entries(value)
    if (entries.length === 0) {
      return <span className="text-xs text-gray-400">空对象</span>
    }
    return (
      <div className="space-y-2">
        {entries.map(([key, child]) => {
          const nested = Array.isArray(child) || isRecord(child)
          return (
            <div key={key} className={nested ? 'rounded-md border border-gray-100 bg-white p-3' : 'grid gap-2 sm:grid-cols-[160px_1fr]'}>
              <div className="break-words text-xs font-semibold text-gray-500">{key}</div>
              <div className="min-w-0">
                {nested ? (
                  <JsonHtmlView value={child} depth={depth + 1} />
                ) : (
                  <span
                    className={`break-words text-sm ${
                      typeof child === 'boolean'
                        ? child ? 'text-emerald-700' : 'text-rose-700'
                        : typeof child === 'number'
                          ? 'font-mono text-blue-700'
                          : 'text-gray-800'
                    }`}
                  >
                    {formatJsonScalar(child)}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  return <span className="text-sm text-gray-800">{formatJsonScalar(value)}</span>
}

const KATEX_CDN_BASES = [
  'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist',
  'https://unpkg.com/katex@0.16.11/dist',
]

let katexLoadPromise: Promise<boolean> | null = null

function loadScriptOnce(id: string, src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id) as HTMLScriptElement | null
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve()
      } else {
        existing.addEventListener('load', () => resolve(), { once: true })
        existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true })
      }
      return
    }
    const script = document.createElement('script')
    script.id = id
    script.src = src
    script.defer = true
    script.onload = () => {
      script.dataset.loaded = 'true'
      resolve()
    }
    script.onerror = () => reject(new Error(`Failed to load ${src}`))
    document.head.appendChild(script)
  })
}

async function ensureKatexAutoRender(): Promise<boolean> {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false
  if (typeof (window as any).renderMathInElement === 'function') return true
  if (katexLoadPromise) return katexLoadPromise

  katexLoadPromise = (async () => {
    for (const base of KATEX_CDN_BASES) {
      try {
        if (!document.getElementById('dra-katex-css')) {
          const link = document.createElement('link')
          link.id = 'dra-katex-css'
          link.rel = 'stylesheet'
          link.href = `${base}/katex.min.css`
          document.head.appendChild(link)
        }
        await loadScriptOnce('dra-katex-script', `${base}/katex.min.js`)
        await loadScriptOnce('dra-katex-auto-render', `${base}/contrib/auto-render.min.js`)
        return typeof (window as any).renderMathInElement === 'function'
      } catch {
        document.getElementById('dra-katex-css')?.remove()
        document.getElementById('dra-katex-script')?.remove()
        document.getElementById('dra-katex-auto-render')?.remove()
      }
    }
    return false
  })()

  return katexLoadPromise
}

function renderMathInAgentElement(el: HTMLElement) {
  ;(window as any).renderMathInElement(el, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false },
      { left: '\\(', right: '\\)', display: false },
      { left: '\\[', right: '\\]', display: true },
    ],
  })
}

function AgentMdContent({ raw }: { raw: string }) {
  const elRef = useRef<HTMLDivElement>(null)
  const html = useMemo(() => {
    let h = marked.parse(raw || '', { async: false }) as string
    h = h.replace(/<table>/g, '<div class="agent-md-table-wrap"><table>')
    h = h.replace(/<\/table>/g, '</table></div>')
    return h
  }, [raw])
  useEffect(() => {
    let cancelled = false
    async function render() {
      const ok = await ensureKatexAutoRender()
      if (!cancelled && ok && elRef.current) {
        renderMathInAgentElement(elRef.current)
      }
    }
    void render()
    return () => {
      cancelled = true
    }
  }, [html])
  return (
    <div
      ref={elRef}
      className="agent-md-content text-sm leading-relaxed text-gray-700"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

type ToolGroup = { kind: 'group'; events: AgentChatEvent[] }
type SingleEvent = { kind: 'single'; event: AgentChatEvent }
type EventBlock = ToolGroup | SingleEvent

function groupEvents(events: AgentChatEvent[]): EventBlock[] {
  const blocks: EventBlock[] = []
  let buf: AgentChatEvent[] = []
  const flush = () => {
    if (buf.length) {
      blocks.push({ kind: 'group', events: [...buf] })
      buf = []
    }
  }
  for (const ev of events) {
    if (ev.type === 'tool_call' || ev.type === 'tool_result') {
      buf.push(ev)
    } else {
      flush()
      blocks.push({ kind: 'single', event: ev })
    }
  }
  flush()
  return blocks
}

function AgentToolGroup({ events, selectable, selectedIds, onToggle }: {
  events: AgentChatEvent[]
  selectable?: boolean
  selectedIds?: Set<string>
  onToggle?: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const toolNames = events
    .filter((e) => e.type === 'tool_call')
    .map((e) => e.title.replace(/^调用工具：/, ''))
  const summary = toolNames.length > 0 ? toolNames.join(' → ') : '工具调用'
  const allSelected = selectable && events.every((e) => selectedIds?.has(e.id))
  const someSelected = selectable && events.some((e) => selectedIds?.has(e.id))
  const handleGroupToggle = () => {
    if (!onToggle) return
    if (allSelected) {
      events.forEach((e) => { if (selectedIds?.has(e.id)) onToggle(e.id) })
    } else {
      events.forEach((e) => { if (!selectedIds?.has(e.id)) onToggle(e.id) })
    }
  }
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/40 shadow-sm">
      {selectable && (
        <label className="flex cursor-pointer items-center gap-2 border-b border-blue-100 px-4 py-2 text-sm text-blue-600 hover:bg-blue-50">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => { if (el) el.indeterminate = !!(someSelected && !allSelected) }}
            onChange={handleGroupToggle}
            className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
          />
          <span className="font-medium">{summary}</span>
          <span className="ml-auto text-xs text-blue-400">{events.length} 步</span>
        </label>
      )}
      {!selectable && (
        <details
          open={open}
          onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-2.5 text-sm font-medium text-blue-700 hover:bg-blue-50 [&::-webkit-details-marker]:hidden">
            <svg
              className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path d="M6 4l8 6-8 6V4z" />
            </svg>
            <span>{summary}</span>
            <span className="ml-auto text-xs text-blue-400">{events.length} 步</span>
          </summary>
          <div className="space-y-2 border-t border-blue-100 px-4 py-3">
            {events.map((ev) => (
              <div key={ev.id}>
                <div className="mb-1 text-xs font-semibold text-gray-500">{ev.title}</div>
                <AgentEventBody event={ev} />
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function AgentEventList({ events, selectable, selectedIds, onToggle }: {
  events: AgentChatEvent[]
  selectable?: boolean
  selectedIds?: Set<string>
  onToggle?: (id: string) => void
}) {
  const blocks = useMemo(() => groupEvents(events), [events])
  return (
    <>
      {blocks.map((block, i) =>
        block.kind === 'group' ? (
          <AgentToolGroup
            key={`g-${i}`}
            events={block.events}
            selectable={selectable}
            selectedIds={selectedIds}
            onToggle={onToggle}
          />
        ) : (
          <div
            key={block.event.id}
            className={`rounded-lg border bg-white p-4 shadow-sm ${
              block.event.type === 'error'
                ? 'border-red-200'
                : block.event.type === 'notice'
                  ? 'border-amber-200'
                : 'border-emerald-200'
            }`}
          >
            {selectable && (
              <label className="mb-2 flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds?.has(block.event.id) ?? false}
                  onChange={() => onToggle?.(block.event.id)}
                  className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span className="text-sm font-semibold text-gray-800">{block.event.title}</span>
              </label>
            )}
            {!selectable && (
              <div className="mb-2 text-sm font-semibold text-gray-800">{block.event.title}</div>
            )}
            <AgentEventBody event={block.event} />
          </div>
        ),
      )}
    </>
  )
}

function AgentRuntimeNoticeCard({ notice }: { notice: AgentRuntimeNotice }) {
  const severity = notice.severity === 'error' ? 'error' : notice.severity === 'info' ? 'info' : 'warning'
  const wrapperClass =
    severity === 'error'
      ? 'border-red-200 bg-red-50/70'
      : severity === 'info'
        ? 'border-sky-200 bg-sky-50/70'
        : 'border-amber-200 bg-amber-50/80'
  const badgeClass =
    severity === 'error'
      ? 'border-red-200 bg-white text-red-700'
      : severity === 'info'
        ? 'border-sky-200 bg-white text-sky-700'
        : 'border-amber-200 bg-white text-amber-700'

  const hasDetails = (notice.blocked_tool || notice.tool || notice.result_set_count !== undefined)
    || (Array.isArray(notice.suggested_tools) && notice.suggested_tools.length > 0)
    || (Array.isArray(notice.recommendations) && notice.recommendations.length > 0)

  return (
    <details className={`rounded-lg border p-3 ${wrapperClass}`} open={severity === 'error'}>
      <summary className="cursor-pointer select-none">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-gray-900">{getRuntimeNoticeTitle(notice)}</div>
            <div className="mt-1 text-sm text-gray-700">{notice.message || '暂无详细说明'}</div>
          </div>
          <div className="flex items-center gap-2">
            {notice.code && (
              <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
                {notice.code}
              </span>
            )}
            {hasDetails && <span className="text-xs text-gray-400">点击展开</span>}
          </div>
        </div>
      </summary>
      {hasDetails && (
        <div className="mt-2 space-y-2">
          {(notice.blocked_tool || notice.tool || notice.result_set_count !== undefined) && (
            <div className="flex flex-wrap gap-2 text-xs text-gray-600">
              {notice.blocked_tool && (
                <span className="rounded-full border border-gray-200 bg-white px-2 py-1">blocked: {notice.blocked_tool}</span>
              )}
              {notice.tool && notice.tool !== notice.blocked_tool && (
                <span className="rounded-full border border-gray-200 bg-white px-2 py-1">tool: {notice.tool}</span>
              )}
              {typeof notice.result_set_count === 'number' && (
                <span className="rounded-full border border-gray-200 bg-white px-2 py-1">result_set: {notice.result_set_count}</span>
              )}
            </div>
          )}
          {Array.isArray(notice.suggested_tools) && notice.suggested_tools.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold text-gray-500">建议工具</div>
              <div className="flex flex-wrap gap-2">
                {notice.suggested_tools.map((tool) => (
                  <span key={tool} className="rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          )}
          {Array.isArray(notice.recommendations) && notice.recommendations.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold text-gray-500">下一步建议</div>
              <div className="space-y-1 text-sm text-gray-700">
                {notice.recommendations.map((item, index) => (
                  <div key={`${item}-${index}`}>{index + 1}. {item}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </details>
  )
}

function AgentSufficiencyCard({ sufficiency }: { sufficiency: NonNullable<AgentSessionState['last_sufficiency']> }) {
  const style = getSufficiencyStyle(sufficiency.status)
  const tierSummary = sufficiency.tier_summary || {}
  const tiers = ['P0', 'P1', 'P2', 'P3']
  const evidenceCount = typeof sufficiency.evidence_count === 'number'
    ? sufficiency.evidence_count
    : tiers.reduce((sum, tier) => sum + (tierSummary[tier] || 0), 0)

  return (
    <div className={`rounded-lg border ${style.border} ${style.bg} p-4 shadow-sm`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className={`text-sm font-semibold ${style.text}`}>{getSufficiencyTitle(sufficiency.status)}</div>
          <div className="mt-1 text-sm text-gray-700">
            {sufficiency.message || '最近一次证据包已完成质量判断。'}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${style.badge}`}>
            {sufficiency.can_answer ? '可回答' : '先别回答'}
          </span>
          {sufficiency.needs_external_consent && (
            <span className="rounded-full border border-amber-200 bg-white px-2 py-0.5 text-xs font-medium text-amber-700">
              需授权
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        {tiers.map((tier) => {
          const count = tierSummary[tier] || 0
          const width = evidenceCount > 0 ? Math.max(8, Math.round((count / evidenceCount) * 100)) : 0
          return (
            <div key={tier} className="rounded-md border border-white/70 bg-white p-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700">{tier}</span>
                <span className="text-gray-500">{count}</span>
              </div>
              <div className="mt-2 h-1.5 rounded-full bg-gray-100">
                <div className={`h-1.5 rounded-full ${style.bar}`} style={{ width: `${width}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AgentInboxSummaryCard({ summary }: { summary: AgentInboxUploadSummary }) {
  const errorEntries = Object.entries(summary.error_counts || {})
  const failedExamples = summary.failed_examples || []
  const recommendations = summary.recommendations || []

  return (
    <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-gray-900">最近上传批次摘要</div>
          <div className="mt-1 text-sm text-gray-700">
            共 {summary.total_files ?? 0} 个文件，成功 {summary.succeeded ?? 0} 个，失败 {summary.failed ?? 0} 个。
          </div>
        </div>
        {summary.status && (
          <span className="rounded-full border border-emerald-200 bg-white px-2 py-0.5 text-xs font-medium text-emerald-700">
            {summary.status}
          </span>
        )}
      </div>
      <div className="grid gap-2 text-xs text-gray-700 md:grid-cols-2">
        <div className="rounded-md border border-emerald-100 bg-white p-3">新导入：{summary.imported_count ?? 0}</div>
        <div className="rounded-md border border-emerald-100 bg-white p-3">去重复用：{summary.deduplicated_count ?? 0}</div>
        <div className="rounded-md border border-emerald-100 bg-white p-3">已匹配文献库：{summary.matched_count ?? 0}</div>
        <div className="rounded-md border border-emerald-100 bg-white p-3">待人工确认：{summary.unmatched_count ?? 0}</div>
      </div>
      {errorEntries.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">失败原因聚合</div>
          <div className="flex flex-wrap gap-2">
            {errorEntries.map(([code, count]) => (
              <span key={code} className="rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                {code} x {count}
              </span>
            ))}
          </div>
        </div>
      )}
      {failedExamples.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">失败样例</div>
          <div className="space-y-2">
            {failedExamples.map((item, index) => (
              <div key={`${item.filename || item.error || 'failed'}-${index}`} className="rounded-md border border-emerald-100 bg-white p-3 text-xs text-gray-700">
                <div className="font-medium text-gray-800">{item.filename || '未命名文件'}</div>
                <div className="mt-1">{item.message || item.error || '未知错误'}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {recommendations.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">建议操作</div>
          <div className="space-y-1 text-sm text-gray-700">
            {recommendations.map((item, index) => (
              <div key={`${item}-${index}`}>{index + 1}. {item}</div>
            ))}
          </div>
        </div>
      )}
      {summary.created_at && (
        <div className="text-xs text-gray-500">创建时间：{new Date(summary.created_at).toLocaleString()}</div>
      )}
    </div>
  )
}

function AgentErrorCard({ error }: { error: AgentStructuredError }) {
  const retryable = Boolean(error.retryable)
  const style = getAgentErrorStyle(error)
  const badgeClass = retryable
    ? 'border-amber-200 bg-white text-amber-700'
    : 'border-red-200 bg-white text-red-700'

  return (
    <div className={`space-y-3 rounded-lg border p-3 ${style.borderClass} ${style.bgClass}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <span className="text-lg leading-none mt-0.5">{style.icon}</span>
          <div>
            <div className="text-sm font-semibold text-gray-900">{getAgentErrorTitle(error)}</div>
            <div className="mt-1 text-sm text-gray-700">{getAgentErrorMessage(error)}</div>
          </div>
        </div>
        {error.code && (
          <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
            {error.code}
          </span>
        )}
      </div>
      {(error.stage || error.provider || error.tool || error.status_code !== undefined) && (
        <div className="flex flex-wrap gap-2 text-xs text-gray-600">
          {error.stage && (
            <span className="rounded-full border border-gray-200 bg-white px-2 py-1">stage: {error.stage}</span>
          )}
          {error.provider && (
            <span className="rounded-full border border-gray-200 bg-white px-2 py-1">provider: {error.provider}</span>
          )}
          {error.tool && (
            <span className="rounded-full border border-gray-200 bg-white px-2 py-1">tool: {error.tool}</span>
          )}
          {typeof error.status_code === 'number' && (
            <span className="rounded-full border border-gray-200 bg-white px-2 py-1">status: {error.status_code}</span>
          )}
          <span className="rounded-full border border-gray-200 bg-white px-2 py-1">
            {retryable ? '可重试' : '需修正后再试'}
          </span>
        </div>
      )}
      {Array.isArray(error.recommendations) && error.recommendations.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">建议处理</div>
          <div className="space-y-1 text-sm text-gray-700">
            {error.recommendations.map((item, index) => (
              <div key={`${item}-${index}`}>{index + 1}. {item}</div>
            ))}
          </div>
        </div>
      )}
      {error.details !== undefined && error.details !== null && (
        <details className="rounded-md border border-red-100 bg-white p-3">
          <summary className="cursor-pointer text-xs font-semibold text-gray-500">错误细节</summary>
          <div className="mt-2">
            <JsonHtmlView value={error.details} />
          </div>
        </details>
      )}
    </div>
  )
}

function AgentEventBody({ event }: { event: AgentChatEvent }) {
  if (event.type === 'answer' && event.title === 'AI 助手' && event.body.trim()) {
    return <AgentMdContent raw={event.body} />
  }
  const parsed = event.payload ?? tryParseJson(event.body)
  if (isAgentStructuredError(parsed) && event.type === 'error') {
    return <AgentErrorCard error={parsed} />
  }
  if (isAgentRuntimeNotice(parsed)) {
    return <AgentRuntimeNoticeCard notice={parsed} />
  }
  if (isRecord(parsed) && Array.isArray(parsed.open_urls)) {
    const urls = parsed.open_urls.filter((url): url is string => typeof url === 'string' && url.startsWith('http'))
    const items = Array.isArray(parsed.items) ? parsed.items : Array.isArray(parsed.results) ? parsed.results : []
    const openAll = () => {
      urls.slice(0, 50).forEach((url) => {
        window.open(url, '_blank', 'noopener,noreferrer')
      })
    }
    return (
      <div className="space-y-3 rounded-lg border border-blue-100 bg-blue-50/40 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-gray-900">{String(parsed.tool || '外部检索链接')}</div>
            <div className="mt-0.5 text-xs text-gray-600">{String(parsed.note || `共 ${urls.length} 个可打开链接`)}</div>
          </div>
          <button
            type="button"
            onClick={openAll}
            disabled={urls.length === 0}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            打开全部链接
          </button>
        </div>
        {items.length > 0 && (
          <div className="max-h-72 overflow-auto rounded-md border border-blue-100 bg-white">
            {items.slice(0, 50).map((item, index) => {
              const row = isRecord(item) ? item : {}
              const url = typeof row.url === 'string' ? row.url : ''
              return (
                <div key={`${url || index}-${index}`} className="border-b border-gray-100 px-3 py-2 last:border-b-0">
                  <div className="text-sm font-medium text-gray-900">{String(row.title || row.label || row.source || `链接 ${index + 1}`)}</div>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-blue-700 hover:underline">
                      {url}
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  }
  if (isRecord(parsed) && Array.isArray(parsed.papers) && isRecord(parsed.library_counts)) {
    const papers = parsed.papers as any[]
    const counts = parsed.library_counts as Record<string, unknown>
    const badgeClass = (status: string) => {
      if (status === 'in_library') return 'bg-emerald-50 text-emerald-700 border-emerald-200'
      if (status === 'possible_match') return 'bg-amber-50 text-amber-700 border-amber-200'
      if (status === 'not_in_library') return 'bg-blue-50 text-blue-700 border-blue-200'
      return 'bg-gray-50 text-gray-600 border-gray-200'
    }
    const statusText = (status: string) => ({
      in_library: '已在库',
      possible_match: '疑似匹配',
      not_in_library: '未入库',
      file_exists_no_bib_entry: '文件已存在',
    }[status] || status || '未知')

    return (
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-4">
          {([
            ['已在库', counts.in_library],
            ['疑似匹配', counts.possible_match],
            ['未入库', counts.not_in_library],
            ['文件已存在', counts.file_exists_no_bib_entry],
          ] as Array<[string, unknown]>).map(([label, value]) => (
            <div key={label} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <div className="text-[11px] font-medium text-gray-500">{label}</div>
              <div className="mt-1 text-lg font-semibold text-gray-900">{String(value ?? 0)}</div>
            </div>
          ))}
        </div>
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left text-xs font-semibold text-gray-500">
              <tr>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">标题</th>
                <th className="px-3 py-2">文件</th>
                <th className="px-3 py-2">相关性</th>
                <th className="px-3 py-2">匹配到的库内标题</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {papers.slice(0, 80).map((paper, index) => {
                const match = paper.library_match || {}
                return (
                  <tr key={`${paper.filename || index}-${index}`} className="align-top">
                    <td className="px-3 py-2">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${badgeClass(match.status)}`}>
                        {statusText(match.status)}
                      </span>
                    </td>
                    <td className="max-w-xs px-3 py-2 font-medium text-gray-900">{paper.title}</td>
                    <td className="max-w-xs break-all px-3 py-2 text-gray-600">{paper.filename}</td>
                    <td className="px-3 py-2 text-gray-600">{paper.relevant ? `相关 ${Math.round((paper.confidence || 0) * 100)}%` : '不相关'}</td>
                    <td className="max-w-xs px-3 py-2 text-gray-600">{match.library_title || '-'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (parsed !== null && parsed !== undefined) {
    return (
      <div className="max-h-[520px] overflow-auto rounded-lg border border-gray-100 bg-white p-3">
        <JsonHtmlView value={parsed} />
      </div>
    )
  }
  return <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700">{event.body}</pre>
}

function AgentScanSummaryCard({ summary }: { summary: NonNullable<AgentSessionState['last_scan_summary']> }) {
  const libraryEntries = Object.entries(summary.library_counts || {})
  const skippedReasonEntries = Object.entries(summary.skipped_reasons || {})
  const skippedExamples = summary.skipped_examples || []
  const recommendations = summary.recommendations || []
  const scanPlan = summary.scan_plan || {}
  const sourceLabel = summary.source === 'upload_batch'
    ? '已上传批次'
    : summary.source === 'server_folder'
      ? '服务器目录'
      : summary.source || '未知来源'

  return (
    <div className="space-y-3 rounded-lg border border-violet-200 bg-violet-50/60 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-violet-900">最近一次扫描摘要</div>
          <div className="mt-1 text-sm text-violet-800">
            来源：{sourceLabel}，主题：{summary.topic || '*'}
          </div>
        </div>
        {summary.batch_id && (
          <span className="rounded-full border border-violet-200 bg-white px-2 py-0.5 text-xs font-medium text-violet-700">
            batch: {summary.batch_id}
          </span>
        )}
      </div>
      <div className="grid gap-2 text-xs text-gray-700 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-md border border-violet-100 bg-white p-3">扫描文件：{summary.scanned ?? 0}</div>
        <div className="rounded-md border border-violet-100 bg-white p-3">候选文献：{summary.candidate_count ?? 0}</div>
        <div className="rounded-md border border-violet-100 bg-white p-3">相关文献：{summary.relevant_count ?? 0}</div>
        <div className="rounded-md border border-violet-100 bg-white p-3">跳过文件：{summary.skipped_count ?? 0}</div>
      </div>
      {typeof scanPlan.total_available === 'number' && (
        <div className="rounded-md border border-violet-100 bg-white p-3 text-xs text-gray-700">
          <div className="font-semibold text-violet-900">Batch workflow</div>
          <div className="mt-1">
            Processed {scanPlan.processed_total ?? 0}/{scanPlan.total_available ?? 0}
            {scanPlan.has_next_batch && typeof scanPlan.next_offset === 'number'
              ? `; next offset ${scanPlan.next_offset}`
              : '; all batches scanned'}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(scanPlan.workflow_steps || []).map((step) => (
              <span key={step} className="rounded-full border border-violet-100 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-700">
                {step}
              </span>
            ))}
          </div>
        </div>
      )}
      {libraryEntries.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">文献库映射</div>
          <div className="flex flex-wrap gap-2">
            {libraryEntries.map(([key, value]) => (
              <span key={key} className="rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                {key}: {value}
              </span>
            ))}
          </div>
        </div>
      )}
      {skippedReasonEntries.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">跳过原因</div>
          <div className="flex flex-wrap gap-2">
            {skippedReasonEntries.map(([key, value]) => (
              <span key={key} className="rounded-full border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                {key} x {value}
              </span>
            ))}
          </div>
        </div>
      )}
      {skippedExamples.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">跳过样例</div>
          <div className="space-y-2">
            {skippedExamples.map((item, index) => (
              <div key={`${item.filename || item.reason || 'skipped'}-${index}`} className="rounded-md border border-violet-100 bg-white p-3 text-xs text-gray-700">
                <div className="font-medium text-gray-800">{item.filename || '未命名文件'}</div>
                <div className="mt-1">{item.message || item.reason || '未知原因'}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {recommendations.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-gray-500">建议操作</div>
          <div className="space-y-1 text-sm text-gray-700">
            {recommendations.map((item, index) => (
              <div key={`${item}-${index}`}>{index + 1}. {item}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function AgentToolTraceCard({ traces }: { traces: AgentToolTraceEntry[] }) {
  const statusLabel = (status?: string) => {
    if (status === 'blocked') return '已拦截'
    if (status === 'proposal') return '提案'
    if (status === 'empty') return '空结果'
    if (status === 'error') return '失败'
    return '命中'
  }

  const statusClass = (status?: string) => {
    if (status === 'blocked') return 'border-amber-200 bg-amber-50 text-amber-700'
    if (status === 'proposal') return 'border-sky-200 bg-sky-50 text-sky-700'
    if (status === 'empty') return 'border-gray-200 bg-gray-50 text-gray-700'
    if (status === 'error') return 'border-red-200 bg-red-50 text-red-700'
    return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  }

  const hitCount = traces.filter(t => t.status !== 'blocked' && t.status !== 'empty' && t.status !== 'error').length
  const blockedCount = traces.filter(t => t.status === 'blocked').length
  const emptyCount = traces.filter(t => t.status === 'empty').length

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-900">最近工具轨迹</div>
          <div className="mt-1 text-sm text-slate-700">展示最近几步工具调用的参数摘要、命中情况和停止原因。</div>
        </div>
        <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700">
          {traces.length} 步
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700">{hitCount} 次命中</span>
        <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-medium text-gray-600">{emptyCount} 次空结果</span>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 font-medium text-amber-700">{blockedCount} 次被策略拦截</span>
      </div>
      <div className="mt-3 space-y-2">
        {traces.map((trace, index) => (
          <div key={`${trace.tool || 'tool'}-${index}`} className="rounded-md border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="text-sm font-medium text-gray-900">{trace.tool || `工具 ${index + 1}`}</div>
                <div className="mt-1 text-sm text-gray-700">{trace.result_summary || '已完成工具调用'}</div>
              </div>
              <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${statusClass(trace.status)}`}>
                {statusLabel(trace.status)}
              </span>
            </div>
            {trace.arguments_summary && Object.keys(trace.arguments_summary).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(trace.arguments_summary).map(([key, value]) => (
                  <span key={key} className="rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-700">
                    {key}: {Array.isArray(value) ? value.join(', ') : String(value)}
                  </span>
                ))}
              </div>
            )}
            {(trace.code || trace.message) && (
              <div className="mt-2 text-xs text-gray-500">
                {trace.code ? `${trace.code}${trace.message ? ' · ' : ''}` : ''}
                {trace.message || ''}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function AgentTab({ apiKey }: { apiKey: string }) {
  const user = useAuthStore((state) => state.user)
  const [message, setMessage] = useState('')
  const [events, setEvents] = useState<AgentChatEvent[]>([])
  const [history, setHistory] = useState<AgentChatTurn[]>([])
  const [sessionId, setSessionId] = useState('')
  const [sessionState, setSessionState] = useState<AgentSessionState | null>(null)
  const [pendingProposal, setPendingProposal] = useState<AgentProposal | null>(null)
  const [confirmingProposal, setConfirmingProposal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [exportMode, setExportMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [journalKbEffectiveContent, setJournalKbEffectiveContent] = useState('')
  const [journalKbUserContent, setJournalKbUserContent] = useState('')
  const [journalKbSystemContent, setJournalKbSystemContent] = useState('')
  const [journalKbSource, setJournalKbSource] = useState('')
  const [journalKbHasUserOverride, setJournalKbHasUserOverride] = useState(false)
  const [journalKbLoading, setJournalKbLoading] = useState(false)
  const [journalKbMessage, setJournalKbMessage] = useState('')
  const [journalKbPanelOpen, setJournalKbPanelOpen] = useState(false)

  const appendEvent = (event: Omit<AgentChatEvent, 'id'>) => {
    setEvents((prev) => [...prev, { ...event, id: `${Date.now()}-${Math.random()}` }])
  }

  const readPromptError = async (response: Response) => {
    const text = await response.text()
    try {
      const data = JSON.parse(text)
      return data?.detail || data?.message || `请求失败（HTTP ${response.status}）`
    } catch {
      return text || `请求失败（HTTP ${response.status}）`
    }
  }

  const journalKbSourceLabel =
    journalKbSource === 'user_override'
      ? '当前生效：我的覆盖'
      : journalKbSource === 'system_default'
        ? '当前生效：系统默认'
        : journalKbSource === 'file_fallback'
          ? '当前生效：文件兜底'
          : journalKbSource === 'builtin_fallback'
            ? '当前生效：代码兜底'
            : '当前生效：未确定'

  const journalKbLines = journalKbEffectiveContent
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => /^-\s+\*\*/.test(line))

  const loadJournalKb = async () => {
    const params = new URLSearchParams({ type: 'journal_kb', key: 'top_tier_registry' })
    const response = await fetch(`/api/prompts/item?${params.toString()}`)
    if (!response.ok) throw new Error(await readPromptError(response))
    const data = await response.json()
    setJournalKbEffectiveContent(data.effective_content || '')
    setJournalKbUserContent(data.user_content || '')
    setJournalKbSystemContent(data.system_content || '')
    setJournalKbSource(data.source || '')
    setJournalKbHasUserOverride(Boolean(data.has_user_override))
  }

  const refreshJournalKb = async () => {
    setJournalKbLoading(true)
    setJournalKbMessage('')
    try {
      await loadJournalKb()
      setJournalKbMessage('✓ 顶刊名录已加载')
    } catch (err: any) {
      setJournalKbMessage(`❌ ${err?.message || '顶刊名录加载失败'}`)
    }
    setJournalKbLoading(false)
  }

  const saveJournalKbUserOverride = async () => {
    setJournalKbLoading(true)
    setJournalKbMessage('')
    try {
      const response = await fetch('/api/prompts/my', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'journal_kb',
          key: 'top_tier_registry',
          content: journalKbUserContent,
        }),
      })
      if (!response.ok) throw new Error(await readPromptError(response))
      await refreshJournalKb()
      setJournalKbMessage('✓ 我的顶刊名录覆盖已保存')
    } catch (err: any) {
      setJournalKbMessage(`❌ ${err?.message || '保存顶刊名录失败'}`)
    }
    setJournalKbLoading(false)
  }

  const resetJournalKbUserOverride = async () => {
    setJournalKbLoading(true)
    setJournalKbMessage('')
    try {
      const params = new URLSearchParams({ type: 'journal_kb', key: 'top_tier_registry' })
      const response = await fetch(`/api/prompts/my?${params.toString()}`, { method: 'DELETE' })
      if (!response.ok) throw new Error(await readPromptError(response))
      await refreshJournalKb()
      setJournalKbMessage('✓ 已恢复为系统默认顶刊名录')
    } catch (err: any) {
      setJournalKbMessage(`❌ ${err?.message || '恢复默认顶刊名录失败'}`)
    }
    setJournalKbLoading(false)
  }

  const saveJournalKbSystemDefault = async () => {
    setJournalKbLoading(true)
    setJournalKbMessage('')
    try {
      const response = await fetch('/api/prompts/system', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'journal_kb',
          key: 'top_tier_registry',
          content: journalKbSystemContent,
        }),
      })
      if (!response.ok) throw new Error(await readPromptError(response))
      await refreshJournalKb()
      setJournalKbMessage('✓ 系统默认顶刊名录已保存')
    } catch (err: any) {
      setJournalKbMessage(`❌ ${err?.message || '保存系统默认顶刊名录失败'}`)
    }
    setJournalKbLoading(false)
  }

  useEffect(() => {
    let cancelled = false
    const loadLatestSession = async () => {
      try {
        const sessionsResponse = await fetch('/api/agent/sessions')
        if (!sessionsResponse.ok) return
        const sessions = await sessionsResponse.json()
        const latest = Array.isArray(sessions) ? sessions[0] : null
        if (!latest?.id) return
        const detailResponse = await fetch(`/api/agent/sessions/${latest.id}`)
        if (!detailResponse.ok) return
        const detail = await detailResponse.json()
        if (cancelled) return
        setSessionId(detail.id)
        setSessionState(detail.last_state || null)
        const restoredEvents: AgentChatEvent[] = (detail.messages || []).map((item: any) => {
          const payload = item.payload
          if (item.event_type === 'tool_call') {
            return { id: item.id, type: 'tool_call', title: `调用工具：${item.tool_name}`, body: JSON.stringify(payload || {}, null, 2), payload }
          }
          if (item.event_type === 'proposal') {
            return { id: item.id, type: 'proposal', title: `执行提案：${item.tool_name}`, body: JSON.stringify(payload || {}, null, 2), payload }
          }
          if (item.event_type === 'tool_result') {
            return { id: item.id, type: 'tool_result', title: `工具结果：${item.tool_name || '执行结果'}`, body: JSON.stringify(payload || {}, null, 2), payload }
          }
          return {
            id: item.id,
            type: item.role === 'user' ? 'answer' : item.event_type === 'error' ? 'error' : 'answer',
            title: item.role === 'user' ? '你' : 'AI 助手',
            body: item.content || '',
          }
        })
        setEvents(restoredEvents)
        setHistory(
          (detail.messages || [])
            .filter((item: any) => item.event_type === 'message' && ['user', 'assistant'].includes(item.role))
            .map((item: any) => ({ role: item.role, content: item.content }))
            .slice(-12),
        )
        const openProposal = (detail.proposals || []).find((proposal: AgentProposal) => proposal.status === 'pending')
        setPendingProposal(openProposal || null)
      } catch {
        // Session restore is best-effort.
      }
    }
    void loadLatestSession()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void refreshJournalKb()
  }, [])

  const sendMessage = async () => {
    const text = message.trim()
    if (!text || loading) return
    if (!apiKey) {
      setError('请先在右上角设置 DeepSeek API Key。')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    setEvents((prev) => [
      ...prev,
      { id: `${Date.now()}-user`, type: 'answer', title: '你', body: text },
    ])

    let answer = ''
    try {
      const response = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId || undefined,
          message: text,
          api_key: apiKey,
          history: history.slice(-8),
        }),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        const structuredError = normalizeAgentErrorPayload(detail?.detail ?? detail)
        if (structuredError) throw structuredError
        throw new Error(stringifyUnknownError(detail?.detail ?? detail))
      }
      if (!response.body) throw new Error('AI 助手未返回流式内容。')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const handleBlock = (block: string) => {
        const eventLine = block.split('\n').find((line) => line.startsWith('event: '))
        const dataLine = block.split('\n').find((line) => line.startsWith('data: '))
        if (!eventLine || !dataLine) return
        const eventName = eventLine.slice(7).trim()
        const data = JSON.parse(dataLine.slice(6))
        if (eventName === 'session') {
          if (data.session_id) setSessionId(data.session_id)
          if (data.last_state) setSessionState(data.last_state)
        } else if (eventName === 'session_state') {
          if (data.last_state) setSessionState(data.last_state)
        } else if (eventName === 'tool_call') {
          appendEvent({
            type: 'tool_call',
            title: `调用工具：${data.name}`,
            body: JSON.stringify(data.arguments || {}, null, 2),
            payload: data.arguments || {},
          })
        } else if (eventName === 'tool_result') {
          const result = data.result || {}
          appendEvent({
            type: 'tool_result',
            title: `工具结果：${data.name}`,
            body: JSON.stringify(result, null, 2).slice(0, 8000),
            payload: result,
          })
          if (result?.proposal_id) {
            setPendingProposal(result)
          }
        } else if (eventName === 'proposal') {
          setPendingProposal(data)
          appendEvent({
            type: 'proposal',
            title: `执行提案：${data.action_type}`,
            body: JSON.stringify(data, null, 2),
            payload: data,
          })
        } else if (eventName === 'analysis_progress') {
          appendEvent({
            type: 'notice',
            title: `批次分析进度：${data.processed_count || 0}/${data.total_count || 0}`,
            body: JSON.stringify(data, null, 2),
            payload: data,
          })
        } else if (eventName === 'runtime_notice') {
          appendEvent({
            type: 'notice',
            title: getRuntimeNoticeTitle(data, '运行时提示'),
            body: JSON.stringify(data, null, 2),
            payload: data,
          })
        } else if (eventName === 'answer') {
          answer += data.content || ''
          appendEvent({
            type: 'answer',
            title: 'AI 助手',
            body: data.content || '',
          })
        } else if (eventName === 'error') {
          throw normalizeAgentErrorPayload(data) || new Error(data.message || 'AI 助手执行失败。')
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''
        blocks.forEach(handleBlock)
      }
      if (buffer.trim()) handleBlock(buffer)

      setHistory((prev) => [
        ...prev,
        { role: 'user' as const, content: text },
        { role: 'assistant' as const, content: answer || '已完成工具调用。' },
      ].slice(-12))
    } catch (err) {
      const structuredError = normalizeAgentErrorPayload(err)
      const messageText = structuredError
        ? getAgentErrorMessage(structuredError)
        : err instanceof Error
          ? err.message
          : 'AI 助手执行失败。'
      setError(messageText)
      appendEvent({
        type: 'error',
        title: structuredError ? getAgentErrorTitle(structuredError) : '错误',
        body: structuredError ? JSON.stringify(structuredError, null, 2) : messageText,
        payload: structuredError || undefined,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmProposal = async () => {
    if (!pendingProposal || confirmingProposal) return
    if (!apiKey) {
      setError('请先在右上角设置 DeepSeek API Key。')
      return
    }
    setConfirmingProposal(true)
    try {
      const response = await fetch(`/api/agent/proposals/${pendingProposal.proposal_id}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || `确认执行失败（HTTP ${response.status}）`)
      }
      if (data?.last_state) setSessionState(data.last_state)
      appendEvent({
        type: 'tool_result',
        title: '确认执行结果',
        body: JSON.stringify(data.result || data, null, 2),
        payload: data.result || data,
      })
      setPendingProposal(null)
    } catch (err) {
      const messageText = err instanceof Error ? err.message : '确认执行失败。'
      setError(messageText)
      appendEvent({ type: 'error', title: '错误', body: messageText })
    } finally {
      setConfirmingProposal(false)
    }
  }

  const handleRejectProposal = async () => {
    if (!pendingProposal || confirmingProposal) return
    setConfirmingProposal(true)
    try {
      const response = await fetch(`/api/agent/proposals/${pendingProposal.proposal_id}/reject`, {
        method: 'POST',
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || `取消失败（HTTP ${response.status}）`)
      }
      const data = await response.json().catch(() => null)
      if (data?.last_state) setSessionState(data.last_state)
      appendEvent({
        type: 'answer',
        title: 'AI 助手',
        body: '已取消这次执行提案。',
      })
      setPendingProposal(null)
    } catch (err) {
      const messageText = err instanceof Error ? err.message : '取消失败。'
      setError(messageText)
      appendEvent({ type: 'error', title: '错误', body: messageText })
    } finally {
      setConfirmingProposal(false)
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAll = () => setSelectedIds(new Set(events.map((e) => e.id)))
  const deselectAll = () => setSelectedIds(new Set())

  const exportSelected = () => {
    const selected = events.filter((e) => selectedIds.has(e.id))
    if (!selected.length) return
    const lines: string[] = ['# AI 文献助手对话记录', '']
    for (const ev of selected) {
      if (ev.type === 'answer' && ev.title === '你') {
        lines.push(`## 👤 ${ev.title}`, '', ev.body, '')
      } else if (ev.type === 'answer' && ev.title === 'AI 助手') {
        lines.push(`## 🤖 ${ev.title}`, '', ev.body, '')
      } else if (ev.type === 'notice') {
        lines.push(`<details><summary>⚠ ${ev.title}</summary>`, '', '```json', ev.body, '```', '</details>', '')
      } else if (ev.type === 'tool_call') {
        lines.push(`<details><summary>🔧 ${ev.title}</summary>`, '', '```json', ev.body, '```', '</details>', '')
      } else if (ev.type === 'tool_result') {
        lines.push(`<details><summary>📋 ${ev.title}</summary>`, '', '```json', ev.body, '```', '</details>', '')
      } else if (ev.type === 'proposal') {
        lines.push(`<details><summary>⚡ ${ev.title}</summary>`, '', '```json', ev.body, '```', '</details>', '')
      } else if (ev.type === 'error') {
        lines.push(`> ❌ ${ev.title}: ${ev.body}`, '')
      }
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AI文献助手_${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
    setExportMode(false)
    setSelectedIds(new Set())
  }

  const eventsEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, pendingProposal])

  return (
    <div className={`mx-auto grid max-w-6xl gap-4 ${journalKbPanelOpen ? 'xl:grid-cols-[340px_minmax(0,1fr)]' : 'grid-cols-1'}`}>
      {journalKbPanelOpen && (
      <div className="space-y-3 xl:sticky xl:top-4 xl:self-start">
          <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-amber-900">AI 助手顶刊名录</div>
                <div className="mt-1 text-sm text-amber-800">供 AI 文献助手识别顶刊、优先排序与缓存子集筛选复用。</div>
              </div>
              <button
                onClick={() => void refreshJournalKb()}
                disabled={journalKbLoading}
                className="rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50"
              >
                刷新
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs font-medium text-amber-700">
                {journalKbSourceLabel}
              </span>
              {journalKbHasUserOverride && (
                <span className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700">
                  已存在个人覆盖
                </span>
              )}
            </div>
            {journalKbMessage && (
              <div className={`mt-3 text-xs ${journalKbMessage.startsWith('✓') ? 'text-emerald-700' : 'text-red-600'}`}>
                {journalKbMessage}
              </div>
            )}
            {journalKbLines.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {journalKbLines.slice(0, 6).map((line, index) => (
                  <span key={`${line}-${index}`} className="rounded-full border border-amber-200 bg-white px-2 py-1 text-[11px] text-amber-800">
                    {line.replace(/^-+\s+\*\*(.+?)\*\*:.+$/, '$1')}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-semibold text-gray-700">当前生效名录</div>
              </div>
              <textarea
                value={journalKbEffectiveContent}
                readOnly
                rows={10}
                className="w-full rounded-lg border border-amber-100 bg-white px-3 py-2 text-xs font-mono text-gray-700"
              />
            </div>
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-semibold text-gray-700">我的覆盖</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => void saveJournalKbUserOverride()}
                    disabled={journalKbLoading}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    保存
                  </button>
                  <button
                    onClick={() => void resetJournalKbUserOverride()}
                    disabled={journalKbLoading}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    恢复默认
                  </button>
                </div>
              </div>
              <textarea
                value={journalKbUserContent}
                onChange={(event) => setJournalKbUserContent(event.target.value)}
                rows={10}
                placeholder="未设置个人覆盖时，将使用系统默认顶刊名录。"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-mono text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            {user?.role === 'admin' && (
              <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50/60 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-violet-800">系统默认顶刊名录</div>
                  <button
                    onClick={() => void saveJournalKbSystemDefault()}
                    disabled={journalKbLoading}
                    className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                  >
                    保存系统默认
                  </button>
                </div>
                <textarea
                  value={journalKbSystemContent}
                  onChange={(event) => setJournalKbSystemContent(event.target.value)}
                  rows={10}
                  className="w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-mono text-gray-700 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                />
              </div>
            )}
          </div>
          {sessionState?.last_agent_error && (
            <AgentErrorCard error={sessionState.last_agent_error} />
          )}
          {sessionState?.last_runtime_notice && (
            <AgentRuntimeNoticeCard notice={sessionState.last_runtime_notice} />
          )}
          {sessionState?.last_stop_summary && (
            <AgentRuntimeNoticeCard notice={sessionState.last_stop_summary} />
          )}
          {sessionState?.last_sufficiency && (
            <AgentSufficiencyCard sufficiency={sessionState.last_sufficiency} />
          )}
          {sessionState?.last_scan_summary && (
            <AgentScanSummaryCard summary={sessionState.last_scan_summary} />
          )}
          {sessionState?.last_analysis_summary && (
          <div className="rounded-lg border border-violet-200 bg-violet-50/70 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-violet-900">最近一次批量分析</div>
                <div className="mt-1 text-sm text-violet-800">
                  {sessionState.last_analysis_summary.topic || '未命名分析'}，共覆盖 {sessionState.last_analysis_summary.count || 0} 篇
                </div>
              </div>
            </div>
            {(sessionState.last_analysis_summary.clusters || []).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {(sessionState.last_analysis_summary.clusters || []).map((cluster, index) => (
                  <span key={`${cluster.label || index}-${index}`} className="rounded-full border border-violet-200 bg-white px-2.5 py-1 text-xs text-violet-800">
                    {cluster.label || '未命名主题'} · {cluster.count || 0}
                  </span>
                ))}
              </div>
            )}
            {(sessionState.last_analysis_summary.priority_candidates || []).length > 0 && (
              <div className="mt-3 space-y-2">
                {(sessionState.last_analysis_summary.priority_candidates || []).slice(0, 5).map((item, index) => (
                  <div key={`${item.entry_id || item.title || index}-${index}`} className="rounded-md border border-violet-100 bg-white p-3 text-sm text-gray-800">
                    <div className="font-medium text-violet-900">{item.title || `候选文献 ${index + 1}`}</div>
                    <div className="mt-1 text-xs text-gray-600">
                      {[item.journal, item.year ? `${item.year}` : '', typeof item.priority_score === 'number' ? `优先分 ${item.priority_score.toFixed(3)}` : '']
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                    {(item.local_rule_reasons || []).length > 0 && (
                      <div className="mt-2 text-xs text-gray-700">{(item.local_rule_reasons || []).join('；')}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          )}
          {sessionState?.analysis_cache_summary && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-emerald-900">当前分析缓存</div>
                <div className="mt-1 text-sm text-emerald-800">
                  {sessionState.analysis_cache_summary.topic || '未命名缓存'}，当前保留 {sessionState.analysis_cache_summary.entry_count || 0} 篇
                </div>
              </div>
              <span className="rounded-full border border-emerald-200 bg-white px-2 py-0.5 text-xs font-medium text-emerald-700">
                {sessionState.analysis_cache_summary.source_scope || 'analysis_cache'}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-emerald-700">
              {sessionState.analysis_cache_summary.cache_id && (
                <span className="rounded-full border border-emerald-200 bg-white px-2.5 py-1">
                  cache: {sessionState.analysis_cache_summary.cache_id}
                </span>
              )}
              {sessionState.analysis_cache_summary.reused_from_cache_id && (
                <span className="rounded-full border border-emerald-200 bg-white px-2.5 py-1">
                  复用自: {sessionState.analysis_cache_summary.reused_from_cache_id}
                </span>
              )}
              {sessionState.analysis_cache_summary.parent_cache_id && (
                <span className="rounded-full border border-emerald-200 bg-white px-2.5 py-1">
                  父缓存: {sessionState.analysis_cache_summary.parent_cache_id}
                </span>
              )}
            </div>
          </div>
          )}
          {Array.isArray(sessionState?.working_notes) && sessionState.working_notes.length > 0 && (
          <div className="rounded-lg border border-fuchsia-200 bg-fuchsia-50/70 p-4 shadow-sm">
            <div className="text-sm font-semibold text-fuchsia-900">最近工作笔记</div>
            <div className="mt-3 space-y-2">
              {sessionState.working_notes.slice(-4).reverse().map((note, index) => (
                <div key={`${note.topic || 'note'}-${note.batch_index || index}-${index}`} className="rounded-md border border-fuchsia-100 bg-white p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-fuchsia-900">
                      {note.topic || '批量分析'} · 第 {note.batch_index || index + 1} 批
                    </div>
                    <div className="text-xs text-gray-500">
                      {note.processed_count || 0}/{note.total_count || 0}
                    </div>
                  </div>
                  <div className="mt-1 text-sm text-gray-700">{note.summary || '暂无摘要'}</div>
                  {(note.top_clusters || []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(note.top_clusters || []).map((cluster, clusterIndex) => (
                        <span key={`${cluster.label || clusterIndex}-${clusterIndex}`} className="rounded-full border border-fuchsia-200 bg-fuchsia-50 px-2 py-0.5 text-xs text-fuchsia-700">
                          {cluster.label || '未命名主题'} · {cluster.count || 0}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          )}
          {Array.isArray(sessionState?.recent_tool_trace) && sessionState.recent_tool_trace.length > 0 && (
            <AgentToolTraceCard traces={sessionState.recent_tool_trace} />
          )}
          {sessionState?.last_result_set && (
          <div className="rounded-lg border border-sky-200 bg-sky-50/70 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-sky-900">当前工作记忆</div>
                <div className="mt-1 text-sm text-sky-800">
                  最近结果集：{sessionState.last_result_set.query_summary || '未命名结果集'}，共 {sessionState.last_result_set.count || 0} 篇
                </div>
              </div>
              {Boolean(sessionState.active_task_frame?.intent) && (
                <span className="rounded-full border border-sky-200 bg-white px-2 py-0.5 text-xs font-medium text-sky-700">
                  intent: {String(sessionState.active_task_frame?.intent || '')}
                </span>
              )}
            </div>
            {(sessionState.last_result_set.entries || []).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {(sessionState.last_result_set.entries || []).map((entry, index) => (
                  <span key={`${entry.entry_id || index}-${index}`} className="rounded-full border border-sky-200 bg-white px-2.5 py-1 text-xs text-sky-800">
                    {entry.title || entry.entry_id || `文献 ${index + 1}`}
                  </span>
                ))}
              </div>
            )}
            {(sessionState.last_evidence_pack || sessionState.budget_snapshot) && (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div className="rounded-md border border-sky-100 bg-white p-3">
                  <div className="text-xs font-semibold text-gray-500">最近证据包</div>
                  <div className="mt-1 text-sm text-gray-800">
                    {sessionState.last_evidence_pack?.question || '暂无'}
                  </div>
                </div>
                <div className="rounded-md border border-sky-100 bg-white p-3">
                  <div className="text-xs font-semibold text-gray-500">预算快照</div>
                  <div className="mt-1 text-xs text-gray-700">
                    {JSON.stringify(sessionState.budget_snapshot || {}, null, 2)}
                  </div>
                </div>
              </div>
            )}
          </div>
          )}
      </div>
      )}
      <div className="space-y-4">
        <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">AI 文献助手</h2>
              <p className="mt-1 text-sm text-gray-500">可检索文献库、读取精读结果、启动精读任务并整理对比综述。</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setJournalKbPanelOpen((prev) => !prev)}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
                  journalKbPanelOpen
                    ? 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                {journalKbPanelOpen ? '收起顶刊名录' : '顶刊名录'}
              </button>
              {events.length > 0 && !exportMode && (
                <button
                  onClick={() => {
                    setExportMode(true)
                    setSelectedIds(new Set(events.map((e) => e.id)))
                  }}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
                >
                  导出对话
                </button>
              )}
              {exportMode && (
                <>
                  <button
                    onClick={() => { setExportMode(false); setSelectedIds(new Set()) }}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => selectedIds.size === events.length ? deselectAll() : selectAll()}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    {selectedIds.size === events.length ? '取消全选' : '全选'}
                  </button>
                  <button
                    onClick={exportSelected}
                    disabled={selectedIds.size === 0}
                    className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    导出 ({selectedIds.size})
                  </button>
                </>
              )}
              {!exportMode && (
                <button
                  onClick={() => {
                    const idToArchive = sessionId
                    setEvents([])
                    setHistory([])
                    setError('')
                    setSessionId('')
                    setSessionState(null)
                    setPendingProposal(null)
                    if (idToArchive) {
                      fetch(`/api/agent/sessions/${idToArchive}/archive`, { method: 'PATCH' }).catch(() => {})
                    }
                  }}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
                >
                  清空会话
                </button>
              )}
            </div>
          </div>
        </div>
        <div className="space-y-3">
          {events.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
              还没有会话。你可以让它先查文献、再启动精读，或者基于已有精读结果写综述。
            </div>
          ) : (
            <AgentEventList
              events={events}
              selectable={exportMode}
              selectedIds={selectedIds}
              onToggle={toggleSelect}
            />
          )}

          {pendingProposal && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-amber-900">需要确认后才会执行</div>
                  <div className="mt-1 text-sm text-amber-800">
                    {pendingProposal.action_type === 'import_folder_and_start_reading'
                      ? '将导入文件夹中的候选文献并启动精读任务。'
                      : pendingProposal.action_type === 'start_batch_reading'
                        ? '将启动批量精读任务。'
                        : '将启动精读任务。'}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => void handleRejectProposal()}
                    disabled={confirmingProposal}
                    className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => void handleConfirmProposal()}
                    disabled={confirmingProposal}
                    className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                  >
                    {confirmingProposal ? '执行中...' : '确认执行'}
                  </button>
                </div>
              </div>
              <div className="mt-3">
                <AgentEventBody
                  event={{
                    id: pendingProposal.proposal_id,
                    type: 'proposal',
                    title: '执行提案',
                    body: JSON.stringify(pendingProposal.preview || pendingProposal, null, 2),
                    payload: pendingProposal.preview || pendingProposal,
                  }}
                />
              </div>
            </div>
          )}

          <div ref={eventsEndRef} />

          <div className="sticky bottom-0 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            {error && <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault()
                    void sendMessage()
                  }
                }}
                className="min-h-20 flex-1 resize-y rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                placeholder="例如：列出我库里制度经济学相关且已精读的文献，并基于精读结果写一段对比综述。（Ctrl+Enter 发送）"
              />
              <button
                onClick={() => void sendMessage()}
                disabled={loading || !message.trim()}
                className="h-20 self-end rounded-lg bg-emerald-600 px-5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? '处理中...' : '发送'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Tab 4: 提示词管理（带子Tab：提示词编辑 / 模板市场）
function PromptsTab({ apiKey }: { apiKey: string }) {
  const [promptSubTab, setPromptSubTab] = useState<'editor' | 'market'>('editor')

  return (
    <div className="w-full space-y-4">
      <div className="flex gap-1 rounded-xl border border-gray-200 bg-white p-1">
        <button
          onClick={() => setPromptSubTab('editor')}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            promptSubTab === 'editor'
              ? 'bg-emerald-50 text-emerald-700 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          提示词管理
        </button>
        <button
          onClick={() => setPromptSubTab('market')}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            promptSubTab === 'market'
              ? 'bg-emerald-50 text-emerald-700 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          模板市场
        </button>
      </div>
      {promptSubTab === 'editor' && <PromptsEditor />}
      {promptSubTab === 'market' && <TemplateMarket apiKey={apiKey} />}
    </div>
  )
}

// 提示词编辑器（原 PromptsTab 内容）
function PromptsEditor() {
  const user = useAuthStore((state) => state.user)
  const [promptType, setPromptType] = useState('long')
  const [currentKey, setCurrentKey] = useState('overview')
  const [catalog, setCatalog] = useState<any[]>([])
  const [effectiveContent, setEffectiveContent] = useState('')
  const [userContent, setUserContent] = useState('')
  const [systemContent, setSystemContent] = useState('')
  const [source, setSource] = useState('')
  const [title, setTitle] = useState('')
  const [hasUserOverride, setHasUserOverride] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('')

  const TYPES = [
    {
      id: 'quant',
      label: '七步精读',
      steps: [
        { key: 'step_1', title: 'Step 1: 研究概览' },
        { key: 'step_2', title: 'Step 2: 理论机制' },
        { key: 'step_3', title: 'Step 3: 数据说明' },
        { key: 'step_4', title: 'Step 4: 变量与度量' },
        { key: 'step_5', title: 'Step 5: 识别策略' },
        { key: 'step_6', title: 'Step 6: 结果呈现' },
        { key: 'step_7', title: 'Step 7: 批判性评估' },
      ],
    },
    {
      id: 'qual',
      label: '四步精读',
      steps: [
        { key: 'L1', title: 'L1: 背景与语境' },
        { key: 'L2', title: 'L2: 理论框架' },
        { key: 'L3', title: 'L3: 论证逻辑' },
        { key: 'L4', title: 'L4: 价值与启示' },
      ],
    },
    {
      id: 'long',
      label: '长文本精读',
      steps: [
        { key: 'overview', title: '研究问题' },
        { key: 'theory', title: '理论框架' },
        { key: 'methodology', title: '识别策略' },
        { key: 'data_source', title: '数据来源' },
        { key: 'variable_measurement', title: '变量度量' },
        { key: 'identification_assumptions', title: '识别假设' },
        { key: 'results', title: '统计结果' },
        { key: 'mechanism', title: '机制分析' },
        { key: 'robustness', title: '稳健性检验' },
        { key: 'external_validity', title: '外部有效性' },
        { key: 'contributions_limitations', title: '贡献与局限' },
        { key: 'writing_quality', title: '写作质量' },
        { key: 'custom', title: '自定义问题' },
      ],
    },
    {
      id: 'filter',
      label: '文献筛选',
      steps: [
        { key: 'explorer', title: '探索者模式' },
        { key: 'reviewer', title: '评审者模式' },
        { key: 'empiricist', title: '实证主义者' },
      ],
    },
    {
      id: 'synthesis',
      label: 'AI 综述',
      icon: '📝',
      steps: [
        { key: 'system_role', title: 'AI 综述：系统角色' },
        { key: 'compare_system_role', title: '对比综述：系统角色' },
        { key: 'dimension_prompt', title: 'AI 综述：逐维度写作指令' },
        { key: 'single_prompt', title: '对比综述：单维度写作' },
        { key: 'multi_prompt', title: '对比综述：多子问题写作' },
        { key: 'cross_dim_prompt', title: '对比综述：跨维度写作' },
        { key: 'long_single_prompt', title: '长文本对比：单维度写作' },
        { key: 'long_multi_prompt', title: '长文本对比：多维度写作' },
      ],
    },
    {
      id: 'ai_template',
      label: 'AI 模板生成',
      icon: '🤖',
      steps: [
        { key: 'meta_prompt', title: '模板生成：元提示词' },
        { key: 'system_role', title: '模板生成：系统角色' },
      ],
    },
    {
      id: 'library_chat',
      label: '文献库 AI 查询',
      steps: [
        { key: 'query_parser', title: '查询解析' },
        { key: 'report_writer', title: '报告生成' },
      ],
    },
    {
      id: 'writing_style',
      label: '写作风格分析',
      steps: [
        { key: 'single_fulltext_analyzer', title: '单篇全文：写法分析' },
        { key: 'single_imitation_advisor', title: '单篇全文：模仿写作建议' },
        { key: 'single_report_writer', title: '单篇全文：报告整理' },
        { key: 'batch_section_analyzer', title: '批量抽样：分节写法分析' },
        { key: 'batch_imitation_advisor', title: '批量抽样：模仿写作建议' },
        { key: 'batch_comparative_synthesizer', title: '批量抽样：多篇风格对比' },
        { key: 'batch_report_writer', title: '批量抽样：报告整理' },
      ],
    },
  ]

  const currentType =
    catalog.find((t) => t.type === promptType) ||
    TYPES.find((t) => t.id === promptType) ||
    TYPES[0]

  const sourceLabel =
    source === 'user_override'
      ? '当前生效：我的覆盖'
      : source === 'system_default'
        ? '当前生效：系统默认'
        : source === 'file_fallback'
          ? '当前生效：文件兜底'
          : source === 'builtin_fallback'
            ? '当前生效：代码兜底'
            : '当前生效：未确定'

  const readError = async (response: Response) => {
    const text = await response.text()
    try {
      const data = JSON.parse(text)
      return data?.detail || data?.message || `请求失败（HTTP ${response.status}）`
    } catch {
      return text || `请求失败（HTTP ${response.status}）`
    }
  }

  const syncSelectionFromCatalog = (nextCatalog: any[]) => {
    if (!nextCatalog.length) return
    const matchedType = nextCatalog.find((item) => item.type === promptType) || nextCatalog[0]
    if (matchedType.type !== promptType) {
      setPromptType(matchedType.type)
    }
    const matchedItem =
      matchedType.items?.find((item: any) => item.key === currentKey) || matchedType.items?.[0]
    if (matchedItem && matchedItem.key !== currentKey) {
      setCurrentKey(matchedItem.key)
    }
  }

  const loadCatalog = async () => {
    const res = await fetch('/api/prompts/catalog')
    if (!res.ok) throw new Error(await readError(res))
    const data = await res.json()
    const nextCatalog = data.types || []
    setCatalog(nextCatalog)
    syncSelectionFromCatalog(nextCatalog)
  }

  const loadItem = async (type: string, key: string) => {
    const params = new URLSearchParams({ type, key })
    const res = await fetch(`/api/prompts/item?${params.toString()}`)
    if (!res.ok) throw new Error(await readError(res))
    const data = await res.json()
    setTitle(data.title || '')
    setEffectiveContent(data.effective_content || '')
    setUserContent(data.user_content || '')
    setSystemContent(data.system_content || '')
    setSource(data.source || '')
    setHasUserOverride(Boolean(data.has_user_override))
  }

  const refreshAll = async (type = promptType, key = currentKey) => {
    setIsLoading(true)
    setMessage('')
    try {
      await loadCatalog()
      await loadItem(type, key)
      setMessage('✓ 提示词已加载')
    } catch (error: any) {
      setMessage(`❌ ${error?.message || '加载失败'}`)
    }
    setIsLoading(false)
  }

  useEffect(() => {
    void refreshAll(promptType, currentKey)
  }, [])

  useEffect(() => {
    if (!currentType) return
    const stepExists = (currentType.items || currentType.steps || []).some((item: any) => (item.key || item.id) === currentKey)
    if (!stepExists) {
      const fallbackKey = (currentType.items || currentType.steps || [])[0]?.key || (currentType.items || currentType.steps || [])[0]?.id
      if (fallbackKey) {
        setCurrentKey(fallbackKey)
      }
      return
    }
    void refreshAll(promptType, currentKey)
  }, [promptType, currentKey])

  const saveMyPrompt = async () => {
    setIsLoading(true)
    setMessage('')
    try {
      const res = await fetch('/api/prompts/my', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: promptType, key: currentKey, content: userContent }),
      })
      if (!res.ok) throw new Error(await readError(res))
      await refreshAll(promptType, currentKey)
      setMessage('✓ 我的提示词已保存')
    } catch (error: any) {
      setMessage(`❌ ${error?.message || '保存失败'}`)
    }
    setIsLoading(false)
  }

  const resetMyPrompt = async () => {
    setIsLoading(true)
    setMessage('')
    try {
      const params = new URLSearchParams({ type: promptType, key: currentKey })
      const res = await fetch(`/api/prompts/my?${params.toString()}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await readError(res))
      await refreshAll(promptType, currentKey)
      setMessage('✓ 已恢复为系统默认')
    } catch (error: any) {
      setMessage(`❌ ${error?.message || '恢复默认失败'}`)
    }
    setIsLoading(false)
  }

  const saveSystemPrompt = async () => {
    setIsLoading(true)
    setMessage('')
    try {
      const res = await fetch('/api/prompts/system', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: promptType, key: currentKey, content: systemContent }),
      })
      if (!res.ok) throw new Error(await readError(res))
      await refreshAll(promptType, currentKey)
      setMessage('✓ 系统默认提示词已保存')
    } catch (error: any) {
      setMessage(`❌ ${error?.message || '保存系统默认失败'}`)
    }
    setIsLoading(false)
  }

  return (
    <div className="w-full space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-gray-600">类型</span>
            <select
              value={promptType}
              onChange={(e) => {
                const nextType = e.target.value
                setPromptType(nextType)
                const nextCatalogType =
                  catalog.find((item) => item.type === nextType) ||
                  TYPES.find((item) => item.id === nextType)
                const nextKey =
                  nextCatalogType?.items?.[0]?.key ||
                  nextCatalogType?.steps?.[0]?.key
                if (nextKey) setCurrentKey(nextKey)
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            >
              {TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-gray-600">步骤</span>
            <select
              value={currentKey}
              onChange={(e) => setCurrentKey(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            >
              {(currentType.items || currentType.steps || []).map((item: any) => (
                <option key={item.key || item.id} value={item.key || item.id}>
                  {item.title || item.label}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button
              onClick={() => void refreshAll(promptType, currentKey)}
              disabled={isLoading}
              className="w-full rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors lg:w-auto"
            >
              刷新
            </button>
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-base font-semibold text-gray-900">{title || '提示词管理'}</h3>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
            {sourceLabel}
          </span>
          {hasUserOverride && (
            <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700">
              已存在个人覆盖
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-gray-500">
          普通用户可维护自己的提示词覆盖；管理员额外可维护系统默认提示词。
        </p>
      </div>
      {message && <div className={`text-sm ${message.startsWith('✓') ? 'text-emerald-600' : 'text-red-600'}`}>{message}</div>}
      <div className="grid gap-4 2xl:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="mb-3 text-sm font-medium text-gray-700">当前生效内容</div>
          <textarea
            value={effectiveContent}
            readOnly
            rows={16}
            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm font-mono text-gray-700"
          />
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium text-gray-700">我的覆盖</div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={saveMyPrompt}
                disabled={isLoading}
                className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all"
              >
                保存我的覆盖
              </button>
              <button
                onClick={resetMyPrompt}
                disabled={isLoading}
                className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors"
              >
                恢复默认
              </button>
            </div>
          </div>
          <textarea
            value={userContent}
            onChange={(e) => setUserContent(e.target.value)}
            placeholder="未设置个人覆盖时，将自动使用系统默认提示词。"
            rows={16}
            className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm font-mono focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>
      </div>
      {user?.role === 'admin' && (
        <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-5">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-semibold text-violet-800">系统默认提示词</div>
              <div className="mt-1 text-xs text-violet-700">仅管理员可编辑；普通用户未设置覆盖时将使用这里的内容。</div>
            </div>
            <button
              onClick={saveSystemPrompt}
              disabled={isLoading}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50 transition-colors"
            >
              保存系统默认
            </button>
          </div>
          <textarea
            value={systemContent}
            onChange={(e) => setSystemContent(e.target.value)}
            rows={14}
            className="w-full rounded-lg border border-violet-200 bg-white px-4 py-3 text-sm font-mono focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
          />
        </div>
      )}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="mb-2 text-sm font-medium text-gray-700">说明</div>
        <textarea
          value={'优先级：我的覆盖 > 系统默认 > 文件兜底 > 代码兜底\n\n修改“我的覆盖”只影响当前账号；修改“系统默认”会影响所有未设置覆盖的用户。'}
          readOnly
          rows={4}
          className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600"
        />
      </div>
    </div>
  )
}

export default App

// History Panel - Show all generated reports
function HistoryTab() {
  const [subTab, setSubTab] = useState<'reading' | 'synthesis' | 'library_chat'>('reading')
  const [readingFiles, setReadingFiles] = useState<any[]>([])
  const [synthesisFiles, setSynthesisFiles] = useState<any[]>([])
  const [libraryChatFiles, setLibraryChatFiles] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [readingRes, synthRes, chatRes] = await Promise.all([
        fetch('/api/history/'),
        fetch('/api/history/synthesis/'),
        fetch('/api/history/library-chat/'),
      ])
      const readingData = await readingRes.json()
      const synthData = await synthRes.json()
      const chatData = await chatRes.json()
      setReadingFiles(readingData.all || [])
      setSynthesisFiles(synthData.all || [])
      setLibraryChatFiles(chatData.all || [])
    } catch (e) {
      console.error('Failed to load history:', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchAll()
  }, [])

  const handleDelete = async (filename: string, tab: string) => {
    if (!confirm(`确定删除 ${filename}？`)) return
    try {
      const res = await fetch(`/api/history/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      if (res.ok) {
        if (tab === 'synthesis') {
          setSynthesisFiles(files => files.filter(f => f.filename !== filename))
        } else if (tab === 'library_chat') {
          setLibraryChatFiles(files => files.filter(f => f.filename !== filename))
        } else {
          setReadingFiles(files => files.filter(f => f.filename !== filename))
        }
      }
    } catch (e) {
      console.error('Failed to delete:', e)
    }
  }

  const typeIcon: Record<string, string> = {
    '长文本精读': '📄',
    '七步精读': '📊',
    '四步精读': '📋',
    '文献筛选': '📑',
    'AI综述': '🤖',
    '全文翻译': '🌐',
    '文献助手': '💬',
    '其他': '📎',
  }

  const renderFileList = (files: any[], tab: string) => {
    if (files.length === 0) {
      return <div className="text-sm text-gray-400 py-8 text-center">暂无记录</div>
    }
    return (
      <div className="space-y-2">
        {files.map((file) => (
          <div
            key={file.filename}
            className="flex items-center justify-between rounded-lg bg-white border border-gray-200 px-4 py-3 hover:border-emerald-300 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-lg">{typeIcon[file.type] || '📎'}</span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-800 truncate">{file.filename}</div>
                <div className="text-xs text-gray-400 flex items-center gap-2">
                  <span>{file.type}</span>
                  <span>·</span>
                  <span>{file.size_human}</span>
                  <span>·</span>
                  <span>{file.modified}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <button
                type="button"
                onClick={() =>
                  openPreviewWithAuth(`/api/history/${encodeURIComponent(file.filename)}/preview`).catch(
                    (error) => alert(error.message),
                  )
                }
                className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
              >
                👁 预览
              </button>
              <button
                type="button"
                onClick={() =>
                  handleProtectedDownload(file.download_path || file.filename, file.filename).catch(
                    (error) => alert(error.message),
                  )
                }
                className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 transition-colors"
              >
                ⬇ 下载
              </button>
              <button
                onClick={() => handleDelete(file.filename, tab)}
                className="rounded-lg bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100 transition-colors"
              >
                🗑 删除
              </button>
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">📁 历史记录</h2>
      
      {/* Sub tabs */}
      <div className="flex gap-2 mb-6 border-b border-gray-200">
        <button
          onClick={() => setSubTab('reading')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            subTab === 'reading'
              ? 'border-emerald-600 text-emerald-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          📚 文献阅读 ({readingFiles.length})
        </button>
        <button
          onClick={() => setSubTab('synthesis')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            subTab === 'synthesis'
              ? 'border-emerald-600 text-emerald-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          🤖 AI综述 ({synthesisFiles.length})
        </button>
        <button
          onClick={() => setSubTab('library_chat')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            subTab === 'library_chat'
              ? 'border-emerald-600 text-emerald-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          💬 文献助手 ({libraryChatFiles.length})
        </button>
        <button
          onClick={fetchAll}
          className="ml-auto px-3 py-2 text-sm text-gray-500 hover:text-emerald-600 transition-colors"
          disabled={loading}
        >
          {loading ? '⏳' : '🔄'} 刷新
        </button>
      </div>

      {subTab === 'reading' && renderFileList(readingFiles, 'reading')}
      {subTab === 'synthesis' && renderFileList(synthesisFiles, 'synthesis')}
      {subTab === 'library_chat' && renderFileList(libraryChatFiles, 'library_chat')}
    </div>
  )
}

