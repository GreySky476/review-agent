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
  total_findings: number
  critical: number
  warning: number
  info: number
}

export interface EnterpriseDashboard {
  total_projects: number
  total_projects_change: number
  reviews_this_week: number
  reviews_week_change: number
  avg_score: number
  avg_score_change: number
  error_rate: number
  error_rate_change: number
  review_coverage: number
  reviews_by_status: Record<string, number>
  top_findings: { category: string; count: number }[]
}

export interface ProjectHealthItem {
  project_id: string
  project_name: string
  platform: string
  latest_score: number | null
  score_change: number | null
  health: 'active' | 'warning' | 'critical' | 'dormant'
  review_count_7d: number
  error_count_7d: number
  last_review_at: string | null
}

export interface RecentReviewItem {
  review_id: string
  project_name: string
  project_id: string
  pr_title: string
  branch: string | null
  status: string
  score: number | null
  head_sha: string
  duration_seconds: number | null
  created_at: string | null
}

export interface PlatformHealthItem {
  platform: string
  status: string
  latency_ms: number
  error_message: string | null
  last_checked_at: string | null
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

export function useEnterpriseStats() {
  return useQuery<EnterpriseDashboard>({
    queryKey: ['dashboard', 'enterprise'],
    queryFn: async () => {
      const { data } = await api.get('/dashboard/enterprise')
      return data
    },
    staleTime: 2 * 60 * 1000,
  })
}

export function useProjectHealth() {
  return useQuery<{ items: ProjectHealthItem[]; total: number }>({
    queryKey: ['dashboard', 'project-health'],
    queryFn: async () => {
      const { data } = await api.get('/dashboard/project-health')
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useRecentReviews(limit = 10) {
  return useQuery<{ items: RecentReviewItem[] }>({
    queryKey: ['dashboard', 'recent-reviews', limit],
    queryFn: async () => {
      const { data } = await api.get('/dashboard/recent-reviews', {
        params: { limit },
      })
      return data
    },
    staleTime: 60 * 1000,
  })
}

export function usePlatformHealth() {
  return useQuery<PlatformHealthItem[]>({
    queryKey: ['health', 'platforms'],
    queryFn: async () => {
      const { data } = await api.get('/health/platforms')
      return data
    },
    staleTime: 60 * 1000,
  })
}
