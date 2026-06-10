import { useDashboardStats, useQualityTrends } from '@/hooks/use-dashboard'
import { StatCard, Skeleton, ErrorState, EmptyState } from '@/components/ui/shared'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  type PieLabelRenderProps,
} from 'recharts'
import { useState } from 'react'

const PIE_COLORS: Record<string, string> = {
  security: '#DC2626',
  bug: '#D97706',
  performance: '#0EA5E9',
  style: '#65A30D',
  dependency: '#A21CAF',
  structure: '#E11D48',
}

const PIE_LABELS: Record<string, string> = {
  security: '安全',
  bug: 'Bug',
  performance: '性能',
  style: '代码规范',
  dependency: '依赖',
  structure: '结构',
}

export function DashboardPage() {
  const { data: stats, isLoading: statsLoading, error: statsError, refetch: refetchStats } = useDashboardStats()
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('monthly')
  const { data: trends, isLoading: trendsLoading } = useQualityTrends({ period })

  if (statsError) {
    return <ErrorState message="仪表盘数据加载失败" onRetry={refetchStats} />
  }

  const pieData = stats?.finding_distribution
    ? Object.entries(stats.finding_distribution).map(([key, value]) => ({
        name: PIE_LABELS[key] || key,
        value,
        color: PIE_COLORS[key] || '#64748B',
      }))
    : []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">仪表盘</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statsLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))
        ) : (
          <>
            <StatCard
              title="接入仓库"
              value={stats?.total_projects ?? 0}
              icon="📦"
            />
            <StatCard
              title="今日评审"
              value={stats?.total_reviews_today ?? 0}
              icon="📝"
            />
            <StatCard
              title="平均评分"
              value={stats?.average_score ? `${Math.round(stats.average_score)}` : '-'}
              icon="⭐"
            />
            <StatCard
              title="待处理异常"
              value={stats?.pending_errors ?? 0}
              icon="⚠️"
            />
          </>
        )}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Trend Chart */}
        <div className="rounded-lg border border-border bg-surface p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium text-foreground">质量趋势</h2>
            <div className="flex gap-1">
              {(['daily', 'weekly', 'monthly'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    period === p
                      ? 'bg-primary text-on-primary'
                      : 'text-muted hover:text-foreground'
                  }`}
                >
                  {p === 'daily' ? '日' : p === 'weekly' ? '周' : '月'}
                </button>
              ))}
            </div>
          </div>

          {trendsLoading ? (
            <Skeleton className="h-64" />
          ) : !trends?.items?.length ? (
            <EmptyState title="暂无趋势数据" description="接入项目并完成评审后将显示质量趋势" />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={trends.items}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E4DD" />
                <XAxis dataKey="date" stroke="#A8A29E" fontSize={12} />
                <YAxis domain={[0, 100]} stroke="#A8A29E" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E6E4DD',
                    borderRadius: '8px',
                    color: '#292524',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="avg_score"
                  name="平均分"
                  stroke="#D97706"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Pie Chart */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">问题分布</h2>
          {statsLoading ? (
            <Skeleton className="h-64" />
          ) : pieData.length === 0 ? (
            <EmptyState title="暂无问题数据" />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, percent }: PieLabelRenderProps) =>
                    `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                >
                  {pieData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E6E4DD',
                    borderRadius: '8px',
                    color: '#292524',
                  }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
