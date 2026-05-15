import { useState, useEffect, useCallback, useRef } from 'react'

interface AnnotationData {
  id: string
  source_type: string
  selected_text: string | null
  note: string
  char_start: number | null
  char_end: number | null
  is_ai_generated: number
  color: string | null
  created_at: string | null
}

interface EditData {
  edited_content: string
  updated_at: string | null
}

interface DimItem {
  id: string
  label: string
  content: string
  reading_item_id?: number
  edit?: EditData
  annotations?: AnnotationData[]
  dim_set_name?: string
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
  const hasLoaded = useRef(false)

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/compare/reading-data?mode=${mode}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      hasLoaded.current = true
    } catch (e: any) {
      setError(e.message)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [mode])

  useEffect(() => { fetchData() }, [fetchData])

  const refetch = useCallback(() => fetchData(true), [fetchData])

  return { data, papers: data?.papers ?? [], loading, error, refetch }
}
