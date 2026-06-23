import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface Commit {
  id: string
  sha: string
  author: string | null
  message: string | null
  branch: string | null
  pr_number: number | null
  is_reviewed: boolean
  review_id: string | null
  review_status: string | null
  review_score: number | null
  severity_breakdown: Record<string, number> | null
  create_time: string
}

interface CommitsResponse {
  items: Commit[]
  total: number
  page: number
  page_size: number
}

export function useCommits(
  projectId: string,
  params?: { branch?: string; author?: string; page?: number; pageSize?: number },
) {
  return useQuery<CommitsResponse>({
    queryKey: ['commits', projectId, params],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/commits`, { params })
      return data
    },
    enabled: !!projectId,
    staleTime: 30 * 1000,
  })
}

export function useTriggerCommitReview(projectId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      sha,
      force,
      skipLevels,
    }: {
      sha: string
      force?: boolean
      skipLevels?: string
    }) => {
      const { data } = await api.post(
        `/projects/${projectId}/commits/${sha}/review`,
        null,
        { params: { force: force ? 'true' : undefined, skip_levels: skipLevels || undefined } },
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commits', projectId] })
    },
  })
}
