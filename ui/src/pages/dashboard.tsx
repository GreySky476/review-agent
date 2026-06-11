import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useEnterpriseStats,
  useQualityTrends,
  useProjectHealth,
  useRecentReviews,
  usePlatformHealth,
  type RecentReviewItem,
  type ProjectHealthItem,
} from '@/hooks/use-dashboard'
import { StatCard, Skeleton, ErrorState, EmptyState, Badge, Button } from '@/components/ui/shared'
import { cn } from '@/lib/utils'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'

/* ── Helpers ───────────────────────────────────────────────── */

const PERIOD_LABELS: Record<string, string> = { daily: '日', weekly: '周', monthly: '月' }

const HEALTH_LABELS: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'default' }> = {
  active: { label: '🟢 健康', variant: 'success' },
  warning: { label: '🟡 一般', variant: 'warning' },
  critical: { label: '🔴 危险', variant: 'error' },
  dormant: { label: '⚪ 休眠', variant: 'default' },
}

const STATUS_BADGE: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'info' }> = {
  completed: { label: '✅ 完成', variant: 'success' },
  completed_with_errors: { label: '⚠ 异常', variant: 'warning' },
  pending: { label: '⏳ 等待', variant: 'info' },
  running: { label: '🔄 进行', variant: 'info' },
  failed: { label: '❌ 失败', variant: 'error' },
}

function TrendBadge({ change, suffix = '%' }: { change: number; suffix?: string }) {
  if (change === 0) return null
  const isUp = change > 0
  return (
    <span className={cn('text-xs font-medium', isUp ? 'text-success' : 'text-error')}>
      {isUp ? '↑' : '↓'} {Math.abs(change)}{suffix}
    </span>
  )
}

/* ── StatCard with trend ───────────────────────────────────── */
function EnterpriseStatCard({
  title,
  value,
  change,
  icon,
  valueFormat,
}: {
  title: string
  value: string | number
  change: number
  icon: string
  valueFormat?: string
}) {
  const color = change === 0 ? 'text-muted-more'
    : change > 0 ? 'text-success'
    : 'text-error'
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted">{title}</p>
          <p className="mt-1 text-3xl font-bold tracking-tight text-foreground">
            {value}{valueFormat ?? ''}
          </p>
          <p className={cn('mt-1 text-xs', color)}>
            {change === 0 ? '— 持平' : change > 0 ? `↑ ${change}%` : `↓ ${Math.abs(change)}%`}
            <span className="text-muted-more ml-1">vs 上周</span>
          </p>
        </div>
        <div className="text-muted-more">{icon}</div>
      </div>
    </div>
  )
}

/* ── Platform Health Indicator ─────────────────────────────── */
const PLATFORM_STATUS: Record<string, { icon: string; color: string }> = {
  connected: { icon: '🟢', color: 'text-success' },
  error: { icon: '🔴', color: 'text-error' },
  pending: { icon: '🟡', color: 'text-warning' },
}

function PlatformStatus({ platforms }: { platforms: { platform: string; status: string; latency_ms: number }[] }) {
  if (!platforms.length) return <EmptyState title="暂无平台数据" />
  return (
    <div className="space-y-3">
      {platforms.map((p) => {
        const st = PLATFORM_STATUS[p.status] ?? { icon: '⚪', color: 'text-muted' }
        return (
          <div key={p.platform} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span>{st.icon}</span>
              <span className="text-sm font-medium text-foreground">{p.platform}</span>
            </div>
            <span className={cn('text-xs font-mono', st.color)}>
              {p.status === 'connected' ? `${p.latency_ms}ms` : p.status}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/* ── Review Activity Feed ──────────────────────────────────── */
function ReviewFeedItem({ item }: { item: RecentReviewItem }) {
  const cfg = STATUS_BADGE[item.status] ?? { label: item.status, variant: 'default' as const }
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {item.project_name}
          </span>
          {item.branch && <span className="text-xs font-mono text-muted-more">{item.branch}</span>}
        </div>
        <p className="text-xs text-muted truncate mt-0.5">{item.pr_title || item.head_sha}</p>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-3">
        {item.score != null && (
          <span className={cn(
            'text-sm font-bold',
            item.score >= 90 ? 'text-success' : item.score >= 70 ? 'text-warning' : 'text-error',
          )}>
            {item.score}
          </span>
        )}
        <Badge variant={cfg.variant}>{cfg.label}</Badge>
        {item.duration_seconds != null && (
          <span className="text-xs text-muted-more">{item.duration_seconds}s</span>
        )}
      </div>
    </div>
  )
}

/* ── Main Dashboard Page ───────────────────────────────────── */
export function DashboardPage() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('monthly')

  const { data: enterprise, isLoading: entLoading, error: entError, refetch: refetchEnt } = useEnterpriseStats()
  const { data: healthData, isLoading: healthLoading } = useProjectHealth()
  const { data: trends, isLoading: trendsLoading } = useQualityTrends({ period })
  const { data: recent, isLoading: recentLoading } = useRecentReviews()
  const { data: platforms, isLoading: platformLoading } = usePlatformHealth()

  const topFindings = enterprise?.top_findings ?? []
  const statusBreakdown = enterprise?.reviews_by_status ?? {}

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">仪表盘</h1>
        <span className="text-sm text-muted">{new Date().toLocaleDateString('zh-CN')}</span>
      </div>

      {/* ═══ KPI Row ═══ */}
      {entError ? (
        <ErrorState message="摘要数据加载失败" onRetry={refetchEnt} />
      ) : entLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <EnterpriseStatCard title="接入仓库" value={enterprise?.total_projects ?? 0} change={enterprise?.total_projects_change ?? 0} icon="📦" />
          <EnterpriseStatCard title="本周评审" value={enterprise?.reviews_this_week ?? 0} change={enterprise?.reviews_week_change ?? 0} icon="📝" />
          <EnterpriseStatCard title="平均评分" value={enterprise?.avg_score ?? '-'} change={enterprise?.avg_score_change ?? 0} icon="⭐" />
          <EnterpriseStatCard title="异常率" value={enterprise?.error_rate ?? 0} change={enterprise?.error_rate_change ?? 0} icon="⚠️" valueFormat="%" />
          <EnterpriseStatCard title="评审覆盖率" value={enterprise?.review_coverage ?? 0} change={0} icon="📊" valueFormat="%" />
          <EnterpriseStatCard title="总评审" value={(statusBreakdown.completed ?? 0) + (statusBreakdown.completed_with_errors ?? 0) + (statusBreakdown.failed ?? 0) + (statusBreakdown.pending ?? 0) + (statusBreakdown.running ?? 0)} change={0} icon="🔍" />
        </div>
      )}

      {/* ═══ Main Grid: 2 columns ═══ */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* ── Left: Project Health Matrix ── */}
        <div className="lg:col-span-3 rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">项目健康矩阵</h2>
          {healthLoading ? (
            <Skeleton className="h-48" />
          ) : !healthData?.items?.length ? (
            <EmptyState title="暂无项目数据" description="接入项目并完成评审后将展示健康状态" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-more text-xs">
                    <th className="pb-3 pr-3 font-medium">项目名称</th>
                    <th className="pb-3 pr-3 font-medium">评分</th>
                    <th className="pb-3 pr-3 font-medium">趋势</th>
                    <th className="pb-3 pr-3 font-medium">健康状态</th>
                    <th className="pb-3 pr-3 font-medium">本周评审</th>
                    <th className="pb-3 pr-3 font-medium">异常</th>
                    <th className="pb-3 pr-3 font-medium">最近评审</th>
                  </tr>
                </thead>
                <tbody>
                  {healthData.items.map((p: ProjectHealthItem) => {
                    const hl = HEALTH_LABELS[p.health] ?? { label: p.health, variant: 'default' as const }
                    return (
                      <tr
                        key={p.project_id}
                        className="border-b border-border/50 hover:bg-surface-hover/50 cursor-pointer transition-colors"
                        onClick={() => navigate(`/projects/${p.project_id}`)}
                      >
                        <td className="py-3 pr-3 font-medium text-foreground">{p.project_name}</td>
                        <td className="py-3 pr-3">
                          {p.latest_score != null ? (
                            <span className={cn(
                              'font-bold',
                              p.latest_score >= 90 ? 'text-success' : p.latest_score >= 70 ? 'text-warning' : 'text-error',
                            )}>
                              {p.latest_score}
                            </span>
                          ) : <span className="text-muted">-</span>}
                        </td>
                        <td className="py-3 pr-3">
                          {p.score_change != null ? (
                            <TrendBadge change={p.score_change} suffix="" />
                          ) : <span className="text-muted">-</span>}
                        </td>
                        <td className="py-3 pr-3"><Badge variant={hl.variant}>{hl.label}</Badge></td>
                        <td className="py-3 pr-3 text-muted">{p.review_count_7d}</td>
                        <td className="py-3 pr-3">
                          {p.error_count_7d > 0 ? (
                            <span className="font-medium text-error">{p.error_count_7d}</span>
                          ) : <span className="text-muted">0</span>}
                        </td>
                        <td className="py-3 pr-3 text-xs text-muted">
                          {p.last_review_at ? new Date(p.last_review_at).toLocaleDateString('zh-CN') : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Right: Quality Trends ── */}
        <div className="lg:col-span-2 rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-foreground">质量趋势</h2>
            <div className="flex gap-1">
              {(['daily', 'weekly', 'monthly'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={cn(
                    'rounded px-2.5 py-1 text-xs font-medium transition-colors',
                    period === p
                      ? 'bg-primary text-on-primary'
                      : 'text-muted hover:text-foreground',
                  )}
                >
                  {PERIOD_LABELS[p]}
                </button>
              ))}
            </div>
          </div>
          {trendsLoading ? (
            <Skeleton className="h-64" />
          ) : !trends?.items?.length ? (
            <EmptyState title="暂无趋势数据" description="完成评审后将显示质量趋势" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={trends.items}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E4DD" />
                <XAxis dataKey="date" stroke="#A8A29E" fontSize={11} />
                <YAxis domain={[0, 100]} stroke="#A8A29E" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: '#FFF', border: '1px solid #E6E4DD', borderRadius: '8px', color: '#292524' }}
                />
                <Line type="monotone" dataKey="avg_score" name="平均分" stroke="#D97706" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="critical" name="Critical" stroke="#DC2626" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="warning" name="Warning" stroke="#F59E0B" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ═══ Bottom Grid: 3 columns ═══ */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Top Findings ── */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">Top 问题类型</h2>
          {entLoading ? (
            <Skeleton className="h-40" />
          ) : !topFindings.length ? (
            <EmptyState title="暂无数据" description="完成评审后将显示问题分布" />
          ) : (
            <div className="space-y-3">
              {topFindings.map((f: { category: string; count: number }) => (
                <div key={f.category} className="flex items-center justify-between">
                  <span className="text-sm text-foreground">{f.category}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-28 h-2 rounded-full bg-stone-100">
                      <div
                        className="h-2 rounded-full bg-error/60"
                        style={{ width: `${(f.count / Math.max(...topFindings.map((x: { count: number }) => x.count), 1)) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs font-medium text-foreground w-6 text-right">{f.count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Platform Health ── */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">平台连通性</h2>
          {platformLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <PlatformStatus platforms={platforms ?? []} />
          )}
        </div>

        {/* ── Recent Review Activity ── */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium text-foreground">最近评审</h2>
            <Button variant="ghost" size="sm" onClick={() => navigate('/reviews')}>
              查看全部 →
            </Button>
          </div>
          {recentLoading ? (
            <Skeleton className="h-40" />
          ) : !recent?.items?.length ? (
            <EmptyState title="暂无评审" description="完成评审后将在此展示" />
          ) : (
            <div className="divide-y divide-border/50">
              {recent.items.slice(0, 5).map((item: RecentReviewItem) => (
                <ReviewFeedItem key={item.review_id} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
