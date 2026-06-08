import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface DashboardStats {
  total_projects: number
  total_reviews_today: number
  average_score: number
  pending_errors: number
  finding_distribution: Record<string, number>
}

export interface TrendDataPoint {
  date: string
  avg_score: number
  total_reviews: number
  critical: number
  warning: number
  info: number
}

export function useDashboardStats() {
  return useQuery<DashboardStats>({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const { data } = await api.get('/dashboard/stats')
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useQualityTrends(params?: {
  project_id?: string
  period?: string
  start_date?: string
  end_date?: string
}) {
  return useQuery<{ items: TrendDataPoint[]; period: string }>({
    queryKey: ['dashboard', 'trends', params],
    queryFn: async () => {
      const { data } = await api.get('/dashboard/quality-trends', {
        params,
      })
      return data
    },
    staleTime: 10 * 60 * 1000,
  })
}
