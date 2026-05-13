import { useState, useEffect, useCallback } from 'react'

interface DimItem {
  id: string
  label: string
  content: string
}

interface StepData {
  label: string
  subQuestions: DimItem[]
}

interface Paper {
  id: string
  title: string
  authors: string[]
  year: number | null
  journal?: string
  doi?: string
  dimensions?: DimItem[]
  steps?: Record<string, StepData>
}

interface CompareData {
  mode: string
  label: string
  papers: Paper[]
}

export function useCompareData(mode: 'long' | 'quant' | 'qual') {
  const [data, setData] = useState<CompareData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/compare/reading-data?mode=${mode}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [mode])

  useEffect(() => { fetchData() }, [fetchData])

  return { data, papers: data?.papers ?? [], loading, error, refetch: fetchData }
}
