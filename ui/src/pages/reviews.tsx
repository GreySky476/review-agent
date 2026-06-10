import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import { Skeleton, ErrorState, EmptyState, Badge, Button } from '@/components/ui/shared'
import { useReviewStats } from '@/hooks/use-reviews'
import { cn } from '@/lib/utils'

interface ReviewItem {
  id: string
  project_id: string
  project_name: string
  pr_number: number | null
  pr_title: string
  head_sha: string
  status: string
  score: number | null
  findings_count: number
  severity_breakdown: Record<string, number> | null
  category_breakdown: Record<string, number> | null
  duration_seconds: number | null
  create_time: string | null
}

interface ReviewsResponse {
  items: ReviewItem[]
  total: number
  page: number
  page_size: number
}

const statusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'info' | 'error' }> = {
  completed: { label: '已完成', variant: 'success' },
  pending: { label: '等待中', variant: 'warning' },
  running: { label: '进行中', variant: 'info' },
  failed: { label: '失败', variant: 'error' },
}

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'completed', label: '已完成' },
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '进行中' },
  { value: 'failed', label: '失败' },
]

function ScoreBar({ score }: { score: number }) {
  const color = score >= 90 ? 'bg-success' : score >= 70 ? 'bg-warning' : 'bg-error'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-stone-200">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={cn('text-sm font-medium', color.replace('bg-', 'text-'))}>{score}</span>
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

export function ReviewsPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
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

  const { data, isLoading, error, refetch } = useQuery<ReviewsResponse>({
    queryKey: ['reviews', { status, page }],
    queryFn: async () => {
      const { data } = await api.get('/reviews', {
        params: { status: status || undefined, page },
      })
      return data
    },
    staleTime: 30 * 1000,
  })
  const { data: stats } = useReviewStats()

  if (error) {
    return <ErrorState message="评审记录加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">评审历史</h1>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">总评审数</div>
          <div className="mt-1 text-2xl font-bold text-foreground">{stats?.total_reviews ?? '-'}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">平均评分</div>
          <div className="mt-1 text-2xl font-bold text-foreground">
            {stats?.avg_score != null ? stats.avg_score : '-'}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">Critical 问题</div>
          <div className="mt-1 text-2xl font-bold text-error">
            {stats?.severity_distribution?.critical ?? 0}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-xs text-muted">总发现数</div>
          <div className="mt-1 text-2xl font-bold text-foreground">
            {Object.values(stats?.severity_distribution ?? {}).reduce((a: number, b: number) => a + b, 0) || '-'}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]"
          >
            <span className="flex-1 text-left">
              {statusOptions.find((o) => o.value === status)?.label || '全部状态'}
            </span>
            <svg className={`h-4 w-4 text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {dropdownOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {statusOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => { setStatus(opt.value); setPage(1); setDropdownOpen(false) }}
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
              <th className="px-4 py-3 font-medium">项目</th>
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
              data.items.map((review) => {
                const cfg = statusConfig[review.status] || { label: review.status, variant: 'default' as const }
                return (
                  <tr
                    key={review.id}
                    className="border-b border-border/50 transition-colors hover:bg-surface-hover/50 cursor-pointer"
                    onClick={() => navigate(`/reviews/${review.id}`)}
                  >
                    <td className="px-4 py-4 font-medium text-foreground">{review.project_name}</td>
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
            <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
            <Button variant="secondary" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage((p) => p + 1)}>下一页</Button>
          </div>
        </div>
      )}
    </div>
  )
}
