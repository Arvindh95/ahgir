import api from './api'

export interface Photo {
  image_id: string
  filename: string
  status: string
  face_count: number
  thumbnail_url: string
  download_url: string
  uploaded_at: string
}

export interface UploadResult {
  uploaded: Array<{
    image_id: string
    filename: string
    size_bytes: number
    status: string
  }>
  duplicates: Array<{
    filename: string
    reason: string
  }>
}

export interface PhotosResponse {
  photos: Photo[]
  total: number
  page: number
  limit: number
}

export const photoService = {
  async uploadPhotos(
    eventId: string,
    files: File[],
    onUploadProgress?: (progress: number) => void
  ): Promise<UploadResult> {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })

    const response = await api.post(`/events/${eventId}/photos`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onUploadProgress) {
          const pct = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          onUploadProgress(pct)
        }
      },
    })
    return response.data
  },

  async getPhotos(
    eventId: string,
    page: number = 1,
    limit: number = 50,
    status?: string
  ): Promise<PhotosResponse> {
    const params: any = { page, limit }
    if (status) {
      params.status = status
    }
    const response = await api.get(`/events/${eventId}/photos`, { params })
    return response.data
  },

  async deletePhoto(eventId: string, imageId: string): Promise<void> {
    await api.delete(`/events/${eventId}/photos/${imageId}`)
  },

  async bulkDeletePhotos(eventId: string, imageIds: string[]): Promise<{ deleted: number }> {
    const response = await api.post(`/events/${eventId}/photos/bulk-delete`, { image_ids: imageIds })
    return response.data
  },

  async downloadZip(eventId: string, imageIds: string[]): Promise<Blob> {
    const response = await api.post(`/events/${eventId}/photos/download-zip`, { image_ids: imageIds }, {
      responseType: 'blob',
    })
    return response.data
  },

  async downloadAllZip(eventId: string): Promise<Blob> {
    const response = await api.post(`/events/${eventId}/photos/download-all-zip`, {}, {
      responseType: 'blob',
    })
    return response.data
  },
}
