import { useQuery } from '@tanstack/react-query'
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
