import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface Comment {
  id: string
  review_id: string
  finding_id: string | null
  author: string
  content: string
  action: string | null
  create_time: string
}

export function useComments(reviewId: string) {
  return useQuery<Comment[]>({
    queryKey: ['comments', reviewId],
    queryFn: async () => {
      const { data } = await api.get(`/reviews/${reviewId}/comments`)
      return data
    },
    enabled: !!reviewId,
    staleTime: 10 * 1000,
  })
}

export function useCreateComment(reviewId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: {
      finding_id?: string
      author: string
      content: string
      action?: string
    }) => {
      const { data } = await api.post(
        `/reviews/${reviewId}/comments`,
        body,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', reviewId] })
    },
  })
}
