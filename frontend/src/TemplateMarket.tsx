import { useState, useEffect, useRef } from 'react'

interface Template {
  id: number
  name: string
  description: string
  category: string
  dim_count: number
}

interface TemplateDetail {
  id: number
  name: string
  description: string
  category: string
  dim_count: number
  group_config: { groups: { name: string; order: number }[] } | null
  _source?: 'preset' | 'user'
  dimensions: {
    id: number
    dim_key: string
    dim_name: string
    description: string | null
    default_question: string
    prompt_content: string
    group_name: string | null
    sort_order: number
  }[]
}

interface GeneratedResult {
  paper_analysis: {
    discipline: string
    research_type: string
    theory_tradition: string
    core_x: string
    core_y: string
    methodology: string
  }
  template: {
    name: string
    description: string
    category: string
    dimension_count: number
  }
  dimensions: {
    dim_name: string
    description: string
    default_question: string
    prompt_content: string
    group_name: string
    rationale: string
  }[]
}

interface ImportPreview {
  template_name: string
  description: string
  dimension_count: number
  dimensions: {
    dim_name: string
    description: string
    default_question: string
    prompt_content: string
    group_name: string | null
  }[]
}

const CATEGORIES = ['全部', '案例研究', '理论分析', '制度分析']

type PanelView = 'list' | 'detail' | 'ai' | 'import'

export default function TemplateMarket({ apiKey }: { apiKey: string }) {
  const [panel, setPanel] = useState<PanelView>('list')

  const [templates, setTemplates] = useState<Template[]>([])
  const [userSets, setUserSets] = useState<{ id: number; name: string; description: string | null; item_count: number; is_system: boolean; is_default: boolean; is_shared: boolean }[]>([])
  const [sharedSets, setSharedSets] = useState<{ id: number; name: string; description: string | null; item_count: number; owner_name: string }[]>([])
  const [selectedCategory, setSelectedCategory] = useState('全部')
  const [importingId, setImportingId] = useState<number | null>(null)
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [detailTarget, setDetailTarget] = useState<TemplateDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // AI generation state
  const [aiFile, setAiFile] = useState<File | null>(null)
  const [aiDimCount, setAiDimCount] = useState(12)
  const [aiStep, setAiStep] = useState<'upload' | 'config' | 'generating' | 'preview'>('upload')
  const [aiResult, setAiResult] = useState<GeneratedResult | null>(null)
  const [aiSaving, setAiSaving] = useState(false)

  // Document import state
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [importSaving, setImportSaving] = useState(false)

  const aiFileRef = useRef<HTMLInputElement>(null)
  const importFileRef = useRef<HTMLInputElement>(null)

  const loadTemplates = async () => {
    try {
      const url =
        selectedCategory === '全部'
          ? '/api/dimensions/templates'
          : `/api/dimensions/templates?category=${encodeURIComponent(selectedCategory)}`
      const res = await fetch(url)
      if (res.ok) setTemplates(await res.json())
    } catch (e) {
      console.error(e)
    }
  }

  const loadUserSets = async () => {
    try {
      const res = await fetch('/api/dimensions/sets')
      if (res.ok) {
        const data = await res.json()
        setUserSets(data.filter((s: any) => !s.is_system))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const loadSharedSets = async () => {
    try {
      const res = await fetch('/api/dimensions/shared')
      if (res.ok) setSharedSets(await res.json())
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    void loadTemplates()
    void loadUserSets()
    void loadSharedSets()
  }, [selectedCategory])

  const importTemplate = async (templateId: number) => {
    setImportingId(templateId)
    setMessage(null)
    try {
      const res = await fetch(`/api/dimensions/templates/${templateId}/import`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: `已导入「${data.name}」，共 ${data.dim_count} 个维度。前往「长文本精读」Tab 的维度集合下拉框即可使用。` })
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '导入失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportingId(null)
  }

  const showDetail = async (templateId: number) => {
    setDetailLoading(true)
    setDetailTarget(null)
    try {
      const res = await fetch(`/api/dimensions/templates/${templateId}`)
      if (res.ok) setDetailTarget(await res.json())
    } catch {
      console.error('load detail failed')
    }
    setDetailLoading(false)
    setPanel('detail')
  }

  const showUserSetDetail = async (setId: number, name: string, description: string | null) => {
    setDetailLoading(true)
    setDetailTarget(null)
    try {
      const res = await fetch(`/api/dimensions/sets/${setId}/items`)
      if (res.ok) {
        const items = await res.json()
        setDetailTarget({
          id: setId,
          name,
          description: description || '',
          category: '我的集合',
          dim_count: items.length,
          group_config: null,
          _source: 'user',
          dimensions: items.map((it: any) => ({
            id: it.id,
            dim_key: it.dim_key || '',
            dim_name: it.dim_name,
            description: it.description,
            default_question: it.default_question || '',
            prompt_content: it.prompt_content || '',
            group_name: it.group_name || null,
            sort_order: it.sort_order || 0,
          })),
        } as TemplateDetail)
      }
    } catch {
      console.error('load user set detail failed')
    }
    setDetailLoading(false)
    setPanel('detail')
  }

  const cloneUserSet = async (setId: number) => {
    setImportingId(setId)
    setMessage(null)
    try {
      const res = await fetch(`/api/dimensions/sets/${setId}/clone`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: `已复制为「${data.name}」` })
        void loadUserSets()
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '复制失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportingId(null)
  }

  const deleteSet = async (setId: number, name: string) => {
    if (!window.confirm(`确定删除「${name}」？仅未使用的自定义集合可删除。`)) return
    setImportingId(setId)
    setMessage(null)
    try {
      const res = await fetch(`/api/dimensions/sets/${setId}`, { method: 'DELETE' })
      if (res.ok) {
        setMessage({ type: 'ok', text: `已删除「${name}」` })
        void loadUserSets()
        if (detailTarget?._source === 'user' && detailTarget.id === setId) {
          setDetailTarget(null)
          setPanel('list')
        }
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '删除失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportingId(null)
  }

  const toggleShare = async (setId: number) => {
    setImportingId(setId)
    setMessage(null)
    try {
      const res = await fetch(`/api/dimensions/sets/${setId}/share`, { method: 'PATCH' })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: data.is_shared ? '已共享到模板市场' : '已取消共享' })
        void loadUserSets()
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '操作失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportingId(null)
  }

  const importSharedSet = async (setId: number) => {
    setImportingId(setId)
    setMessage(null)
    try {
      const res = await fetch(`/api/dimensions/shared/${setId}/import`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: `已导入「${data.name}」` })
        void loadUserSets()
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '导入失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportingId(null)
  }

  // AI generation
  const startAiGeneration = async () => {
    if (!aiFile) return
    setAiStep('generating')
    setMessage(null)
    try {
      const fd = new FormData()
      fd.append('file_upload', aiFile)
      fd.append('dim_count', String(aiDimCount))
      if (apiKey) fd.append('api_key', apiKey)
      const res = await fetch('/api/dimensions/generate', {
        method: 'POST',
        body: fd,
      })
      if (res.ok) {
        setAiResult(await res.json())
        setAiStep('preview')
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '生成失败' })
        setAiStep('config')
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
      setAiStep('config')
    }
  }

  const saveAiResult = async () => {
    if (!aiResult) return
    setAiSaving(true)
    try {
      const res = await fetch('/api/dimensions/generate/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: aiResult.template.name,
          description: aiResult.template.description,
          category: aiResult.template.category,
          dimensions: aiResult.dimensions,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: `已保存「${data.name}」，共 ${data.dim_count} 个维度` })
        setPanel('list')
        setAiResult(null)
        setAiFile(null)
        setAiStep('upload')
        void loadUserSets()
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '保存失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setAiSaving(false)
  }

  // Document import
  const previewDocumentImport = async () => {
    if (!importFile) return
    setMessage(null)
    try {
      const fd = new FormData()
      fd.append('file', importFile)
      const res = await fetch('/api/dimensions/import/preview', { method: 'POST', body: fd })
      if (res.ok) {
        setImportPreview(await res.json())
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '解析失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
  }

  const confirmDocumentImport = async () => {
    if (!importPreview) return
    setImportSaving(true)
    try {
      const res = await fetch('/api/dimensions/import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: importPreview.template_name,
          description: importPreview.description,
          dimensions: importPreview.dimensions,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setMessage({ type: 'ok', text: `已导入「${data.name}」，共 ${data.dim_count} 个维度。前往「长文本精读」Tab 的维度集合下拉框即可使用。` })
        setPanel('list')
        setImportPreview(null)
        setImportFile(null)
      } else {
        const err = await res.json().catch(() => null)
        setMessage({ type: 'err', text: err?.detail || '导入失败' })
      }
    } catch {
      setMessage({ type: 'err', text: '网络错误' })
    }
    setImportSaving(false)
  }

  const goBack = () => {
    setPanel('list')
    setDetailTarget(null)
    setAiResult(null)
    setAiFile(null)
    setAiStep('upload')
    setImportPreview(null)
    setImportFile(null)
  }

  // ---- Detail panel ----
  if (panel === 'detail' && detailTarget) {
    return (
      <div className="w-full space-y-4">
        <button onClick={goBack} className="text-sm text-emerald-600 hover:text-emerald-700">&larr; 返回模板市场</button>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">{detailTarget.name}</h3>
              <span className="text-xs text-gray-500">{detailTarget.category} &middot; {detailTarget.dim_count}个维度</span>
            </div>
            <div className="flex shrink-0 gap-2">
              <button onClick={() => detailTarget._source === 'user' ? cloneUserSet(detailTarget.id) : importTemplate(detailTarget.id)}
                disabled={importingId === detailTarget.id}
                className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50">
                {importingId === detailTarget.id ? '处理中...' : detailTarget._source === 'user' ? '复制集合' : '一键导入'}
              </button>
              {detailTarget._source === 'user' && (
                <>
                  <button onClick={() => toggleShare(detailTarget.id)} disabled={importingId === detailTarget.id}
                    className="rounded-lg border border-blue-200 bg-white px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50">
                    共享
                  </button>
                  <button onClick={() => deleteSet(detailTarget.id, detailTarget.name)} disabled={importingId === detailTarget.id}
                    className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50">
                    删除
                  </button>
                </>
              )}
            </div>
          </div>
          <p className="mt-2 text-sm text-gray-600">{detailTarget.description}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="mb-3 text-sm font-medium text-gray-700">维度列表（{detailTarget.dimensions.length}）</div>
          <div className="space-y-2">
            {(() => {
              if (!detailTarget.group_config?.groups?.length) {
                return detailTarget.dimensions.map((dim) => (
                  <div key={dim.id} className="flex items-start gap-3 rounded-lg border border-gray-100 bg-gray-50/50 p-3">
                    <span className="shrink-0 mt-0.5 h-2 w-2 rounded-full bg-emerald-400" />
                    <div>
                      <div className="text-sm font-medium text-gray-800">{dim.dim_name}</div>
                      {dim.description && <div className="text-xs text-gray-500 mt-0.5">{dim.description}</div>}
                    </div>
                  </div>
                ))
              }
              const gm: Record<string, typeof detailTarget.dimensions> = {}
              detailTarget.dimensions.forEach((d) => { const g = d.group_name || '__'; if (!gm[g]) gm[g] = []; gm[g].push(d) })
              return detailTarget.group_config.groups.map((group) => {
                const items = gm[group.name] || []
                if (!items.length) return null
                return (
                  <div key={group.name} className="rounded-lg border border-gray-200 p-3">
                    <div className="mb-2 text-xs font-medium text-gray-500">{group.name}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {items.map((dim) => (
                        <div key={dim.id} className="flex items-start gap-2 rounded-lg bg-gray-50/50 p-2">
                          <span className="shrink-0 mt-1 h-1.5 w-1.5 rounded-full bg-emerald-400" />
                          <div>
                            <div className="text-sm text-gray-800">{dim.dim_name}</div>
                            {dim.description && <div className="text-xs text-gray-500">{dim.description}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })
            })()}
          </div>
        </div>
        {message && <MsgBlock message={message} />}
      </div>
    )
  }

  // ---- AI Generation panel ----
  if (panel === 'ai') {
    return (
      <div className="w-full space-y-4">
        <button onClick={goBack} className="text-sm text-emerald-600 hover:text-emerald-700">&larr; 返回模板市场</button>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-5">
          <h3 className="text-base font-semibold text-gray-900">AI 生成专属模板</h3>
          <p className="mt-1 text-sm text-gray-600">上传一篇种子论文，自动生成定制化分析维度</p>
        </div>

        {aiStep === 'upload' && (
          <div className="space-y-4">
            <div className="rounded-xl border-2 border-dashed border-gray-300 bg-white p-8 text-center cursor-pointer hover:border-emerald-400 transition-colors"
              onClick={() => aiFileRef.current?.click()}>
              <input ref={aiFileRef} type="file" accept=".pdf,.md,.txt,.markdown" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) { setAiFile(f); setAiStep('config') } }} />
              <div className="text-3xl mb-2">📄</div>
              <div className="text-sm text-gray-600">点击选择论文文件</div>
              <div className="text-xs text-gray-400 mt-1">支持 PDF / Markdown / TXT</div>
            </div>
          </div>
        )}

        {aiStep === 'config' && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm text-gray-700">
              <span>已选择：</span>
              <span className="font-medium text-gray-900">{aiFile?.name}</span>
              <button onClick={() => { setAiFile(null); setAiStep('upload') }} className="text-xs text-red-500 hover:text-red-600">移除</button>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">期望维度数</label>
              <select value={aiDimCount} onChange={(e) => setAiDimCount(Number(e.target.value))}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
                {[8, 12, 16, 20].map((n) => <option key={n} value={n}>{n} 个</option>)}
              </select>
            </div>
            <button onClick={startAiGeneration}
              className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2 text-sm font-medium text-white hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">
              开始生成
            </button>
          </div>
        )}

        {aiStep === 'generating' && (
          <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent mx-auto" />
            <p className="mt-3 text-sm text-gray-600">正在分析论文并生成维度...</p>
            <p className="text-xs text-gray-400 mt-1">通常需要 30-60 秒</p>
          </div>
        )}

        {aiStep === 'preview' && aiResult && (
          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <h4 className="font-semibold text-gray-900">{aiResult.template.name}</h4>
              <p className="text-sm text-gray-600 mt-1">{aiResult.template.description}</p>
              <div className="mt-2 text-xs text-gray-500 flex flex-wrap gap-2">
                <span>{aiResult.paper_analysis.discipline}</span>
                <span>&middot;</span>
                <span>{aiResult.paper_analysis.research_type}</span>
                <span>&middot;</span>
                <span>{aiResult.dimensions.length} 个维度</span>
              </div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="mb-3 text-sm font-medium text-gray-700">生成维度预览</div>
              <div className="max-h-64 overflow-y-auto space-y-2">
                {aiResult.dimensions.map((dim, idx) => (
                  <div key={idx} className="rounded-lg border border-gray-100 bg-gray-50/50 p-3">
                    <div className="text-sm font-medium text-gray-800">{dim.dim_name}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{dim.description}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={saveAiResult} disabled={aiSaving}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                {aiSaving ? '保存中...' : '保存为我的集合'}
              </button>
              <button onClick={() => setAiStep('config')} className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200">
                重新生成
              </button>
            </div>
          </div>
        )}
        {message && <MsgBlock message={message} />}
      </div>
    )
  }

  // ---- Document Import panel ----
  if (panel === 'import') {
    return (
      <div className="w-full space-y-4">
        <button onClick={goBack} className="text-sm text-emerald-600 hover:text-emerald-700">&larr; 返回模板市场</button>
        <div className="rounded-xl border border-amber-200 bg-amber-50/30 p-5">
          <h3 className="text-base font-semibold text-gray-900">从文档导入</h3>
          <p className="mt-1 text-sm text-gray-600">上传 TXT / MD / JSON 格式的维度定义文档</p>
        </div>

        {!importPreview && (
          <div className="space-y-4">
            <div className="rounded-xl border-2 border-dashed border-gray-300 bg-white p-8 text-center cursor-pointer hover:border-amber-400 transition-colors"
              onClick={() => importFileRef.current?.click()}>
              <input ref={importFileRef} type="file" accept=".txt,.md,.json,.markdown" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) setImportFile(f) }} />
              <div className="text-3xl mb-2">📝</div>
              <div className="text-sm text-gray-600">点击选择维度文档</div>
              <div className="text-xs text-gray-400 mt-1">支持 .txt / .md / .json</div>
            </div>
            {importFile && (
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-700">已选择：<span className="font-medium">{importFile.name}</span></span>
                <button onClick={previewDocumentImport}
                  className="rounded-lg bg-amber-600 px-4 py-2 text-sm text-white hover:bg-amber-700">解析文档</button>
                <button onClick={() => setImportFile(null)} className="text-xs text-red-500">移除</button>
              </div>
            )}
            <div className="text-xs text-gray-500">
              提示：可从其他大模型生成提示词后导出为 txt/md，再导入此处
            </div>
          </div>
        )}

        {importPreview && (
          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <h4 className="font-semibold text-gray-900">{importPreview.template_name}</h4>
              <p className="text-sm text-gray-600 mt-1">{importPreview.description}</p>
              <div className="text-xs text-gray-500 mt-1">共 {importPreview.dimension_count} 个维度</div>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="mb-3 text-sm font-medium text-gray-700">维度预览</div>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {importPreview.dimensions.map((dim, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded-lg bg-gray-50/50 p-2 text-sm">
                    <span className="text-gray-800">{dim.dim_name}</span>
                    {dim.description && <span className="text-gray-400 text-xs truncate ml-2">{dim.description}</span>}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={confirmDocumentImport} disabled={importSaving}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                {importSaving ? '导入中...' : '确认导入'}
              </button>
              <button onClick={() => { setImportPreview(null); setImportFile(null) }} className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200">取消</button>
            </div>
          </div>
        )}
        {message && <MsgBlock message={message} />}
      </div>
    )
  }

  // ---- List panel (default) ----
  return (
    <div className="w-full space-y-4">
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button key={cat} onClick={() => setSelectedCategory(cat)}
            className={`rounded-full px-3 py-1 text-sm transition-colors ${selectedCategory === cat ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
            {cat}
          </button>
        ))}
      </div>

      {detailLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {templates.map((t) => (
          <div key={`t-${t.id}`} className="rounded-xl border border-gray-200 bg-white p-5 transition-shadow hover:shadow-md">
            <div>
              <h3 className="font-semibold text-gray-900">{t.name}</h3>
              <span className="text-xs text-gray-500">{t.category} &middot; {t.dim_count}个维度</span>
            </div>
            <p className="mt-2 text-sm text-gray-600 line-clamp-2">{t.description}</p>
            <div className="mt-3 flex gap-2">
              <button onClick={() => showDetail(t.id)} className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-200">查看详情</button>
              <button onClick={() => importTemplate(t.id)} disabled={importingId === t.id}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700 disabled:opacity-50">
                {importingId === t.id ? '导入中...' : '一键导入'}
              </button>
            </div>
          </div>
        ))}
        {userSets.map((s) => (
          <div key={`s-${s.id}`} className="rounded-xl border border-gray-200 bg-white p-5 transition-shadow hover:shadow-md">
            <div>
              <h3 className="font-semibold text-gray-900">
                {s.name}
                {s.is_shared && <span className="ml-2 inline-block rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">已共享</span>}
              </h3>
              <span className="text-xs text-gray-500">{s.item_count}个维度</span>
            </div>
            <p className="mt-2 text-sm text-gray-600 line-clamp-2">{s.description || ''}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={() => showUserSetDetail(s.id, s.name, s.description)} className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-200">查看详情</button>
              <button onClick={() => cloneUserSet(s.id)} disabled={importingId === s.id}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700 disabled:opacity-50">
                {importingId === s.id ? '处理中...' : '复制集合'}
              </button>
              <button onClick={() => toggleShare(s.id)} disabled={importingId === s.id}
                className={`rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50 ${s.is_shared ? 'border-blue-200 text-blue-600 hover:bg-blue-50' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
                {s.is_shared ? '取消共享' : '共享'}
              </button>
              {!s.is_system && (
                <button onClick={() => deleteSet(s.id, s.name)} disabled={importingId === s.id}
                  className="rounded-lg bg-white border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50">
                  删除
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {sharedSets.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-gray-700">来自其他用户的共享</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {sharedSets.map((s) => (
              <div key={`sh-${s.id}`} className="rounded-xl border border-blue-100 bg-blue-50/30 p-5 transition-shadow hover:shadow-md">
                <div>
                  <h3 className="font-semibold text-gray-900">{s.name}</h3>
                  <span className="text-xs text-gray-500">{s.item_count}个维度 &middot; 来自 {s.owner_name}</span>
                </div>
                <p className="mt-2 text-sm text-gray-600 line-clamp-2">{s.description || ''}</p>
                <div className="mt-3 flex gap-2">
                  <button onClick={() => importSharedSet(s.id)} disabled={importingId === s.id}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700 disabled:opacity-50">
                    {importingId === s.id ? '导入中...' : '一键导入'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/20 p-5 cursor-pointer hover:border-emerald-400 transition-colors"
          onClick={() => setPanel('ai')}>
          <div className="text-lg mb-1">🪄</div>
          <h3 className="font-semibold text-gray-900">AI 生成专属模板</h3>
          <p className="mt-1 text-sm text-gray-600">上传种子论文，自动生成定制化分析维度</p>
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50/20 p-5 cursor-pointer hover:border-amber-400 transition-colors"
          onClick={() => setPanel('import')}>
          <div className="text-lg mb-1">📝</div>
          <h3 className="font-semibold text-gray-900">从文档导入</h3>
          <p className="mt-1 text-sm text-gray-600">上传 TXT / MD / JSON 维度文档</p>
        </div>
      </div>

      {templates.length === 0 && userSets.length === 0 && !detailLoading && (
        <div className="py-8 text-center text-sm text-gray-400">暂无模板</div>
      )}
      {message && <MsgBlock message={message} />}
    </div>
  )
}

function MsgBlock({ message }: { message: { type: 'ok' | 'err'; text: string } }) {
  return (
    <div className={`rounded-lg px-4 py-3 text-sm ${message.type === 'ok' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
      {message.text}
    </div>
  )
}
