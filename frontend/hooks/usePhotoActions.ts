import { useState } from 'react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface DownloadablePhoto {
  image_id: string
  download_url?: string
  filename?: string
}

export function usePhotoActions() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)

  const toggleSelect = (imageId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(imageId)) next.delete(imageId)
      else next.add(imageId)
      return next
    })
  }

  const selectAll = (allIds: string[]) => {
    if (selectedIds.size === allIds.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(allIds))
    }
  }

  const handleDownload = async (photo: DownloadablePhoto) => {
    if (!photo.download_url) return
    try {
      const res = await fetch(photo.download_url)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = photo.filename || `photo_${photo.image_id}.jpg`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      alert('Failed to download photo')
    }
  }

  const handleBulkDownload = async () => {
    if (selectedIds.size === 0) return
    setDownloading(true)
    try {
      const token = localStorage.getItem('event_token')
      const response = await fetch(`${API_URL}/download-zip`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ image_ids: Array.from(selectedIds) })
      })
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'photos.zip'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      alert('Failed to download photos')
    } finally {
      setDownloading(false)
    }
  }

  return {
    selectedIds,
    setSelectedIds,
    toggleSelect,
    selectAll,
    handleDownload,
    handleBulkDownload,
    downloading,
  }
}
