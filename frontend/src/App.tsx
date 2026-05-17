import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './index.css'
import LibraryTab from './LibraryTab'
import ReferenceTraceTab from './ReferenceTraceTab'
import TemplateMarket from './TemplateMarket'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'
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
  { id: 'library', label: '我的文献库', icon: '📚' },
  { id: 'references', label: '参考文献梳理', icon: '🔗' },
  { id: 'prompts', label: '提示词管理', icon: '⚙' },
  { id: 'history', label: '历史记录', icon: '📁' },
]

const TAB_IDS = new Set(TABS.map((tab) => tab.id))
const LEGACY_API_KEY_STORAGE = 'deepseek_api_key'

function getApiKeyStorageKey(username?: string | null) {
  const normalized = username?.trim()
  return normalized ? `deepseek_api_key:${normalized}` : null
}

function getInitialTab(pathname: string, search: string): string {
  if (pathname.startsWith('/workspace/library')) {
    return 'library'
  }
  const fromQuery = new URLSearchParams(search).get('tab') || ''
  if (fromQuery === 'compare') {
    return 'compare-long'
  }
  return TAB_IDS.has(fromQuery) && fromQuery !== 'library' ? fromQuery : 'filter'
}

function promptForApiKey(): string {
  const username = useAuthStore.getState().user?.username
  const storageKey = getApiKeyStorageKey(username)
  const existing = storageKey ? localStorage.getItem(storageKey) : ''
  if (existing) return existing
  const key = prompt('请输入 DeepSeek API Key（sk-开头）：')
  if (!key || !key.trim()) return ''
  const trimmed = key.trim()
  if (storageKey) {
    localStorage.setItem(storageKey, trimmed)
  }
  return trimmed
}

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [activeTab, setActiveTab] = useState(() => getInitialTab(location.pathname, location.search))
  const [apiKey, setApiKey] = useState('')
  const [showKeyInput, setShowKeyInput] = useState(false)
  const [tempKey, setTempKey] = useState('')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<Record<string, unknown> | null>(null)
  const [selectedImportFile, setSelectedImportFile] = useState<File | null>(null)

  useEffect(() => {
    const storageKey = getApiKeyStorageKey(user?.username)
    if (!storageKey) {
      setApiKey('')
      setTempKey('')
      return
    }
    const saved = localStorage.getItem(storageKey)
    setApiKey(saved || '')
    setTempKey('')
  }, [user?.username])

  useEffect(() => {
    setActiveTab(getInitialTab(location.pathname, location.search))
  }, [location.pathname, location.search])

  const handleTabChange = (tabId: string) => {
    setActiveTab(tabId)
    if (tabId === 'library') {
      if (location.pathname !== '/workspace/library') {
        navigate('/workspace/library')
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
    if (!storageKey || !tempKey.trim()) return
    const key = tempKey.trim()
    setApiKey(key)
    localStorage.setItem(storageKey, key)
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    setShowKeyInput(false)
    setTempKey('')
  }

  const handleDeleteKey = () => {
    const storageKey = getApiKeyStorageKey(user?.username)
    setApiKey('')
    setTempKey('')
    if (storageKey) {
      localStorage.removeItem(storageKey)
    }
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
    setShowKeyInput(false)
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
  }

  const handleImport = async (file: File) => {
    setImporting(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch('/api/data/import', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      })
      
      let data: any = {}
      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        const text = await response.text()
        data = { detail: text || `服务器返回非JSON响应（HTTP ${response.status}）` }
      }
      
      if (!response.ok) {
        throw new Error(data.detail || `导入失败（HTTP ${response.status}）`)
      }
      setImportResult(data)
      window.alert(`导入成功！已恢复 ${data.files_restored || 0} 个文件。页面即将刷新。`)
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
              DeepSeek ✓
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
              <h3 className="text-sm font-semibold text-gray-700 mb-2">DeepSeek API Key</h3>
              <input
                type="password"
                value={tempKey}
                onChange={(e) => setTempKey(e.target.value)}
                placeholder={apiKey ? '••••••••••••••••' : 'sk-...'}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-gray-400">仅保存在当前账号对应的浏览器 localStorage 中，不会与其他账号共用</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleSaveKey}
                  disabled={!tempKey.trim()}
                  className="flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300 transition-colors"
                >
                  保存
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
                导入将<span className="font-bold">清空您当前的所有数据</span>，并用导出包中的数据替换。此操作不可撤销。
              </p>
              <p>请选择 .dra 格式的导出包文件：</p>
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
            </div>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setImportDialogOpen(false)}
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
                    '确定要导入吗？这将清空您当前的所有数据并用导出包中的数据替换。此操作不可撤销。'
                  )
                  if (!confirmed) return
                  handleImport(selectedImportFile)
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
                  已恢复 {(importResult.files_restored as number) || 0} 个文件，缺失 {(importResult.files_missing as number) || 0} 个
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="mx-auto w-full max-w-[1800px] px-2 sm:px-3 lg:px-6 xl:px-8">
          <div className="no-scrollbar flex gap-1 overflow-x-auto py-1">
            {TABS.map((tab) => (
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
          {activeTab === 'filter' && <FilterTab apiKey={apiKey} />}
          {activeTab === 'long' && <LongTab apiKey={apiKey} />}
          {activeTab === 'quant' && <QuantTab apiKey={apiKey} />}
          {activeTab === 'qual' && <QualTab apiKey={apiKey} />}
          {activeTab === 'compare-long' && <CompareView mode="long" apiKey={apiKey || null} />}
          {activeTab === 'compare-7step' && <CompareView mode="quant" apiKey={apiKey || null} />}
          {activeTab === 'compare-4step' && <CompareView mode="qual" apiKey={apiKey || null} />}
          {activeTab === 'library' && <LibraryTab apiKey={apiKey} />}
          {activeTab === 'references' && <ReferenceTraceTab apiKey={apiKey} />}
          {activeTab === 'prompts' && <PromptsTab apiKey={apiKey} />}
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

function persistBatchId(batchId: string | null) {
  if (batchId) {
    localStorage.setItem('dra_batch_task_id', batchId)
  } else {
    localStorage.removeItem('dra_batch_task_id')
  }
}

function restoreBatchId(): string | null {
  return localStorage.getItem('dra_batch_task_id')
}

function useBatchReadingTracker() {
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
    persistBatchId(null)
    setState({
      batchId: null, total: 0, completed: 0, failed: 0, running: 0, queued: 0, tasks: [], isBatchRunning: false,
    })
  }

  const startBatchTracking = (batchId: string) => {
    persistBatchId(batchId)
    setState(prev => ({ ...prev, batchId, isBatchRunning: true }))
    const poll = async () => {
      try {
        const res = await fetch(`/api/reading/batch/${batchId}/status`)
        const data = await res.json()
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
          persistBatchId(null)
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
    const savedBatchId = restoreBatchId()
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
  const batchTracker = useBatchReadingTracker()
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
        await reloadItems(active.id)
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
      if (!res.ok) throw new Error((await res.json()).detail || '删除失败')
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

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
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
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if ((startData.skipped_count || 0) > 0) addLog(`ℹ ${startData.skipped_count} 个文件已有结果已跳过`)
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

          {dimSets.length > 1 && (
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
                    <a href={`/api/download/${encodeURIComponent(t.download_url)}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline ml-2">下载</a>
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
  const batchTracker = useBatchReadingTracker()
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

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
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
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if ((startData.skipped_count || 0) > 0) addLog(`ℹ ${startData.skipped_count} 个文件已有结果已跳过`)
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
                    <a href={`/api/download/${encodeURIComponent(t.download_url)}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline ml-2">下载</a>
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
  const batchTracker = useBatchReadingTracker()
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

  const handleBatchConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
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
      if (queuedCount === 0) throw new Error(`所有 ${fileIds.length} 个文件均启动失败${errorCount > 0 ? `（${errorCount} 个错误）` : ''}`)
      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${queuedCount} 篇排队)`)
      if (errorCount > 0) addLog(`⚠ ${errorCount} 个文件跳过`)
      if ((startData.skipped_count || 0) > 0) addLog(`ℹ ${startData.skipped_count} 个文件已有结果已跳过`)
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
                    <a href={`/api/download/${encodeURIComponent(t.download_url)}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline ml-2">下载</a>
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
  const [subTab, setSubTab] = useState<'reading' | 'synthesis'>('reading')
  const [readingFiles, setReadingFiles] = useState<any[]>([])
  const [synthesisFiles, setSynthesisFiles] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [readingRes, synthRes] = await Promise.all([
        fetch('/api/history/'),
        fetch('/api/history/synthesis/')
      ])
      const readingData = await readingRes.json()
      const synthData = await synthRes.json()
      setReadingFiles(readingData.all || [])
      setSynthesisFiles(synthData.all || [])
    } catch (e) {
      console.error('Failed to load history:', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchAll()
  }, [])

  const handleDelete = async (filename: string, isSynthesis: boolean) => {
    if (!confirm(`确定删除 ${filename}？`)) return
    try {
      const res = await fetch(`/api/history/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      if (res.ok) {
        if (isSynthesis) {
          setSynthesisFiles(files => files.filter(f => f.filename !== filename))
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
    '其他': '📎',
  }

  const renderFileList = (files: any[], isSynthesis: boolean) => {
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
                onClick={() => handleDelete(file.filename, isSynthesis)}
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
          onClick={fetchAll}
          className="ml-auto px-3 py-2 text-sm text-gray-500 hover:text-emerald-600 transition-colors"
          disabled={loading}
        >
          {loading ? '⏳' : '🔄'} 刷新
        </button>
      </div>

      {subTab === 'reading' && renderFileList(readingFiles, false)}
      {subTab === 'synthesis' && renderFileList(synthesisFiles, true)}
    </div>
  )
}


