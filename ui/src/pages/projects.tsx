import { useState, useCallback, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
  type Project,
  type ProjectCreate,
} from '@/hooks/use-projects'
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

const platforms = [
  { value: '', label: '全部平台' },
  { value: 'github', label: 'GitHub' },
  { value: 'gitlab', label: 'GitLab' },
  { value: 'gitee', label: 'Gitee' },
]

export function ProjectsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [form, setForm] = useState<ProjectCreate>({
    name: '',
    platform: 'github',
    repo_url: '',
  })
  const [formError, setFormError] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, error, refetch } = useProjects({
    search: search || undefined,
    platform: platform || undefined,
    page,
  })

  const createProject = useCreateProject()
  const deleteProject = useDeleteProject()

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

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
        {/* Custom Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]"
          >
            <span className="flex-1 text-left">
              {platforms.find((p) => p.value === platform)?.label || '全部平台'}
            </span>
            <svg
              className={`h-4 w-4 text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {platforms.map((p) => (
                <button
                  key={p.value}
                  onClick={() => {
                    setPlatform(p.value)
                    setPage(1)
                    setDropdownOpen(false)
                  }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                    platform === p.value ? 'text-primary' : 'text-foreground'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          )}
        </div>
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
                    <WebhookStatus status={project.webhook_status || (project.webhook_enabled ? 'connected' : 'disconnected')} />
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
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setShowDeleteConfirm(project.id)
                        }}
                        className="ml-1 text-muted-more hover:text-error transition-colors"
                        title="删除项目"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
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

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg">
            <h2 className="text-lg font-bold text-foreground">删除项目</h2>
            <p className="mt-2 text-sm text-muted">
              确定要删除此项目吗？项目相关的评审记录和 PR 数据将被一并移除。此操作不可撤销。
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" size="md" onClick={() => setShowDeleteConfirm(null)}>
                取消
              </Button>
              <button
                onClick={async () => {
                  try {
                    await deleteProject.mutateAsync(showDeleteConfirm)
                    setShowDeleteConfirm(null)
                  } catch {
                    setShowDeleteConfirm(null)
                  }
                }}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-error px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
                disabled={deleteProject.isPending}
              >
                {deleteProject.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
