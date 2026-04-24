import { useState, useEffect } from 'react'
import './index.css'

// Tab definitions
const TABS = [
  { id: 'filter', label: '文献筛选', icon: '□' },
  { id: 'long', label: '长文本精读', icon: '➤' },
  { id: 'quant', label: '七步精读', icon: '△' },
  { id: 'qual', label: '四步精读', icon: '◉' },
  { id: 'compare', label: '对比分析', icon: '⇄' },
  { id: 'prompts', label: '提示词管理', icon: '⚙' },
  { id: 'history', label: '历史记录', icon: '📁' },
]

function App() {
  const [activeTab, setActiveTab] = useState('filter')
  const [apiKey, setApiKey] = useState('')
  const [showKeyInput, setShowKeyInput] = useState(false)
  const [tempKey, setTempKey] = useState('')

  // Load key from localStorage on mount, or set default
  useEffect(() => {
    const saved = localStorage.getItem('deepseek_api_key')
    if (saved) {
      setApiKey(saved)
    } else {
      // Set default key
      const defaultKey = 'sk-b067838ed9de4569b41f8e98e96ded3c'
      setApiKey(defaultKey)
      localStorage.setItem('deepseek_api_key', defaultKey)
    }
  }, [])

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

  return (
    <div className={`min-h-screen bg-white text-gray-900 ${activeTab === 'compare' ? 'flex flex-col h-screen overflow-hidden' : ''}`}>
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
            {/* API Key Button */}
            <div className="relative">
              <button
                onClick={() => setShowKeyInput(!showKeyInput)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  apiKey
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <span>{apiKey ? '🔐' : '🔓'}</span>
                {apiKey ? 'Key 已设置' : '输入 Key'}
              </button>

              {showKeyInput && (
                <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-gray-200 bg-white p-4 shadow-lg z-50">
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
                  </div>
                </div>
              )}
            </div>

            <span className="px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
              DeepSeek ✓
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
              KIMI v3
            </span>
          </div>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="mx-auto max-w-7xl px-4">
          <div className="flex gap-1 overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
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
      <main className={activeTab === 'compare' ? 'flex-1 min-h-0 overflow-hidden' : 'mx-auto max-w-7xl px-4 py-6'}>
        {activeTab === 'filter' && <FilterTab apiKey={apiKey} />}
        {activeTab === 'long' && <LongTab apiKey={apiKey} />}
        {activeTab === 'quant' && <QuantTab apiKey={apiKey} />}
        {activeTab === 'qual' && <QualTab apiKey={apiKey} />}
        {activeTab === 'compare' && <CompareTab />}
        {activeTab === 'prompts' && <PromptsTab />}
        {activeTab === 'history' && <HistoryTab />}
      </main>
    </div>
  )
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
              <a href={`/api/download/${encodeURIComponent(downloadUrl)}`} 
                 download
                 className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100 transition-colors">
                <span>↓</span> 下载筛选报告 (Excel)
              </a>
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
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待上传...')
  const [logs, setLogs] = useState<string[]>([])
  const [preview, setPreview] = useState('')
  const [downloadUrl, setDownloadUrl] = useState('')

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

      const pollInterval = setInterval(async () => {
        const statusRes = await fetch(`/api/reading/task/${taskId}/status`)
        const statusData = await statusRes.json()
        setProgress(statusData.progress || 0)
        setStage(statusData.stage || '处理中...')
        if (statusData.logs) setLogs(statusData.logs)

        if (statusData.status === 'completed') {
          clearInterval(pollInterval)
          setIsRunning(false); setProgress(100); setStage('完成'); addLog('✅ 全部完成！')
          if (statusData.result?.preview) setPreview(statusData.result.preview)
          if (statusData.result?.output_path) setDownloadUrl(statusData.result.output_path)
        } else if (statusData.status === 'failed') {
          clearInterval(pollInterval)
          setIsRunning(false); setStage('错误'); addLog(`❌ ${statusData.error || '失败'}`)
        }
      }, 1000)
    } catch (error: any) {
      setIsRunning(false); setStage('错误'); addLog(`❌ ${error.message}`)
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
          <button onClick={() => setIsRunning(false)} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
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
              <a href={`/api/download/${encodeURIComponent(downloadUrl)}`} download className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100 transition-colors">
                ↓ 下载完整报告
              </a>
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
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待上传...')
  const [logs, setLogs] = useState<string[]>([])
  const [currentStep, setCurrentStep] = useState(0)

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

      const pollInterval = setInterval(async () => {
        const statusRes = await fetch(`/api/reading/task/${taskId}/status`)
        const statusData = await statusRes.json()
        setProgress(statusData.progress || 0)
        setStage(statusData.stage || '处理中...')
        if (statusData.logs) setLogs(statusData.logs)
        const stepNum = Math.min(7, Math.floor((statusData.progress || 0) / 15) + 1)
        setCurrentStep(stepNum)
        if (statusData.status === 'completed') {
          clearInterval(pollInterval); setIsRunning(false); setProgress(100); setStage('完成'); addLog('✅ 全部完成！'); setCurrentStep(7)
        } else if (statusData.status === 'failed') {
          clearInterval(pollInterval); setIsRunning(false); setStage('错误'); addLog(`❌ ${statusData.error || '失败'}`)
        }
      }, 1000)
    } catch (error: any) { setIsRunning(false); setStage('错误'); addLog(`❌ ${error.message}`) }
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
          <button onClick={() => setIsRunning(false)} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
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
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('等待上传...')
  const [logs, setLogs] = useState<string[]>([])
  const [currentStep, setCurrentStep] = useState(0)

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

      const pollInterval = setInterval(async () => {
        const statusRes = await fetch(`/api/reading/task/${taskId}/status`)
        const statusData = await statusRes.json()
        setProgress(statusData.progress || 0)
        setStage(statusData.stage || '处理中...')
        if (statusData.logs) setLogs(statusData.logs)
        const stepNum = Math.min(4, Math.floor((statusData.progress || 0) / 25) + 1)
        setCurrentStep(stepNum)
        if (statusData.status === 'completed') {
          clearInterval(pollInterval); setIsRunning(false); setProgress(100); setStage('完成'); addLog('✅ 全部完成！'); setCurrentStep(4)
        } else if (statusData.status === 'failed') {
          clearInterval(pollInterval); setIsRunning(false); setStage('错误'); addLog(`❌ ${statusData.error || '失败'}`)
        }
      }, 1000)
    } catch (error: any) { setIsRunning(false); setStage('错误'); addLog(`❌ ${error.message}`) }
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
          <button onClick={() => setIsRunning(false)} disabled={!isRunning} className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors">
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
              <a
                href={`/api/history/${encodeURIComponent(file.filename)}/preview`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
              >
                👁 预览
              </a>
              <a
                href={`/api/download/${encodeURIComponent(file.filename)}`}
                download
                className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 transition-colors"
              >
                ⬇ 下载
              </a>
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
function CompareTab() {
  const [mode, setMode] = useState<'long' | '7step' | '4step'>('long')

  const srcMap = {
    long: '/compare_long.html',
    '7step': '/compare_7step.html',
    '4step': '/compare_4step.html',
  }

  const modes = [
    { id: 'long' as const, label: '长文本精读', desc: '自由维度对比' },
    { id: '7step' as const, label: '七步法', desc: '定量实证对比' },
    { id: '4step' as const, label: '四步法', desc: '定性理论对比' },
  ]

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-48 bg-gray-900 text-white flex flex-col border-r border-gray-800">
        <div className="p-4 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300">对比分析</h3>
          <p className="text-xs text-gray-500 mt-1">选择对比模式</p>
        </div>
        <div className="flex-1 p-2 space-y-1">
          {modes.map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={`w-full text-left px-3 py-3 rounded-lg text-sm transition-all ${
                mode === m.id
                  ? 'bg-emerald-600 text-white shadow-lg'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              }`}
            >
              <div className="font-medium">{m.label}</div>
              <div className={`text-xs mt-0.5 ${mode === m.id ? 'text-emerald-200' : 'text-gray-600'}`}>
                {m.desc}
              </div>
            </button>
          ))}
        </div>
        <div className="p-3 border-t border-gray-800">
          <p className="text-xs text-gray-600">
            勾选文献后横向对比
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 bg-gray-100">
        <iframe
          key={mode}
          src={srcMap[mode]}
          className="w-full h-full border-0"
          title="文献对比分析"
        />
      </div>
    </div>
  )
}
