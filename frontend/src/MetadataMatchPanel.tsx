import { useState } from 'react'

type Candidate = {
  title: string
  authors: string[]
  year: number | null
  journal: string | null
  doi: string | null
  volume: string | null
  issue: string | null
  pages: string | null
  source: string
  score: number
}

type MatchResult = {
  candidates: Candidate[]
  extracted_metadata: Record<string, any>
  high_confidence_count: number
  medium_confidence_count: number
}

export default function MetadataMatchPanel({
  entryId,
  apiKey,
  onComplete,
}: {
  entryId: string
  apiKey: string
  onComplete?: () => void
}) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<MatchResult | null>(null)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState<number | null>(null)

  async function handleMatch() {
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const response = await fetch(`/api/library/entries/${encodeURIComponent(entryId)}/match-online`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiKey ? { api_key: apiKey } : {}),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '匹配失败')
      }

      const data = await response.json()
      setResult(data)
    } catch (err: any) {
      setError(err.message || '匹配失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleApply(index: number) {
    setApplying(index)
    try {
      const candidate = result?.candidates[index]
      if (!candidate) return

      const response = await fetch(`/api/library/entries/${encodeURIComponent(entryId)}/apply-match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '应用失败')
      }

      onComplete?.()
    } catch (err: any) {
      setError(err.message || '应用失败')
    } finally {
      setApplying(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          onClick={() => void handleMatch()}
          disabled={loading}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {loading ? '匹配中...' : '匹配'}
        </button>
        {result && (
          <span className="text-sm text-gray-500">
            找到 {result.candidates.length} 个候选
            （高置信度 {result.high_confidence_count}，中置信度 {result.medium_confidence_count}）
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {result && result.candidates.length > 0 && (
        <div className="space-y-3">
          {result.candidates.map((candidate, index) => (
            <div
              key={index}
              className={`rounded-xl border p-4 ${
                candidate.score >= 0.92
                  ? 'border-emerald-200 bg-emerald-50'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium text-gray-900">{candidate.title}</div>
                  <div className="mt-1 text-sm text-gray-600">
                    {candidate.authors.join(', ') || '未知作者'}
                  </div>
                  <div className="mt-1 text-sm text-gray-500">
                    {candidate.journal && <span>{candidate.journal}</span>}
                    {candidate.year && <span> · {candidate.year}</span>}
                    {candidate.doi && <span> · DOI: {candidate.doi}</span>}
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    来源: {candidate.source} · 置信度: {Math.round(candidate.score * 100)}%
                  </div>
                </div>
                <button
                  onClick={() => void handleApply(index)}
                  disabled={applying === index}
                  className="ml-4 rounded-lg bg-emerald-100 px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-200 disabled:opacity-50"
                >
                  {applying === index ? '应用中...' : '应用'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {result && result.candidates.length === 0 && (
        <div className="rounded-lg bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
          未找到匹配的候选元数据
        </div>
      )}
    </div>
  )
}
