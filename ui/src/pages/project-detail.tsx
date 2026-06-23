import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useProject } from '@/hooks/use-projects'
import { usePullRequests, useProjectReviews } from '@/hooks/use-reviews'
import { useCommits, useTriggerCommitReview } from '@/hooks/use-commits'
import { useQualityTrends } from '@/hooks/use-dashboard'
import { useUpdateProject } from '@/hooks/use-projects'
import { api } from '@/lib/api-client'
import {
  Skeleton,
  ErrorState,
  EmptyState,
  Badge,
  PlatformBadge,
  WebhookStatus,
  Button,
} from '@/components/ui/shared'
import { cn } from '@/lib/utils'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

type TabId = 'prs' | 'commits' | 'reviews' | 'quality' | 'webhook'

const tabs: { id: TabId; label: string }[] = [
  { id: 'prs', label: 'PR 列表' },
  { id: 'commits', label: '提交' },
  { id: 'reviews', label: '评审记录' },
  { id: 'quality', label: '质量趋势' },
  { id: 'webhook', label: 'Webhook' },
]

/* ── Review Status Badge ────────────────────────────────── */
function ReviewStatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="default">等待</Badge>
  const config: Record<string, { variant: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
    completed: { variant: 'success', label: '已完成' },
    pending: { variant: 'warning', label: '等待中' },
    running: { variant: 'info', label: '进行中' },
    failed: { variant: 'error', label: '失败' },
    completed_with_errors: { variant: 'warning', label: '已完成（有异常）' },
  }
  const cfg = config[status]
  return cfg ? <Badge variant={cfg.variant}>{cfg.label}</Badge> : null
}

/* ── PR State Badge ─────────────────────────────────────── */
function PRStateBadge({ state, isMerged }: { state: string; isMerged: boolean }) {
  if (isMerged) return <Badge variant="purple">Merged</Badge>
  if (state === 'open') return <Badge variant="success">Open</Badge>
  return <Badge variant="default">Closed</Badge>
}

/* ── Score Bar ────────────────────────────────────────────── */
function ScoreBar({ score }: { score: number }) {
  const color = score >= 90 ? 'bg-success' : score >= 70 ? 'bg-warning' : 'bg-error'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-stone-200">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-sm font-medium${color.replace('bg-', ' text-')}`}>{score}</span>
    </div>
  )
}

function SeverityBadges({ breakdown }: { breakdown: Record<string, number> | null }) {
  if (!breakdown || Object.keys(breakdown).length === 0) return <span className="text-xs text-muted">-</span>
  const items = [
    { key: 'critical', label: 'C', color: 'bg-error text-white' },
    { key: 'warning', label: 'W', color: 'bg-warning text-white' },
    { key: 'info', label: 'I', color: 'bg-info text-white' },
  ]
  return (
    <div className="flex items-center gap-1.5">
      {items.map(({ key, label, color }) => {
        const count = breakdown[key] ?? 0
        if (count === 0) return null
        return (
          <span key={key} className={`inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] font-medium ${color}`}>
            {label} {count}
          </span>
        )
      })}
    </div>
  )
}

/* ── Webhook Events Tab ──────────────────────────────────── */
function WebhookEventsTab({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['webhook-events', projectId, page],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/webhook-events`, { params: { page } })
      return data as { items: any[]; total: number; page: number; page_size: number }
    },
    enabled: !!projectId,
    staleTime: 10 * 1000,
  })

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-muted-more">
              <th className="px-4 py-3 font-medium">时间</th>
              <th className="px-4 py-3 font-medium">事件 ID</th>
              <th className="px-4 py-3 font-medium">动作</th>
              <th className="px-4 py-3 font-medium">PR</th>
              <th className="px-4 py-3 font-medium">已处理</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <td key={j} className="px-4 py-4"><Skeleton className="h-4 w-20" /></td>
                  ))}
                </tr>
              ))
            ) : !data?.items?.length ? (
              <tr>
                <td colSpan={5} className="px-4 py-12">
                  <EmptyState title="暂无 Webhook 事件" description="接入 Webhook 后事件将自动记录" />
                </td>
              </tr>
            ) : (
              data.items.map((evt: any) => (
                <tr key={evt.id} className="border-b border-border/50 text-muted hover:bg-surface-hover/50">
                  <td className="px-4 py-4 text-xs">
                    {evt.create_time ? new Date(evt.create_time).toLocaleString('zh-CN') : '-'}
                  </td>
                  <td className="px-4 py-4 font-mono text-xs text-foreground">{evt.event_id?.slice(0, 16)}...</td>
                  <td className="px-4 py-4">
                    <Badge variant={
                      evt.action === 'opened' ? 'success' :
                      evt.action === 'synchronize' ? 'info' :
                      evt.action === 'closed' ? 'default' : 'warning'
                    }>
                      {evt.action}
                    </Badge>
                  </td>
                  <td className="px-4 py-4 font-mono text-xs text-primary">#{evt.pr_number}</td>
                  <td className="px-4 py-4">
                    <Badge variant={evt.is_processed ? 'success' : 'warning'}>
                      {evt.is_processed ? '已处理' : '待处理'}
                    </Badge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>第 {data.page} 页，共 {Math.ceil(data.total / data.page_size)} 页</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
            <Button variant="secondary" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage((p) => p + 1)}>下一页</Button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── 评审记录 Tab ──────────────────────────────────────────── */
const reviewStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'completed', label: '已完成' },
  { value: 'completed_with_errors', label: '已完成（有异常）' },
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '进行中' },
  { value: 'failed', label: '失败' },
]

const reviewStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'info' | 'error' }> = {
  completed: { label: '已完成', variant: 'success' },
  pending: { label: '等待中', variant: 'warning' },
  running: { label: '进行中', variant: 'info' },
  failed: { label: '失败', variant: 'error' },
  completed_with_errors: { label: '已完成（有异常）', variant: 'warning' },
}

function ReviewsTabContent({
  projectId,
  data,
  isLoading,
  status,
  onStatusChange,
  page,
  onPageChange,
}: {
  projectId: string
  data: { items: any[]; total: number; page: number; page_size: number } | undefined
  isLoading: boolean
  status: string
  onStatusChange: (s: string) => void
  page: number
  onPageChange: (p: number) => void
}) {
  const navigate = useNavigate()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">总评审数</div>
          <div className="mt-1 text-2xl font-bold text-foreground">{data?.total ?? '-'}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">当前页</div>
          <div className="mt-1 text-2xl font-bold text-foreground">{data?.items?.length ?? 0} 条</div>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-4">
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]"
          >
            <span className="flex-1 text-left">
              {reviewStatusOptions.find((o) => o.value === status)?.label || '全部状态'}
            </span>
            <svg className={`h-4 w-4 text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {reviewStatusOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => { onStatusChange(opt.value); setDropdownOpen(false) }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                    status === opt.value ? 'text-primary' : 'text-foreground'
                  }`}
                >
                  {opt.label}
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
              <th className="px-4 py-3 font-medium">类型</th>
              <th className="px-4 py-3 font-medium">标题</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">评分</th>
              <th className="px-4 py-3 font-medium">严重性</th>
              <th className="px-4 py-3 font-medium">耗时</th>
              <th className="px-4 py-3 font-medium">时间</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="px-4 py-4"><Skeleton className="h-4 w-20" /></td>
                  ))}
                </tr>
              ))
            ) : !data?.items?.length ? (
              <tr>
                <td colSpan={7} className="px-4 py-12">
                  <EmptyState title="暂无评审记录" description="完成代码评审后将在此展示" />
                </td>
              </tr>
            ) : (
              data.items.map((review: any) => {
                const cfg = reviewStatusConfig[review.status] || { label: review.status, variant: 'default' as const }
                return (
                  <tr
                    key={review.id}
                    className="border-b border-border/50 transition-colors hover:bg-surface-hover/50 cursor-pointer"
                    onClick={() => navigate(`/projects/${projectId}/reviews/${review.id}`)}
                  >
                    <td className="px-4 py-4">
                      {review.pr_number != null
                        ? <span className="text-primary font-mono text-xs">PR #{review.pr_number}</span>
                        : <span className="font-mono text-xs text-muted">{review.head_sha?.slice(0, 8) || '-'}</span>}
                    </td>
                    <td className="max-w-xs truncate px-4 py-4 text-foreground" title={review.pr_title}>
                      {review.pr_number != null
                        ? <><span className="text-primary">#{review.pr_number}</span> {review.pr_title}</>
                        : <span className="text-muted">{review.pr_title || '-'}</span>}
                    </td>
                    <td className="px-4 py-4"><Badge variant={cfg.variant}>{cfg.label}</Badge></td>
                    <td className="px-4 py-4">
                      {review.score != null ? <ScoreBar score={review.score} /> : <span className="text-muted">-</span>}
                    </td>
                    <td className="px-4 py-4">
                      <SeverityBadges breakdown={review.severity_breakdown} />
                    </td>
                    <td className="px-4 py-4 text-xs text-muted">
                      {review.duration_seconds != null ? `${review.duration_seconds}s` : '-'}
                    </td>
                    <td className="px-4 py-4 text-xs text-muted">
                      {review.create_time ? new Date(review.create_time).toLocaleString('zh-CN') : '-'}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>第 {data.page} 页，共 {Math.ceil(data.total / data.page_size)} 页</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>上一页</Button>
            <Button variant="secondary" size="sm" disabled={page * data.page_size >= data.total} onClick={() => onPageChange(page + 1)}>下一页</Button>
          </div>
        </div>
      )}
    </div>
  )
}

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = (searchParams.get('tab') as TabId) || 'prs'
  const [activeTab, setActiveTab] = useState<TabId>(
    ['prs', 'commits', 'reviews', 'quality'].includes(tabFromUrl) ? tabFromUrl : 'prs',
  )
  const [prPage, setPrPage] = useState(1)

  const { data: project, isLoading: projectLoading, error: projectError, refetch: refetchProject } = useProject(id!)
  const { data: prs, isLoading: prsLoading } = usePullRequests(id!, { page: prPage })
  const { data: trends, isLoading: trendsLoading } = useQualityTrends({
    project_id: id,
  })
  const [commitPage, setCommitPage] = useState(1)
  const { data: commitsData, isLoading: commitsLoading } = useCommits(id!, {
    page: commitPage,
  })
  const triggerReview = useTriggerCommitReview(id!)
  const [triggeredSha, setTriggeredSha] = useState<string | null>(null)
  const [triggerErrorSha, setTriggerErrorSha] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [copied, setCopied] = useState(false)
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(null)
  const [reviewBranchesInput, setReviewBranchesInput] = useState<string>('*')
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)
  const [activeSettingsTab, setActiveSettingsTab] = useState<string>('basic')
  const updateProject = useUpdateProject()
  const queryClient = useQueryClient()
  const [reviewsStatus, setReviewsStatus] = useState('')
  const [reviewsPage, setReviewsPage] = useState(1)
  const { data: projectReviews, isLoading: reviewsLoading } = useProjectReviews(id!, {
    status: reviewsStatus || undefined,
    page: reviewsPage,
  })

  // 当 project.review_branches 变化时同步到输入框
  useEffect(() => {
    if (project?.review_branches) {
      setReviewBranchesInput(project.review_branches.join(', '))
    } else if (project) {
      setReviewBranchesInput('*')
    }
  }, [project?.review_branches, project?.id])
  const testWebhook = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/projects/${id}/webhook/test`)
      return data as { found: boolean; status?: string; error?: string; ping_sent?: boolean }
    },
    onSuccess: (result) => {
      if (result.found) {
        setWebhookTestResult(`已连接${result.ping_sent ? '（测试 Ping 已发送）' : ''}`)
        queryClient.invalidateQueries({ queryKey: ['project', id] })
      } else {
        setWebhookTestResult(result.error === 'project_not_found' ? '项目不存在' : '未检测到 Webhook 配置')
      }
    },
    onError: () => setWebhookTestResult('连接测试失败'),
  })

  if (projectError) {
    return <ErrorState message="项目加载失败" onRetry={refetchProject} />
  }

  if (projectLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-6 w-96" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (!project) {
    return <ErrorState message="项目不存在" />
  }

  return (
    <div className="space-y-6">
      {/* Project Header */}
      <div>
        <div className="flex items-center justify-between">
          <div>
            <button
              onClick={() => navigate('/projects')}
              className="mb-2 text-sm text-muted hover:text-foreground"
            >
              ← 返回项目列表
            </button>
            <h1 className="text-2xl font-bold text-foreground">{project.name}</h1>
          </div>
          <Button variant="secondary" size="sm" onClick={async () => {
            setSaveSuccess(null)
            // 先刷新项目数据确保拿到最新配置
            const { data: fresh } = await refetchProject()
            const branches = fresh?.review_branches
            setReviewBranchesInput(branches?.join(', ') || '*')
            setShowSettings(true)
          }}>
            设置
          </Button>
        </div>
        <div className="mt-2 flex items-center gap-4 text-sm text-muted">
          <PlatformBadge platform={project.platform as 'github' | 'gitlab' | 'gitee'} />
          <span>·</span>
          <WebhookStatus status={project.webhook_status || (project.webhook_enabled ? 'connected' : 'disconnected')} />
          {project.recent_review_time && (
            <>
              <span>·</span>
              <span>最近评审: {project.recent_review_time}</span>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id)
              setSearchParams({ tab: tab.id }, { replace: true })
            }}
            className={cn(
              'px-4 py-3 text-sm font-medium transition-colors',
              activeTab === tab.id
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content: PR List */}
      {activeTab === 'prs' && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface text-left text-muted-more">
                <th className="px-4 py-3 font-medium">PR #</th>
                <th className="px-4 py-3 font-medium">标题</th>
                <th className="px-4 py-3 font-medium">作者</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">AI 评审</th>
                <th className="px-4 py-3 font-medium">评分</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {prsLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50">
                    {Array.from({ length: 7 }).map((_, j) => (
                      <td key={j} className="px-4 py-4">
                        <Skeleton className="h-4 w-16" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : !prs?.items?.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12">
                    <EmptyState title="暂无 PR" description="该仓库还没有提交 Pull Request" />
                  </td>
                </tr>
              ) : (
                prs.items.map((pr: any) => (
                  <tr
                    key={pr.pr_number}
                    className="border-b border-border/50 transition-colors hover:bg-surface-hover/50 cursor-pointer"
                    onClick={() => navigate(`/projects/${id}/prs/${pr.pr_number}`)}
                  >
                    <td className="px-4 py-4 font-mono text-primary">
                      #{pr.pr_number}
                    </td>
                    <td className="px-4 py-4 text-foreground">{pr.title || '-'}</td>
                    <td className="px-4 py-4 text-muted">{pr.author || '-'}</td>
                    <td className="px-4 py-4">
                      <PRStateBadge state={pr.state} isMerged={pr.is_merged} />
                    </td>
                    <td className="px-4 py-4">
                      <ReviewStatusBadge status={pr.review_status} />
                    </td>
                    <td className="px-4 py-4">
                      {pr.review_score != null ? (
                        <span
                          className={cn(
                            'font-medium',
                            pr.review_score >= 90
                              ? 'text-success'
                              : pr.review_score >= 70
                                ? 'text-warning'
                                : 'text-error',
                          )}
                        >
                          {pr.review_score}
                        </span>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <Button variant="ghost" size="sm">
                        查看
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {prs && prs.total > prs.page_size && (
            <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted">
              <span>
                第 {prs.page} 页，共 {Math.ceil(prs.total / prs.page_size)} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={prPage <= 1}
                  onClick={() => setPrPage((p) => p - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={prPage * prs.page_size >= prs.total}
                  onClick={() => setPrPage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab Content: Commits (placeholder) */}
      {/* Tab Content: Commits */}
      {activeTab === 'commits' && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface text-left text-muted-more">
                  <th className="px-4 py-3 font-medium">SHA</th>
                  <th className="px-4 py-3 font-medium">作者</th>
                  <th className="px-4 py-3 font-medium">提交信息</th>
                  <th className="px-4 py-3 font-medium">分支</th>
                  <th className="px-4 py-3 font-medium">严重级别</th>
                  <th className="px-4 py-3 font-medium">分数</th>
                  <th className="px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {commitsLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className="border-b border-border/50">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <td key={j} className="px-4 py-4">
                          <Skeleton className="h-4 w-20" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : !commitsData?.items?.length ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12">
                      <EmptyState
                        title="暂无提交记录"
                        description="提交数据将在接入 Webhook 后自动同步"
                      />
                    </td>
                  </tr>
                ) : (
                  commitsData.items.map((commit: { id: string; sha: string; author: string | null; message: string | null; branch: string | null; is_reviewed: boolean; review_id: string | null; review_score: number | null; severity_breakdown: Record<string, number> | null }) => (
                    <tr
                      key={commit.id}
                      className="border-b border-border/50 transition-colors hover:bg-surface-hover/50 cursor-pointer"
                      onClick={() => commit.review_id && navigate(`/projects/${id}/reviews/${commit.review_id}`)}
                    >
                      <td className="px-4 py-4 font-mono text-xs text-primary">
                        {commit.sha.slice(0, 7)}
                      </td>
                      <td className="px-4 py-4 text-muted">{commit.author || '-'}</td>
                      <td className="max-w-md truncate px-4 py-4 text-foreground" title={commit.message ?? ''}>
                        {commit.message || '-'}
                      </td>
                      <td className="px-4 py-4">
                        {commit.branch ? (
                          <Badge variant="default">{commit.branch}</Badge>
                        ) : (
                          <span className="text-muted-more">-</span>
                        )}
                      </td>
                      <td className="px-4 py-4">
                        <SeverityBadges breakdown={commit.severity_breakdown} />
                      </td>
                      <td className="px-4 py-4">
                        {commit.is_reviewed && commit.review_score != null ? (
                          <span className={cn(
                            'text-sm font-medium',
                            commit.review_score >= 90 ? 'text-success' : commit.review_score >= 70 ? 'text-warning' : 'text-error',
                          )}>
                            {commit.review_score}
                          </span>
                        ) : commit.is_reviewed ? (
                          <Badge variant="success">✓</Badge>
                        ) : (
                          <Badge variant="warning">待评审</Badge>
                        )}
                      </td>
                      <td className="px-4 py-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={triggerReview.isPending && triggeredSha !== commit.sha}
                          onClick={async (e) => {
                            e.stopPropagation()
                            setTriggerErrorSha(null)
                            try {
                              await triggerReview.mutateAsync({
                                sha: commit.sha,
                                mentionUser: 'reviewer',
                              })
                              setTriggeredSha(commit.sha)
                              setTimeout(() => setTriggeredSha(null), 2000)
                            } catch {
                              setTriggerErrorSha(commit.sha)
                              setTimeout(() => setTriggerErrorSha(null), 2000)
                            }
                          }}
                        >
                          {triggeredSha === commit.sha
                            ? '✓ 已触发'
                            : triggerErrorSha === commit.sha
                              ? '✗ 触发失败'
                              : triggerReview.isPending
                                ? '...'
                                : '@ 触发评审'}
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {commitsData && commitsData.total > commitsData.page_size && (
            <div className="flex items-center justify-between text-sm text-muted">
              <span>
                第 {commitsData.page} 页，共 {Math.ceil(commitsData.total / commitsData.page_size)} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={commitPage <= 1}
                  onClick={() => setCommitPage((p) => p - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={commitPage * commitsData.page_size >= commitsData.total}
                  onClick={() => setCommitPage((p) => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab Content: 评审记录 */}
      {activeTab === 'reviews' && (
        <ReviewsTabContent
          projectId={id!}
          data={projectReviews}
          isLoading={reviewsLoading}
          status={reviewsStatus}
          onStatusChange={(s) => { setReviewsStatus(s); setReviewsPage(1) }}
          page={reviewsPage}
          onPageChange={setReviewsPage}
        />
      )}

      {/* Tab Content: Quality Trends */}
      {activeTab === 'quality' && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">质量趋势</h2>
          {trendsLoading ? (
            <Skeleton className="h-64" />
          ) : !trends?.items?.length ? (
            <EmptyState title="暂无质量数据" description="完成评审后展示质量趋势" />
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={trends.items}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" stroke="#64748B" fontSize={12} />
                <YAxis domain={[0, 100]} stroke="#64748B" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: '#1E293B',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    color: '#F8FAFC',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="avg_score"
                  name="平均分"
                  stroke="#2563EB"
                  strokeWidth={2}
                  dot={{ fill: '#2563EB', r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Tab Content: Webhook Events */}
      {activeTab === 'webhook' && (
        <WebhookEventsTab projectId={id!} />
      )}

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="flex w-full max-w-2xl h-[70vh] rounded-xl border border-border bg-surface shadow-lg overflow-hidden">
            {/* Left Sidebar */}
            <div className="w-44 shrink-0 border-r border-border bg-surface-alt p-3 flex flex-col">
              <h2 className="text-sm font-bold text-foreground px-3 py-2">项目设置</h2>
              <div className="mt-2 space-y-1 flex-1">
                {[
                  { id: 'basic', label: '基本信息', icon: '📋' },
                  { id: 'webhook', label: 'Webhook', icon: '🔗' },
                  { id: 'branches', label: '分支过滤', icon: '🌿' },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSettingsTab(tab.id)}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors text-left ${
                      activeSettingsTab === tab.id
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'text-muted hover:text-foreground hover:bg-surface-hover'
                    }`}
                  >
                    <span className="text-base">{tab.icon}</span>
                    <span>{tab.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Right Content */}
            <div className="flex-1 flex flex-col">
              {/* Header with close button */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                <div>
                  <h2 className="text-lg font-bold text-foreground">
                    {activeSettingsTab === 'basic' && '基本信息'}
                    {activeSettingsTab === 'webhook' && 'Webhook 配置'}
                    {activeSettingsTab === 'branches' && '分支过滤'}
                  </h2>
                  <p className="text-sm text-muted">
                    {activeSettingsTab === 'basic' && '项目的基础配置信息'}
                    {activeSettingsTab === 'webhook' && '配置 Webhook 以自动同步仓库数据'}
                    {activeSettingsTab === 'branches' && '设置需要触发 AI 评审的分支范围'}
                  </p>
                </div>
                <button
                  onClick={() => setShowSettings(false)}
                  className="shrink-0 rounded-md p-1.5 text-muted hover:text-foreground hover:bg-surface-hover transition-colors"
                  title="关闭"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              {/* Scrollable content */}
              <div className="flex-1 p-6 overflow-y-auto">
              {/* ═══ Basic Info ═══ */}
              {activeSettingsTab === 'basic' && (
                <div className="space-y-5">
                  <div>
                    <h3 className="text-base font-bold text-foreground">基本信息</h3>
                    <p className="mt-1 text-sm text-muted">项目的基础配置信息</p>
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between items-center rounded-lg border border-border bg-surface-alt px-4 py-3">
                      <span className="text-muted">项目 ID</span>
                      <span className="text-foreground font-mono text-xs">{project.id}</span>
                    </div>
                    <div className="flex justify-between items-center rounded-lg border border-border bg-surface-alt px-4 py-3">
                      <span className="text-muted">名称</span>
                      <span className="text-foreground">{project.name}</span>
                    </div>
                    <div className="flex justify-between items-center rounded-lg border border-border bg-surface-alt px-4 py-3">
                      <span className="text-muted">平台</span>
                      <PlatformBadge platform={project.platform as 'github' | 'gitlab' | 'gitee'} />
                    </div>
                    <div className="flex justify-between items-center rounded-lg border border-border bg-surface-alt px-4 py-3">
                      <span className="text-muted">仓库 URL</span>
                      <span className="text-foreground font-mono text-xs truncate max-w-[200px]">{project.repo_url}</span>
                    </div>
                    <div className="flex justify-between items-center rounded-lg border border-border bg-surface-alt px-4 py-3">
                      <span className="text-muted">Webhook 状态</span>
                      <WebhookStatus status={project.webhook_status || (project.webhook_enabled ? 'connected' : 'disconnected')} />
                    </div>
                  </div>
                </div>
              )}

              {/* ═══ Webhook ═══ */}
              {activeSettingsTab === 'webhook' && (
                <div className="space-y-5">
                  <div>
                    <h3 className="text-base font-bold text-foreground">Webhook 配置</h3>
                    <p className="mt-1 text-sm text-muted">
                      在 GitHub/GitLab/Gitee 的仓库设置中添加以下 Webhook URL 以自动同步 PR 数据
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface-alt p-4">
                    <h4 className="text-sm font-medium text-foreground">Webhook URL</h4>
                    <div className="mt-2 flex items-center gap-2 rounded-md bg-black/30 px-3 py-2 text-xs font-mono text-primary">
                      <span className="flex-1 truncate font-mono text-xs">
                        ngrok URL 替换: ngrok_地址/webhook/{project.platform}
                      </span>
                      <button
                        onClick={async () => {
                          const url = `http://localhost:8000/webhook/${project.platform}`
                          try {
                            await navigator.clipboard.writeText(url)
                            setCopied(true)
                            setTimeout(() => setCopied(false), 2000)
                          } catch { /* fallback: ignore */ }
                        }}
                        className="shrink-0 text-xs text-muted hover:text-foreground transition-colors min-w-[4rem] text-center"
                        title="复制"
                      >
                        {copied ? '已复制!' : '复制'}
                      </button>
                    </div>
                    <div className="mt-3 space-y-1 text-xs text-muted">
                      <p>• 内容类型: <span className="text-foreground">application/json</span></p>
                      <p>• 触发事件: <span className="text-foreground">Pull Request (opened, synchronize, closed)</span></p>
                      <p>• 开发环境使用 ngrok 隧道暴露后端 8000 端口</p>
                      <p>• 在 ngrok 终端查看公网 URL，替换上方地址</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <button onClick={() => { setWebhookTestResult(null); testWebhook.mutate() }}
                      disabled={testWebhook.isPending}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-foreground hover:bg-surface-hover transition-colors disabled:opacity-50">
                      {testWebhook.isPending ? '测试中...' : '测试连接'}
                    </button>
                    {webhookTestResult && (
                      <span className={`text-xs ${webhookTestResult.startsWith('已连接') ? 'text-success' : 'text-warning'}`}>
                        {webhookTestResult}
                      </span>
                    )}
                  </div>

                  <div className="rounded-lg border border-border/50 bg-surface-alt/50 p-3 text-xs text-muted">
                    PR 数据通过 Webhook 自动同步。配置 Webhook 后，新创建的 PR 将在提交时自动出现在列表中。
                    如尚未配置，PR 列表为空是正常现象。
                  </div>
                </div>
              )}

              {/* ═══ Branch Filter ═══ */}
              {activeSettingsTab === 'branches' && (
                <div className="space-y-5">
                  <div>
                    <h3 className="text-base font-bold text-foreground">评审分支过滤</h3>
                    <p className="mt-1 text-sm text-muted">
                      只有匹配以下分支模式的推送才会触发 AI 评审，减少不必要的调用。
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface-alt p-4">
                    <label className="block text-sm font-medium text-foreground" htmlFor="review-branches">
                      分支模式
                    </label>
                    <p className="mt-1 text-xs text-muted mb-3">
                      多个模式用逗号分隔，支持通配符 <code className="text-primary">*</code>
                    </p>
                    <div className="flex gap-2">
                      <input
                        id="review-branches"
                        type="text"
                        value={reviewBranchesInput}
                        onChange={(e) => setReviewBranchesInput(e.target.value)}
                        placeholder="main, develop, release/*"
                        className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-more focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={updateProject.isPending}
                        onClick={async () => {
                          setSaveSuccess(null)
                          const branches = reviewBranchesInput
                            .split(/[,，\s]+/)
                            .map((b) => b.trim())
                            .filter(Boolean)
                          try {
                            await updateProject.mutateAsync({
                              id: project.id,
                              review_branches: branches.length > 0 ? branches : ['*'],
                            })
                            setSaveSuccess('分支配置已保存')
                            setTimeout(() => setSaveSuccess(null), 3000)
                          } catch {
                            setSaveSuccess('保存失败，请重试')
                          }
                        }}
                      >
                        {updateProject.isPending ? '保存中...' : '保存'}
                      </Button>
                    </div>
                    {saveSuccess && (
                      <p className={`mt-2 text-xs ${saveSuccess.includes('失败') ? 'text-error' : 'text-success'}`}>
                        {saveSuccess}
                      </p>
                    )}
                    {updateProject.isError && (
                      <p className="mt-2 text-xs text-error">保存失败，请稍后重试</p>
                    )}
                  </div>

                  <div className="rounded-lg border border-border bg-surface-alt p-4">
                    <h4 className="text-sm font-medium text-foreground">使用示例</h4>
                    <div className="mt-2 space-y-2 text-xs text-muted">
                      <div className="flex items-center gap-2">
                        <code className="rounded bg-black/30 px-2 py-0.5 text-foreground">*</code>
                        <span>所有分支（默认）</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <code className="rounded bg-black/30 px-2 py-0.5 text-foreground">main</code>
                        <span>仅 main 分支</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <code className="rounded bg-black/30 px-2 py-0.5 text-foreground">main, develop</code>
                        <span>main 和 develop 分支</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <code className="rounded bg-black/30 px-2 py-0.5 text-foreground">release/*</code>
                        <span>所有 release 前缀的分支</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
