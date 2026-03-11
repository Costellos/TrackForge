import { api } from './client'

export interface FileTags {
  filename: string
  tags: Record<string, string>
  format: string
  duration_ms: number | null
}

export interface ReviewTagsResponse {
  request_id: string
  name: string
  artist: string | null
  files: FileTags[]
  auto_import_at: string | null
}

export interface FileTagEdit {
  filename: string
  tags: Record<string, string>
}

export async function getReviewTags(requestId: string): Promise<ReviewTagsResponse> {
  const res = await api.get<ReviewTagsResponse>(`/review/${requestId}/tags`)
  return res.data
}

export async function saveReviewTags(requestId: string, files: FileTagEdit[]): Promise<{ updated: number }> {
  const res = await api.post<{ updated: number }>(`/review/${requestId}/tags`, { files })
  return res.data
}

export async function approveReview(requestId: string): Promise<void> {
  await api.post(`/review/${requestId}/approve`)
}
