import { useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useProject } from '@/hooks/use-projects'
import { usePullRequests } from '@/hooks/use-reviews'
import { useCommits, useTriggerCommitReview } from '@/hooks/use-commits'
import { useQualityTrends } from '@/hooks/use-dashboard'
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

type TabId = 'prs' | 'commits' | 'quality' | 'webhook'

const tabs: { id: TabId; label: string }[] = [
  { id: 'prs', label: 'PR 列表' },
  { id: 'commits', label: '提交' },
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

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = (searchParams.get('tab') as TabId) || 'prs'
  const [activeTab, setActiveTab] = useState<TabId>(
    ['prs', 'commits', 'quality'].includes(tabFromUrl) ? tabFromUrl : 'prs',
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
  const queryClient = useQueryClient()
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
          <Button variant="secondary" size="sm" onClick={() => setShowSettings(true)}>
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
                  <th className="px-4 py-3 font-medium">Review</th>
                  <th className="px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {commitsLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className="border-b border-border/50">
                      {Array.from({ length: 6 }).map((_, j) => (
                        <td key={j} className="px-4 py-4">
                          <Skeleton className="h-4 w-20" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : !commitsData?.items?.length ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12">
                      <EmptyState
                        title="暂无提交记录"
                        description="提交数据将在接入 Webhook 后自动同步"
                      />
                    </td>
                  </tr>
                ) : (
                  commitsData.items.map((commit: { id: string; sha: string; author: string | null; message: string | null; branch: string | null; is_reviewed: boolean }) => (
                    <tr
                      key={commit.id}
                      className="border-b border-border/50 transition-colors hover:bg-surface-hover/50"
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
                        {commit.is_reviewed ? (
                          <Badge variant="success">已评审</Badge>
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
          <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-lg">
            <h2 className="text-lg font-bold text-foreground">项目设置</h2>
            <p className="mt-1 text-sm text-muted">项目信息和 Webhook 配置</p>

            <div className="mt-4 space-y-5">
              {/* Basic Info */}
              <div>
                <h3 className="text-sm font-medium text-foreground">基本信息</h3>
                <div className="mt-2 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted">项目 ID</span>
                    <span className="text-foreground font-mono text-xs">{project.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">名称</span>
                    <span className="text-foreground">{project.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">平台</span>
                    <PlatformBadge platform={project.platform as 'github' | 'gitlab' | 'gitee'} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">仓库 URL</span>
                    <span className="text-foreground font-mono text-xs truncate max-w-[240px]">{project.repo_url}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Webhook</span>
                    <WebhookStatus status={project.webhook_status || (project.webhook_enabled ? 'connected' : 'disconnected')} />
                  </div>
                </div>
              </div>

              {/* Webhook Config */}
              <div className="rounded-lg border border-border bg-surface-alt p-4">
                <h3 className="text-sm font-medium text-foreground">配置 Webhook</h3>
                <p className="mt-1 text-xs text-muted">
                  在 GitHub/GitLab/Gitee 的仓库设置中添加以下 Webhook URL 以自动同步 PR 数据：
                </p>
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

              {/* Test Connection */}
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

              {/* Sync Notice */}
              <div className="rounded-lg border border-border/50 bg-surface-alt/50 p-3 text-xs text-muted">
                PR 数据通过 Webhook 自动同步。配置 Webhook 后，新创建的 PR 将在提交时自动出现在列表中。
                如尚未配置，PR 列表为空是正常现象。
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <Button variant="secondary" size="md" onClick={() => setShowSettings(false)}>
                关闭
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
