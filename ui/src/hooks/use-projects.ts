import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export interface Project {
  id: string
  name: string
  platform: 'github' | 'gitlab' | 'gitee'
  repo_url: string
  webhook_enabled: boolean
  webhook_status: 'connected' | 'never_connected' | 'inactive' | 'disconnected'
  webhook_last_event_at: string | null
  recent_review_time: string | null
  pr_count: number
  review_count: number
  latest_score: number | null
  status: 'active' | 'inactive' | 'dormant'
  active_days: number | null
  review_branches?: string[]
}

export interface ProjectCreate {
  name: string
  platform: 'github' | 'gitlab' | 'gitee'
  repo_url: string
}

interface ProjectsResponse {
  items: Project[]
  total: number
  page: number
  page_size: number
}

export function useProjects(params?: {
  platform?: string
  search?: string
  page?: number
  pageSize?: number
}) {
  return useQuery<ProjectsResponse>({
    queryKey: ['projects', params],
    queryFn: async () => {
      const { data } = await api.get('/projects', { params })
      return data
    },
    staleTime: 2 * 60 * 1000,
  })
}

export function useProject(id: string) {
  return useQuery<Project>({
    queryKey: ['project', id],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${id}`)
      return data
    },
    enabled: !!id,
    staleTime: 10 * 60 * 1000,
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: ProjectCreate) => {
      const { data } = await api.post('/projects', body)
      return data as Project
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.delete(`/projects/${id}`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useUpdateProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      ...body
    }: { id: string } & Partial<{ name: string; review_branches: string[] }>) => {
      const { data } = await api.patch(`/projects/${id}`, body)
      return data as Project & { id: string }
    },
    onSuccess: (result) => {
      queryClient.setQueryData(['project', result.id], result)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
