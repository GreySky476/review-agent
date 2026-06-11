import { useState, useEffect, useRef } from 'react'
import { useErrors, useErrorStats, useErrorTrend, type ErrorStatsItem } from '@/hooks/use-errors'
import {
  Skeleton,
  ErrorState,
  EmptyState,
  Badge,
  Button,
} from '@/components/ui/shared'
import { cn } from '@/lib/utils'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LineChart,
  Line,
} from 'recharts'

const ERROR_TYPE_COLORS: Record<string, string> = {
  ai_call_failed: '#DC2626',
  git_api_failed: '#D97706',
  git_file_fetch_failed: '#EA580C',
  parse_failed: '#0EA5E9',
  timeout: '#A21CAF',
  pipeline_crashed: '#BE123C',
  pipeline_partial_failure: '#F59E0B',
  webhook_parse_failed: '#6366F1',
  webhook_verify_failed: '#8B5CF6',
  queue_enqueue_failed: '#EC4899',
  db_write_failed: '#EF4444',
  publish_failed: '#F97316',
  unknown: '#6B7280',
}

const ERROR_LABELS: Record<string, string> = {
  ai_call_failed: 'AI 调用失败',
  git_api_failed: 'Git API 失败',
  git_file_fetch_failed: 'Git 文件拉取失败',
  parse_failed: '解析失败',
  timeout: '超时',
  pipeline_crashed: '流水线崩溃',
  pipeline_partial_failure: '流水线部分失败',
  webhook_parse_failed: 'Webhook 解析失败',
  webhook_verify_failed: 'Webhook 验证失败',
  queue_enqueue_failed: '队列入队失败',
  db_write_failed: '数据库写入失败',
  publish_failed: '发布评论失败',
  unknown: '未知错误',
}

const errorTypeOptions = [
  { value: '', label: '全部类型' },
  ...Object.entries(ERROR_LABELS).map(([value, label]) => ({ value, label })),
]

function AlertBanner({ stats }: { stats: ErrorStatsItem[] }) {
  const spike = stats.find((s) => s.count > 5)
  if (!spike) return null
  return (
    <div className="flex items-center gap-2 rounded-lg border border-error/30 bg-error/5 px-4 py-3 text-sm">
      <span className="text-error font-bold">⚠</span>
      <span className="text-foreground">
        <strong>{ERROR_LABELS[spike.error_type] || spike.error_type}</strong> 发生次数较多（{spike.count} 次），建议关注
      </span>
    </div>
  )
}

export function ErrorsPage() {
  const [errorType, setErrorType] = useState('')
  const [page, setPage] = useState(1)
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

  const { data, isLoading, error, refetch } = useErrors({
    error_type: errorType || undefined,
    page,
  })
  const { data: stats, isLoading: statsLoading } = useErrorStats()
  const { data: trend, isLoading: trendLoading } = useErrorTrend(14)

  if (error) {
    return <ErrorState message="异常数据加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">异常监控</h1>
      </div>

      {/* Alert Banner */}
      {stats && stats.length > 0 && <AlertBanner stats={stats} />}

      {/* ── Two-column: Type Distribution + Trend ── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Error Type Distribution */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">错误类型分布</h2>
          {statsLoading ? (
            <Skeleton className="h-48" />
          ) : !stats?.length ? (
            <EmptyState title="暂无异常数据" description="系统运行正常" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={stats}
                layout="vertical"
                onClick={(e) => {
                  if (e?.activePayload?.[0]?.payload?.error_type) {
                    setErrorType(e.activePayload[0].payload.error_type)
                    setPage(1)
                  }
                }}
                style={{ cursor: 'pointer' }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E4DD" />
                <XAxis type="number" stroke="#A8A29E" fontSize={12} />
                <YAxis
                  dataKey="error_type"
                  type="category"
                  stroke="#A8A29E"
                  fontSize={12}
                  tickFormatter={(v) => ERROR_LABELS[v] || v}
                  width={130}
                />
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E6E4DD',
                    borderRadius: '8px',
                    color: '#292524',
                  }}
                  formatter={(_: any, __: any, props: any) => [
                    props.payload.count,
                    ERROR_LABELS[props.payload.error_type] || props.payload.error_type,
                  ]}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {stats.map((entry: ErrorStatsItem) => (
                    <Cell
                      key={entry.error_type}
                      fill={ERROR_TYPE_COLORS[entry.error_type] || '#64748B'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Error Trend */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium text-foreground">错误趋势（近 14 天）</h2>
          {trendLoading ? (
            <Skeleton className="h-48" />
          ) : !trend?.length ? (
            <EmptyState title="暂无趋势数据" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E4DD" />
                <XAxis dataKey="date" stroke="#A8A29E" fontSize={11} />
                <YAxis stroke="#A8A29E" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E6E4DD',
                    borderRadius: '8px',
                    color: '#292524',
                  }}
                />
                <Line type="monotone" dataKey="count" name="错误数" stroke="#DC2626" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[140px]"
          >
            <span className="flex-1 text-left">
              {errorTypeOptions.find((o) => o.value === errorType)?.label || '全部类型'}
            </span>
            <svg className={`h-4 w-4 text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 max-h-60 w-full overflow-y-auto rounded-md border border-border bg-surface shadow-lg">
              {errorTypeOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    setErrorType(opt.value)
                    setPage(1)
                    setDropdownOpen(false)
                  }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                    errorType === opt.value ? 'text-primary font-medium' : 'text-foreground'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
        {data && (
          <span className="text-xs text-muted-more">
            共 {data.total} 条记录
          </span>
        )}
      </div>

      {/* Error Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-muted-more">
              <th className="px-4 py-3 font-medium">时间</th>
              <th className="px-4 py-3 font-medium">类型</th>
              <th className="px-4 py-3 font-medium">恢复状态</th>
              <th className="px-4 py-3 font-medium">错误消息</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {Array.from({ length: 4 }).map((_, j) => (
                    <td key={j} className="px-4 py-4">
                      <Skeleton className="h-4 w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : !data?.items?.length ? (
              <tr>
                <td colSpan={4} className="px-4 py-12">
                  <EmptyState title="暂无异常" description="系统运行正常，没有错误记录" />
                </td>
              </tr>
            ) : (
              data.items.map((err: { id: string; create_time: string; error_type: string; error_message: string; recovered: boolean }) => (
                <tr
                  key={err.id}
                  className="border-b border-border/50 transition-colors hover:bg-surface-hover/50"
                >
                  <td className="px-4 py-4 text-muted">
                    {err.create_time
                      ? new Date(err.create_time).toLocaleString('zh-CN')
                      : '-'}
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium"
                      style={{
                        color: ERROR_TYPE_COLORS[err.error_type] || '#6B7280',
                        background: `${ERROR_TYPE_COLORS[err.error_type] || '#6B7280'}15`,
                      }}
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: ERROR_TYPE_COLORS[err.error_type] || '#6B7280' }}
                      />
                      {ERROR_LABELS[err.error_type] || err.error_type}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    {err.recovered ? (
                      <Badge variant="success">已恢复</Badge>
                    ) : (
                      <Badge variant="error">未恢复</Badge>
                    )}
                  </td>
                  <td className="max-w-md truncate px-4 py-4 text-muted" title={err.error_message}>
                    {err.error_message}
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
    </div>
  )
}
