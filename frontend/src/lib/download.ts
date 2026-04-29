function getFilenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const quotedMatch = disposition.match(/filename="([^"]+)"/i)
  if (quotedMatch?.[1]) {
    return quotedMatch[1]
  }
  const plainMatch = disposition.match(/filename=([^;]+)/i)
  return plainMatch?.[1]?.trim() || null
}

export async function downloadWithAuth(url: string, fallbackFilename?: string): Promise<void> {
  const response = await fetch(url)
  if (!response.ok) {
    let message = `下载失败（HTTP ${response.status}）`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') {
        message = data.detail
      }
    } catch {
      const text = await response.text().catch(() => '')
      if (text && !text.trim().startsWith('<')) {
        message = text.trim()
      }
    }
    throw new Error(message)
  }

  const blob = await response.blob()
  const filename =
    getFilenameFromDisposition(response.headers.get('content-disposition')) ||
    fallbackFilename ||
    'download'

  const blobUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(blobUrl)
}

export async function openPreviewWithAuth(url: string): Promise<void> {
  const response = await fetch(url)
  if (!response.ok) {
    let message = `预览失败（HTTP ${response.status}）`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') {
        message = data.detail
      }
    } catch {
      const text = await response.text().catch(() => '')
      if (text && !text.trim().startsWith('<')) {
        message = text.trim()
      }
    }
    throw new Error(message)
  }

  const blob = await response.blob()
  const blobUrl = URL.createObjectURL(blob)
  window.open(blobUrl, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000)
}
