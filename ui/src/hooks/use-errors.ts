import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface ReviewError {
  id: string
  project_id: string | null
  review_id: string | null
  error_type: string
  error_message: string
  error_detail: string | null
  recovered: boolean
  frequency: number
  create_time: string
}

interface ErrorsResponse {
  items: ReviewError[]
  total: number
  page: number
  page_size: number
}

export interface ErrorStatsItem {
  error_type: string
  count: number
  last_occurred: string | null
}

export function useErrors(params?: {
  project_id?: string
  error_type?: string
  start_date?: string
  end_date?: string
  page?: number
  pageSize?: number
}) {
  return useQuery<ErrorsResponse>({
    queryKey: ['errors', params],
    queryFn: async () => {
      const { data } = await api.get('/errors', { params })
      return data
    },
    staleTime: 30 * 1000,
    refetchInterval: 30_000,
  })
}

export function useErrorStats(params?: {
  start_date?: string
  end_date?: string
}) {
  return useQuery<ErrorStatsItem[]>({
    queryKey: ['errors', 'stats', params],
    queryFn: async () => {
      const { data } = await api.get('/errors/stats', { params })
      return data
    },
    staleTime: 60 * 1000,
  })
}
