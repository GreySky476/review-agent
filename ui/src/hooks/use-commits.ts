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
    staleTime: 2 * 60 * 1000,
  })
}

export function useTriggerCommitReview(projectId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      sha,
      mentionUser,
    }: {
      sha: string
      mentionUser: string
    }) => {
      const { data } = await api.post(
        `/projects/${projectId}/commits/${sha}/review`,
        { sha, mention_user: mentionUser },
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commits', projectId] })
    },
  })
}
