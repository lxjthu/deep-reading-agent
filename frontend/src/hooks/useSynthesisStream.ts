import { useState, useCallback, useRef } from 'react'

interface SynthesisParams {
  mode: string
  bib_entry_ids: string[]
  api_key: string
  selected_dimensions: string[]
}

export function useSynthesisStream() {
  const [content, setContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const start = useCallback(async (params: SynthesisParams) => {
    setIsStreaming(true)
    setContent('')
    setError(null)
    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/compare/synthesis-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: abortRef.current.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No response body')

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6)
            if (payload === '[DONE]') break
            try {
              const parsed = JSON.parse(payload)
              if (parsed.content) {
                setContent(prev => prev + parsed.content)
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setIsStreaming(false)
    }
  }, [])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const reset = useCallback(() => {
    setContent('')
    setError(null)
    setIsStreaming(false)
  }, [])

  return { content, isStreaming, error, start, abort, reset }
}
