import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface PullRequest {
  pr_number: number
  title: string
  author: string | null
  state: 'open' | 'merged' | 'closed'
  is_merged: boolean
  review_status: string | null
  review_score: number | null
  findings_count: number
}

interface PullRequestsResponse {
  items: PullRequest[]
  total: number
  page: number
  page_size: number
}

export function usePullRequests(
  projectId: string,
  params?: { state?: string; page?: number; pageSize?: number },
) {
  return useQuery<PullRequestsResponse>({
    queryKey: ['pull-requests', projectId, params],
    queryFn: async () => {
      const { data } = await api.get(
        `/projects/${projectId}/pull-requests`,
        { params },
      )
      return data
    },
    enabled: !!projectId,
    staleTime: 60 * 1000,
  })
}

export function usePullRequestDetail(
  projectId: string,
  prNumber: number,
) {
  return useQuery({
    queryKey: ['pull-request', projectId, prNumber],
    queryFn: async () => {
      const { data } = await api.get(
        `/projects/${projectId}/pull-requests/${prNumber}`,
      )
      return data
    },
    enabled: !!projectId && !!prNumber,
    staleTime: 30 * 1000,
  })
}

export interface ReviewStats {
  total_reviews: number
  avg_score: number
  severity_distribution: Record<string, number>
  category_distribution: Record<string, number>
}

export function useReviewStats() {
  return useQuery<ReviewStats>({
    queryKey: ['review-stats'],
    queryFn: async () => {
      const { data } = await api.get('/reviews/stats')
      return data
    },
    staleTime: 60 * 1000,
  })
}

export interface ReviewDetail {
  id: string
  project_id: string
  project_name: string
  pr_number: number | null
  pr_title: string
  head_sha: string
  status: string
  score: number | null
  findings_count: number
  create_time: string | null
  update_time: string | null
  task_id: string | null
  statistics: {
    severity: Record<string, number>
    category: Record<string, number>
  }
  file_summary: Array<{
    file_path: string
    findings: number
    critical: number
    warning: number
    info: number
  }>
  findings: Array<{
    id: string
    file_path: string
    line_start: number | null
    line_end: number | null
    category: string
    severity: string
    title: string
    description: string
    suggestion: string
    rule_id: string | null
    is_valid: boolean
  }>
}

export function useReviewDetail(reviewId: string) {
  return useQuery<ReviewDetail>({
    queryKey: ['review-detail', reviewId],
    queryFn: async () => {
      const { data } = await api.get(`/reviews/${reviewId}`)
      return data
    },
    enabled: !!reviewId,
    staleTime: 30 * 1000,
  })
}

export function useTriggerPRReview(projectId: string, prNumber: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post(
        `/projects/${projectId}/pull-requests/${prNumber}/review`,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pull-request', projectId, prNumber] })
    },
  })
}
