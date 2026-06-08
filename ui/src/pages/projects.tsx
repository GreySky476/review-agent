import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjects, useCreateProject, type Project, type ProjectCreate } from '@/hooks/use-projects'
import {
  Skeleton,
  ErrorState,
  EmptyState,
  PlatformBadge,
  WebhookStatus,
  Button,
  Badge,
} from '@/components/ui/shared'
import { formatRelativeTime } from '@/lib/utils'

export function ProjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState<ProjectCreate>({
    name: '',
    platform: 'github',
    repo_url: '',
  })
  const [formError, setFormError] = useState('')

  const { data, isLoading, error, refetch } = useProjects({
    search: search || undefined,
    platform: platform || undefined,
    page,
  })

  const createProject = useCreateProject()

  const handleSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearch(e.target.value)
      setPage(1)
    },
    [],
  )

  const handleCreate = async () => {
    if (!form.name.trim()) { setFormError('请输入仓库名'); return }
    if (!form.repo_url.trim()) { setFormError('请输入仓库 URL'); return }
    setFormError('')
    try {
      await createProject.mutateAsync(form)
      setShowModal(false)
      setForm({ name: '', platform: 'github', repo_url: '' })
    } catch {
      setFormError('创建失败，请确认后端服务运行中')
    }
  }

  if (error) {
    return <ErrorState message="项目列表加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">项目</h1>
        <Button variant="primary" size="md" onClick={() => setShowModal(true)}>
          + 添加项目
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <input
            type="text"
            placeholder="🔍 搜索仓库名..."
            value={search}
            onChange={handleSearch}
            className="w-full rounded-md border border-border bg-surface px-4 py-2 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <select
          value={platform}
          onChange={(e) => {
            setPlatform(e.target.value)
            setPage(1)
          }}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
        >
          <option value="">全部平台</option>
          <option value="github">GitHub</option>
          <option value="gitlab">GitLab</option>
          <option value="gitee">Gitee</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-muted-more">
              <th className="px-4 py-3 font-medium">仓库名</th>
              <th className="px-4 py-3 font-medium">平台</th>
              <th className="px-4 py-3 font-medium">Webhook</th>
              <th className="px-4 py-3 font-medium">最近评审</th>
              <th className="px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <td key={j} className="px-4 py-4">
                      <Skeleton className="h-4 w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : !data?.items?.length ? (
              <tr>
                <td colSpan={5} className="px-4 py-12">
                  <EmptyState
                    title="还没有接入仓库"
                    description="添加第一个项目开始使用 AI 代码评审"
                    action={
                      <Button variant="primary" size="sm" onClick={() => setShowModal(true)}>
                        添加项目
                      </Button>
                    }
                  />
                </td>
              </tr>
            ) : (
              data.items.map((project: Project) => (
                <tr
                  key={project.id}
                  className="border-b border-border/50 transition-colors hover:bg-surface-hover/50 cursor-pointer"
                  onClick={() => navigate(`/projects/${project.id}`)}
                >
                  <td className="px-4 py-4 font-medium text-foreground">
                    {project.name}
                  </td>
                  <td className="px-4 py-4">
                    <PlatformBadge
                      platform={project.platform as 'github' | 'gitlab' | 'gitee'}
                    />
                  </td>
                  <td className="px-4 py-4">
                    {project.webhook_enabled ? (
                      <WebhookStatus status="connected" />
                    ) : (
                      <WebhookStatus status="disconnected" />
                    )}
                  </td>
                  <td className="px-4 py-4 text-muted">
                    {project.recent_review_time
                      ? formatRelativeTime(project.recent_review_time)
                      : '-'}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      <Badge variant="info">{project.pr_count} PR</Badge>
                      <Badge variant="default">{project.review_count} 评审</Badge>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>
            第 {data.page} 页，共 {Math.ceil(data.total / data.page_size)} 页
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}

      {/* Create Project Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg">
            <h2 className="text-lg font-bold text-foreground">添加项目</h2>
            <p className="mt-1 text-sm text-muted">注册一个代码仓库到系统</p>

            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">仓库名 *</label>
                <input
                  type="text"
                  placeholder="my-project"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1">平台 *</label>
                <select
                  value={form.platform}
                  onChange={(e) => setForm({ ...form, platform: e.target.value as ProjectCreate['platform'] })}
                  className="w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  <option value="github">GitHub</option>
                  <option value="gitlab">GitLab</option>
                  <option value="gitee">Gitee</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1">仓库 URL *</label>
                <input
                  type="text"
                  placeholder="https://github.com/org/repo"
                  value={form.repo_url}
                  onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
                  className="w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none"
                />
              </div>

              {formError && (
                <p className="text-sm text-error">{formError}</p>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => { setShowModal(false); setFormError('') }}
                >
                  取消
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  onClick={handleCreate}
                  disabled={createProject.isPending}
                >
                  {createProject.isPending ? '创建中...' : '确认创建'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
