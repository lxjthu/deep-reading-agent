import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './index.css'
import LibraryTab from './LibraryTab'
import { downloadWithAuth, openPreviewWithAuth } from './lib/download'
import { useAuthStore } from './store/auth'

// Tab definitions
const TABS = [
  { id: 'filter', label: '文献筛选', icon: '□' },
  { id: 'long', label: '长文本精读', icon: '➤' },
  { id: 'quant', label: '七步精读', icon: '△' },
  { id: 'qual', label: '四步精读', icon: '◉' },
  { id: 'compare-long', label: '长文本对比', icon: '⇄' },
  { id: 'compare-7step', label: '七步对比', icon: '⇄' },
  { id: 'compare-4step', label: '四步对比', icon: '⇄' },
  { id: 'library', label: '我的文献库', icon: '📚' },
  { id: 'prompts', label: '提示词管理', icon: '⚙' },
  { id: 'history', label: '历史记录', icon: '📁' },
]

const TAB_IDS = new Set(TABS.map((tab) => tab.id))

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

  useEffect(() => {
    const saved = localStorage.getItem('deepseek_api_key')
    if (saved) setApiKey(saved)
  }, [])

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
    if (tempKey.trim()) {
      const key = tempKey.trim()
      setApiKey(key)
      localStorage.setItem('deepseek_api_key', key)
      setShowKeyInput(false)
      setTempKey('')
    }
  }

  const handleDeleteKey = () => {
    setApiKey('')
    setTempKey('')
    localStorage.removeItem('deepseek_api_key')
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

  const isCompareTab =
    activeTab === 'compare-long' || activeTab === 'compare-7step' || activeTab === 'compare-4step'

  return (
    <div className={`${isCompareTab ? 'h-screen overflow-hidden' : 'min-h-screen'} bg-white text-gray-900 flex flex-col`}>
      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">❤️‍🔥</span>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Deep Reading Agent</h1>
              <p className="text-sm text-gray-500">学术论文深度精读系统</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
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
          <div className="mx-auto max-w-7xl px-4 py-4">
            <div className="max-w-md rounded-xl border border-emerald-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">DeepSeek API Key</h3>
              <input
                type="password"
                value={tempKey}
                onChange={(e) => setTempKey(e.target.value)}
                placeholder={apiKey ? '••••••••••••••••' : 'sk-...'}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-gray-400">保存在浏览器 localStorage，刷新后不丢失</p>
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
          <div className="mx-auto max-w-7xl px-4 py-3 text-sm text-red-700">
            <span className="font-semibold">⚠ 试用提醒：</span>
            <span>{user.warning_msg}</span>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="mx-auto max-w-7xl px-4">
          <div className="flex gap-1 overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
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
      <main className={isCompareTab ? 'flex flex-1 min-h-0 overflow-hidden' : 'mx-auto max-w-7xl flex-1 px-4 py-6'}>
        {activeTab === 'filter' && <FilterTab apiKey={apiKey} />}
        {activeTab === 'long' && <LongTab apiKey={apiKey} />}
        {activeTab === 'quant' && <QuantTab apiKey={apiKey} />}
        {activeTab === 'qual' && <QualTab apiKey={apiKey} />}
        {activeTab === 'compare-long' && <CompareTab title="长文本精读对比分析" src="/compare_long.html" />}
        {activeTab === 'compare-7step' && <CompareTab title="七步法对比分析" src="/compare_7step.html" />}
        {activeTab === 'compare-4step' && <CompareTab title="四步法对比分析" src="/compare_4step.html" />}
        {activeTab === 'library' && <LibraryTab />}
        {activeTab === 'prompts' && <PromptsTab />}
        {activeTab === 'history' && <HistoryTab />}
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
    const nextProgress = statusData.progress || 0
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

// Tab 0: 文献筛选
function FilterTab({ apiKey }: { apiKey: string }) {
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
          ...(apiKey ? { api_key: apiKey } : {}),
        }),
      })
      const startData = await startRes.json()
      const taskId = startData.task_id

      addLog(`✓ 任务已创建: ${taskId}`)

      // Step 3: Poll for progress
      const pollInterval = setInterval(async () => {
        const statusRes = await fetch(`/api/filter/task/${taskId}/status`)
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
      }, 1000)

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
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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
            disabled={isRunning || !apiKey}
            className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isRunning ? '处理中...' : apiKey ? '开始筛选' : '请先输入 API Key'}
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
      <div className="lg:col-span-2 space-y-4">
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
function LongTab({ apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [dims, setDims] = useState<string[]>(["研究问题", "理论框架", "识别策略"])
  const [customQ, setCustomQ] = useState('')
  const [extraction, _setExtraction] = useState('full')
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0])
  }

  const handleStart = async () => {
    if (!file) { alert('请先上传 PDF'); return }
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

      setProgress(10); setStage('解析 PDF...'); addLog('✓ 文件上传成功')

      const startRes = await fetch('/api/reading/long/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, analysis_dims: dims, custom_question: customQ || undefined, extraction_method: extraction, ...(apiKey ? { api_key: apiKey } : {}) })
      })
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
    }
  }

  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">★ 分析维度</h3>
          <div className="grid grid-cols-2 gap-2">
            {ALL_DIMS.map(dim => (
              <label key={dim} className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
                <input type="checkbox" checked={dims.includes(dim)} onChange={() => toggleDim(dim)} className="rounded text-emerald-600" />
                <span className="text-gray-700">{dim}</span>
              </label>
            ))}
          </div>
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
          <button onClick={handleStart} disabled={isRunning || !apiKey} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : apiKey ? '开始精读' : '请先输入 API Key'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>

      <div className="lg:col-span-2 space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">■ 处理进度</h3>
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
      </div>
    </div>
  )
}

// Tab 2: 七步精读
function QuantTab({ apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [extraction, setExtraction] = useState('full')
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
    if (!file) { alert('请先上传 PDF'); return }
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
      setProgress(10); setStage('解析 PDF...'); addLog('✓ 文件上传成功')

      const startRes = await fetch('/api/reading/quant/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, extraction_method: extraction, ...(apiKey ? { api_key: apiKey } : {}) })
      })
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) { setStage('错误'); addLog(`❌ ${error.message}`) }
  }
  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
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
          <button onClick={handleStart} disabled={isRunning || !apiKey} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : apiKey ? '开始精读' : '请先输入 API Key'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>
      <div className="lg:col-span-2 space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">△ 七步进度</h3>
          <div className="flex items-center gap-1 mb-4">
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
      </div>
    </div>
  )
}

// Tab 3: 四步精读
function QualTab({ apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [extraction, setExtraction] = useState('full')
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
    if (!file) { alert('请先上传 PDF'); return }
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
      setProgress(10); setStage('解析 PDF...'); addLog('✓ 文件上传成功')

      const startRes = await fetch('/api/reading/qual/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: uploadData.file_id, extraction_method: extraction, ...(apiKey ? { api_key: apiKey } : {}) })
      })
      const startData = await startRes.json()
      const taskId = startData.task_id
      addLog(`✓ 任务已创建: ${taskId}`)
      await startTrackingTask(taskId)
    } catch (error: any) { setStage('错误'); addLog(`❌ ${error.message}`) }
  }
  const addLog = (msg: string) => setLogs(prev => [...prev, msg])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">↗ 上传论文</h3>
          <label className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors">
            <input type="file" accept=".pdf" onChange={handleFileChange} className="hidden" />
            <span className="text-2xl mb-2">↗</span>
            <span className="text-sm text-gray-600">点击上传 PDF</span>
            {file && <span className="mt-2 text-xs text-emerald-600">✓ {file.name}</span>}
          </label>
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
          <button onClick={handleStart} disabled={isRunning || !apiKey} className="flex-1 rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
            {isRunning ? '分析中...' : apiKey ? '开始精读' : '请先输入 API Key'}
          </button>
          <button onClick={() => void cancelTask()} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
            停止
          </button>
        </div>
      </div>
      <div className="lg:col-span-2 space-y-4">
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">◉ 四步进度</h3>
          <div className="flex items-center gap-1 mb-4">
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
      </div>
    </div>
  )
}

// Tab 4: 提示词管理
function PromptsTab() {
  const [promptType, setPromptType] = useState('long')
  const [currentStep, setCurrentStep] = useState('overview')
  const [content, setContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('')

  const TYPES = [
    { id: 'quant', label: '七步精读', steps: [
      { id: 'step_1', label: 'Step 1: 研究概览' },
      { id: 'step_2', label: 'Step 2: 理论机制' },
      { id: 'step_3', label: 'Step 3: 数据说明' },
      { id: 'step_4', label: 'Step 4: 变量与度量' },
      { id: 'step_5', label: 'Step 5: 识别策略' },
      { id: 'step_6', label: 'Step 6: 结果呈现' },
      { id: 'step_7', label: 'Step 7: 批判性评估' },
    ]},
    { id: 'qual', label: '四步精读', steps: [
      { id: 'L1', label: 'L1: 背景与语境' },
      { id: 'L2', label: 'L2: 理论框架' },
      { id: 'L3', label: 'L3: 论证逻辑' },
      { id: 'L4', label: 'L4: 价值与启示' },
    ]},
    { id: 'long', label: '长文本精读', steps: [
      { id: 'overview', label: '研究问题' },
      { id: 'theory', label: '理论框架' },
      { id: 'methodology', label: '识别策略' },
      { id: 'data_source', label: '数据来源' },
      { id: 'variable_measurement', label: '变量度量' },
      { id: 'identification_assumptions', label: '识别假设' },
      { id: 'results', label: '统计结果' },
      { id: 'mechanism', label: '机制分析' },
      { id: 'robustness', label: '稳健性检验' },
      { id: 'external_validity', label: '外部有效性' },
      { id: 'contributions_limitations', label: '贡献与局限' },
      { id: 'writing_quality', label: '写作质量' },
      { id: 'custom', label: '自定义问题' },
    ]},
    { id: 'filter', label: '文献筛选', steps: [
      { id: 'explorer', label: '探索者模式' },
      { id: 'reviewer', label: '评审者模式' },
      { id: 'empiricist', label: '实证主义者' },
    ]},
  ]

  const currentType = TYPES.find(t => t.id === promptType) || TYPES[0]

  const handleLoad = async () => {
    setIsLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/prompts/?type=${promptType}&step=${currentStep}`)
      const data = await res.json()
      setContent(data.content || '')
      setMessage('✓ 加载成功')
    } catch (e) { setMessage('❌ 加载失败') }
    setIsLoading(false)
  }

  const handleSave = async () => {
    setIsLoading(true); setMessage('')
    try {
      const res = await fetch('/api/prompts/', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: promptType, step: currentStep, content })
      })
      if (res.ok) setMessage('✓ 保存成功')
      else setMessage('❌ 保存失败')
    } catch (e) { setMessage('❌ 保存失败') }
    setIsLoading(false)
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-5 flex gap-4 items-start">
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1.5">类型</label>
          <select value={promptType} onChange={(e) => { setPromptType(e.target.value); setCurrentStep(TYPES.find(t => t.id === e.target.value)?.steps[0].id || '') }} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none">
            {TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1.5">步骤</label>
          <select value={currentStep} onChange={(e) => setCurrentStep(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none">
            {currentType.steps.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="pt-6 flex gap-2">
          <button onClick={handleLoad} disabled={isLoading} className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors">加载</button>
          <button onClick={handleSave} disabled={isLoading} className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">保存</button>
        </div>
      </div>
      {message && <div className={`text-sm ${message.startsWith('✓') ? 'text-emerald-600' : 'text-red-600'}`}>{message}</div>}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="选择类型和步骤后点击「加载」查看提示词内容..."
          rows={20}
          className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm font-mono focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
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
    <div className="mx-auto max-w-7xl px-4 py-6">
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

// Tab: 对比分析
function CompareTab({ title, src }: { title: string; src: string }) {
  return (
    <div className="flex flex-1 min-h-0 flex-col bg-gray-100">
      <div className="shrink-0 border-b border-gray-200 bg-white px-6 py-4 shadow-sm">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        <p className="mt-1 text-sm text-gray-500">当前标签直接进入对应对比页面，内容区域按整个工作区展开。</p>
      </div>

      <div className="flex flex-1 min-h-0 bg-white p-2">
        <iframe
          src={src}
          className="block flex-1 min-h-0 w-full rounded-xl border border-gray-200 bg-white"
          title={title}
        />
      </div>
    </div>
  )
}
