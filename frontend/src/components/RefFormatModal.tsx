import { useEffect, useMemo, useState } from 'react'

type Preset = {
  id: number
  name: string
  description: string | null
  format_name: string | null
  format_rules: string
  source_text: string | null
  entry_count: number
}

type AnalyzeResult = {
  format_name: string
  format_rules: string
  raw_references_count: number
  raw_references_sample: string[]
  source_text_truncated: string
}

type GenerateResult = {
  result_text: string
  entry_count: number
  artifact_id: number
  preset_id: number | null
  storage_path: string
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : '请求失败。'
    throw new Error(detail)
  }
  return data as T
}

export default function RefFormatModal({
  apiKey,
  entryIds,
  onClose,
}: {
  apiKey: string
  entryIds: string[]
  onClose: () => void
}) {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)
  const [presets, setPresets] = useState<Preset[]>([])
  const [sourceMode, setSourceMode] = useState<'preset' | 'new'>('new')
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(null)
  const [sampleMode, setSampleMode] = useState<'paste' | 'upload'>('paste')
  const [sampleText, setSampleText] = useState('')
  const [sampleFile, setSampleFile] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null)
  const [savePreset, setSavePreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const selectedPreset = useMemo(
    () => presets.find((item) => item.id === selectedPresetId) || null,
    [presets, selectedPresetId],
  )

  useEffect(() => {
    let cancelled = false
    fetch('/api/ref-format/presets')
      .then((response) => parseJsonOrThrow<Preset[]>(response))
      .then((data) => {
        if (cancelled) return
        setPresets(data)
        if (data.length > 0) {
          setSourceMode('preset')
          setSelectedPresetId(data[0].id)
        }
      })
      .catch(() => {
        if (!cancelled) setPresets([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  function goConfirm() {
    setError('')
    if (sourceMode === 'preset') {
      if (!selectedPreset) {
        setError('请选择一个预设。')
        return
      }
      setAnalysis({
        format_name: selectedPreset.format_name || selectedPreset.name,
        format_rules: selectedPreset.format_rules,
        raw_references_count: selectedPreset.entry_count,
        raw_references_sample: [],
        source_text_truncated: selectedPreset.source_text || '',
      })
      setSavePreset(false)
      setStep(3)
      return
    }
    setStep(2)
  }

  async function analyze() {
    setError('')
    if (!apiKey) {
      setError('请先设置 DeepSeek API Key。')
      return
    }
    if (sampleMode === 'paste' && sampleText.trim().length < 80) {
      setError('文本过短，请粘贴完整的参考文献列表。')
      return
    }
    if (sampleMode === 'upload' && !sampleFile) {
      setError('请选择一个示例文件。')
      return
    }

    setBusy(true)
    try {
      const form = new FormData()
      form.append('source', sampleMode)
      form.append('api_key', apiKey)
      if (sampleMode === 'paste') form.append('text', sampleText)
      if (sampleMode === 'upload' && sampleFile) form.append('file', sampleFile)
      const response = await fetch('/api/ref-format/analyze', { method: 'POST', body: form })
      const data = await parseJsonOrThrow<AnalyzeResult>(response)
      setAnalysis(data)
      setPresetName(data.format_name)
      setSavePreset(true)
      setStep(3)
    } catch (err) {
      setError(err instanceof Error ? err.message : '解析失败。')
    } finally {
      setBusy(false)
    }
  }

  async function generate() {
    if (!analysis) return
    setError('')
    setBusy(true)
    try {
      const response = await fetch('/api/ref-format/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format_rules: analysis.format_rules,
          format_name: analysis.format_name,
          entry_ids: entryIds,
          api_key: apiKey,
          save_preset: savePreset,
          preset_name: savePreset ? presetName : null,
          source_text: analysis.source_text_truncated,
          raw_references_count: analysis.raw_references_count,
        }),
      })
      const data = await parseJsonOrThrow<GenerateResult>(response)
      setResult(data)
      setStep(4)
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成失败。')
    } finally {
      setBusy(false)
    }
  }

  async function copyResult() {
    if (!result) return
    await navigator.clipboard.writeText(result.result_text)
  }

  function downloadResult() {
    if (!result) return
    const blob = new Blob([`# 参考文献目录\n\n${result.result_text}\n`], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'reference-format.md'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              {step === 4 ? '参考文献目录已生成' : `生成参考文献目录${step > 1 ? ` (${step}/3)` : ''}`}
            </h3>
            <p className="mt-1 text-xs text-gray-500">已选择 {entryIds.length} 篇文献</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg px-2 py-1 text-gray-500 hover:bg-gray-100">
            关闭
          </button>
        </div>

        <div className="max-h-[68vh] overflow-y-auto px-5 py-4">
          {error && <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}

          {step === 1 && (
            <div className="space-y-3">
              <div
                className={`w-full rounded-lg border p-4 ${sourceMode === 'preset' ? 'border-emerald-300 bg-emerald-50' : 'border-gray-200'}`}
              >
                <button
                  type="button"
                  onClick={() => setSourceMode('preset')}
                  className="w-full text-left font-medium text-gray-800"
                >
                  使用已存预设
                </button>
                <select
                  value={selectedPresetId || ''}
                  onChange={(event) => {
                    setSourceMode('preset')
                    setSelectedPresetId(Number(event.target.value))
                  }}
                  className="mt-3 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  disabled={presets.length === 0}
                >
                  {presets.length === 0 ? (
                    <option value="">暂无预设</option>
                  ) : (
                    presets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name} {preset.format_name ? `(${preset.format_name})` : ''}
                      </option>
                    ))
                  )}
                </select>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSourceMode('new')
                  setError('')
                  setStep(2)
                }}
                className={`w-full rounded-lg border p-4 text-left ${sourceMode === 'new' ? 'border-emerald-300 bg-emerald-50' : 'border-gray-200'}`}
              >
                <div className="font-medium text-gray-800">上传或粘贴新示例</div>
                <div className="mt-1 text-sm text-gray-500">支持 PDF / Markdown / TXT，或直接粘贴参考文献文本。</div>
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div className="inline-flex rounded-lg border border-gray-200 p-1 text-sm">
                <button
                  type="button"
                  onClick={() => setSampleMode('paste')}
                  className={`rounded-md px-3 py-1.5 ${sampleMode === 'paste' ? 'bg-emerald-600 text-white' : 'text-gray-600'}`}
                >
                  粘贴文本
                </button>
                <button
                  type="button"
                  onClick={() => setSampleMode('upload')}
                  className={`rounded-md px-3 py-1.5 ${sampleMode === 'upload' ? 'bg-emerald-600 text-white' : 'text-gray-600'}`}
                >
                  上传文件
                </button>
              </div>
              {sampleMode === 'paste' ? (
                <textarea
                  value={sampleText}
                  onChange={(event) => setSampleText(event.target.value)}
                  className="h-56 w-full rounded-lg border border-gray-200 p-3 text-sm text-gray-700 focus:border-emerald-400 focus:outline-none"
                  placeholder="直接粘贴参考文献列表..."
                />
              ) : (
                <input
                  type="file"
                  accept=".pdf,.md,.markdown,.txt"
                  onChange={(event) => setSampleFile(event.target.files?.[0] || null)}
                  className="block w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              )}
            </div>
          )}

          {step === 3 && analysis && (
            <div className="space-y-4">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="text-sm font-medium text-gray-800">格式：{analysis.format_name}</div>
                <div className="mt-1 text-sm text-gray-500">示例条目数：{analysis.raw_references_count || '未知'}</div>
                <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs text-gray-600">
                  {analysis.format_rules}
                </pre>
              </div>
              {sourceMode === 'new' && (
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input type="checkbox" checked={savePreset} onChange={(event) => setSavePreset(event.target.checked)} />
                  保存为预设
                </label>
              )}
              {savePreset && (
                <input
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  placeholder="预设名称"
                />
              )}
            </div>
          )}

          {step === 4 && result && (
            <textarea
              value={result.result_text}
              onChange={(event) => setResult({ ...result, result_text: event.target.value })}
              className="h-80 w-full rounded-lg border border-gray-200 p-3 font-mono text-sm text-gray-700 focus:border-emerald-400 focus:outline-none"
            />
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-4">
          {step === 1 && (
            <>
              <button type="button" onClick={onClose} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600">
                取消
              </button>
              <button type="button" onClick={goConfirm} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white">
                下一步
              </button>
            </>
          )}
          {step === 2 && (
            <>
              <button type="button" onClick={() => setStep(1)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600">
                上一步
              </button>
              <button type="button" onClick={() => void analyze()} disabled={busy} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {busy ? '解析中...' : '解析'}
              </button>
            </>
          )}
          {step === 3 && (
            <>
              <button type="button" onClick={() => setStep(sourceMode === 'preset' ? 1 : 2)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600">
                上一步
              </button>
              <button type="button" onClick={() => void generate()} disabled={busy} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {busy ? '生成中...' : '生成参考文献'}
              </button>
            </>
          )}
          {step === 4 && (
            <>
              <button type="button" onClick={() => void copyResult()} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600">
                复制
              </button>
              <button type="button" onClick={downloadResult} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600">
                下载 .md
              </button>
              <button type="button" onClick={onClose} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white">
                关闭
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
