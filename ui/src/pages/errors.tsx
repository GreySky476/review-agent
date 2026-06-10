import { useState, useEffect, useRef } from 'react'
import { useErrors, useErrorStats, type ErrorStatsItem } from '@/hooks/use-errors'
import {
  Skeleton,
  ErrorState,
  EmptyState,
  Badge,
  Button,
} from '@/components/ui/shared'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const ERROR_TYPE_COLORS: Record<string, string> = {
  ai_call_failed: '#DC2626',
  git_api_failed: '#D97706',
  parse_failed: '#0EA5E9',
  timeout: '#A21CAF',
}

const ERROR_LABELS: Record<string, string> = {
  ai_call_failed: 'AI 调用失败',
  git_api_failed: 'Git API 失败',
  parse_failed: '解析失败',
  timeout: '超时',
}

const errorTypeOptions = [
  { value: '', label: '全部类型' },
  { value: 'ai_call_failed', label: 'AI 调用失败' },
  { value: 'git_api_failed', label: 'Git API 失败' },
  { value: 'parse_failed', label: '解析失败' },
  { value: 'timeout', label: '超时' },
]

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

  if (error) {
    return <ErrorState message="异常数据加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">异常监控</h1>

      {/* Stats Chart */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <h2 className="mb-4 text-sm font-medium text-foreground">错误类型分布</h2>
        {statsLoading ? (
          <Skeleton className="h-48" />
        ) : !stats?.length ? (
          <EmptyState title="暂无异常数据" description="系统运行正常" />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stats} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#E6E4DD" />
              <XAxis type="number" stroke="#A8A29E" fontSize={12} />
              <YAxis
                dataKey="error_type"
                type="category"
                stroke="#A8A29E"
                fontSize={12}
                tickFormatter={(v) => ERROR_LABELS[v] || v}
                width={120}
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

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]"
          >
            <span className="flex-1 text-left">
              {errorTypeOptions.find((o) => o.value === errorType)?.label || '全部类型'}
            </span>
            <svg className={`h-4 w-4 text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {errorTypeOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    setErrorType(opt.value)
                    setPage(1)
                    setDropdownOpen(false)
                  }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                    errorType === opt.value ? 'text-primary' : 'text-foreground'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
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
                    <Badge
                      variant={
                        err.error_type === 'ai_call_failed'
                          ? 'error'
                          : err.error_type === 'git_api_failed'
                            ? 'warning'
                            : err.error_type === 'timeout'
                              ? 'purple'
                              : 'info'
                      }
                    >
                      {ERROR_LABELS[err.error_type] || err.error_type}
                    </Badge>
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
