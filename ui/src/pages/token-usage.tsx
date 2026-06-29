import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import { useProjects } from '@/hooks/use-projects'
import { Badge, Skeleton, EmptyState } from '@/components/ui/shared'

interface TokenItem {
  id: string
  project_id: string
  project_name: string
  pr_number: number | null
  pr_title: string
  head_sha: string
  status: string
  score: number | null
  findings_count: number
  duration_seconds: number | null
  create_time: string | null
  metrics: {
    total_prompt_tokens: number
    total_completion_tokens: number
    ai_call_count: number
    pipeline_duration_ms: number | null
    chunk_count: number
    file_count: number
  } | null
  ai_call_failed: number
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; variant: 'success' | 'warning' | 'error' | 'info' }> = {
    completed: { label: '完成', variant: 'success' },
    completed_with_errors: { label: '异常', variant: 'warning' },
    pending: { label: '等待', variant: 'info' },
    running: { label: '进行', variant: 'info' },
    failed: { label: '失败', variant: 'error' },
  }
  const s = map[status] || { label: status, variant: 'default' as const }
  return <Badge variant={s.variant}>{s.label}</Badge>
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString()
}

function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '-'
  const s = ms / 1000
  if (s > 60) return `${(s / 60).toFixed(1)}m`
  return `${s.toFixed(0)}s`
}

export function TokenUsagePage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterPlatform, setFilterPlatform] = useState('')
  const [filterProject, setFilterProject] = useState('')
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [statusOpen, setStatusOpen] = useState(false)
  const [platformOpen, setPlatformOpen] = useState(false)
  const statusRef = useRef<HTMLDivElement>(null)
  const cascadeRef = useRef<HTMLDivElement>(null)
  const pageSize = 20

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) setStatusOpen(false)
      if (cascadeRef.current && !cascadeRef.current.contains(e.target as Node)) {
        setPlatformOpen(false)
        setFilterPlatform(prev => prev)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const statusOptions = [
    { value: '', label: '全部状态' },
    { value: 'completed', label: '完成' },
    { value: 'completed_with_errors', label: '异常' },
    { value: 'pending', label: '等待' },
    { value: 'running', label: '进行' },
    { value: 'failed', label: '失败' },
  ]
  const platformOptions = [
    { value: '', label: '全部平台' },
    { value: 'github', label: 'GitHub' },
    { value: 'gitlab', label: 'GitLab' },
    { value: 'gitee', label: 'Gitee' },
  ]

  const { data: projects } = useProjects({ platform: filterPlatform || undefined })
  const { data, isLoading } = useQuery({
    queryKey: ['token-usage', page, filterStatus, filterProject, filterDateFrom, filterDateTo],
    queryFn: async () => {
      const params: Record<string, unknown> = { page, page_size: pageSize }
      if (filterStatus) params.status = filterStatus
      if (filterProject) params.project_id = filterProject
      if (filterDateFrom) params.date_from = filterDateFrom
      if (filterDateTo) params.date_to = filterDateTo
      const { data } = await api.get('/reviews', { params })
      return data as { items: TokenItem[]; total: number }
    },
    staleTime: 60 * 1000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Token 消耗</h1>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-4">
        {/* 状态 dropdown */}
        <div className="relative" ref={statusRef}>
          <button onClick={() => setStatusOpen(!statusOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]">
            <span className="flex-1 text-left">{statusOptions.find(s => s.value === filterStatus)?.label || '全部状态'}</span>
            <svg className={`h-4 w-4 text-muted transition-transform ${statusOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {statusOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {statusOptions.map(s => (
                <button key={s.value} onClick={() => { setFilterStatus(s.value); setPage(1); setStatusOpen(false) }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${filterStatus === s.value ? 'text-primary' : 'text-foreground'}`}>
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 平台 + 项目级联筛选 */}
        <div className="relative" ref={cascadeRef}>
          <button onClick={() => setPlatformOpen(!platformOpen)}
            className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors min-w-[120px]">
            <span className="flex-1 text-left">{platformOptions.find(p => p.value === filterPlatform)?.label || '选择平台'}</span>
            <svg className={`h-4 w-4 text-muted transition-transform ${platformOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {platformOpen && (
            <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {platformOptions.map(p => (
                <button key={p.value} onClick={() => {
                  setFilterPlatform(p.value)
                  setFilterProject('')
                  setPage(1)
                  if (!p.value) setPlatformOpen(false) // 点击「全部平台」关闭
                }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${filterPlatform === p.value ? 'text-primary' : 'text-foreground'}`}>
                  {p.label}
                </button>
              ))}
            </div>
          )}
          {/* 项目 dropdown 菜单（紧贴平台菜单右侧） */}
          {platformOpen && filterPlatform && (
            <div className="absolute left-full ml-[3px] top-full mt-1 z-20 w-[200px] rounded-md border border-border bg-surface shadow-lg">
              <button onClick={() => { setFilterProject(''); setPage(1); setPlatformOpen(false) }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${!filterProject ? 'text-primary' : 'text-foreground'}`}>
                全部项目
              </button>
              {projects?.items?.map((p: { id: string; name: string }) => (
                <button key={p.id} onClick={() => { setFilterProject(p.id); setPage(1); setPlatformOpen(false) }}
                  className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${filterProject === p.id ? 'text-primary' : 'text-foreground'}`}>
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 日期范围 */}
        <div className="flex items-center gap-2">
          <input type="date" value={filterDateFrom}
            onChange={e => { setFilterDateFrom(e.target.value); setPage(1) }}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary" />
          <span className="text-xs text-muted">至</span>
          <input type="date" value={filterDateTo}
            onChange={e => { setFilterDateTo(e.target.value); setPage(1) }}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState title="暂无数据" description="还没有评审记录" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-alt text-left text-muted">
                  <th className="px-4 py-3 font-medium">项目 / PR</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium text-right">耗时</th>
                  <th className="px-4 py-3 font-medium text-right">成功</th>
                  <th className="px-4 py-3 font-medium text-right">失败</th>
                  <th className="px-4 py-3 font-medium text-right">LLM 次数</th>
                  <th className="px-4 py-3 font-medium text-right">Input</th>
                  <th className="px-4 py-3 font-medium text-right">Output</th>
                  <th className="px-4 py-3 font-medium text-right">Total</th>
                  <th className="px-4 py-3 font-medium text-right">分块</th>
                  <th className="px-4 py-3 font-medium text-right">文件</th>
                  <th className="px-4 py-3 font-medium text-right">创建时间</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const m = item.metrics
                  return (
                    <tr
                      key={item.id}
                      className="cursor-pointer border-b border-border/50 transition-colors hover:bg-stone-50"
                      onClick={() => navigate(`/reviews/${item.id}/ai-calls`)}
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">
                          {item.project_name || item.pr_title || 'unknown'}
                        </div>
                        <div className="text-xs text-muted">
                          {item.pr_number ? `PR #${item.pr_number} · ` : ''}{item.head_sha?.slice(0, 7)}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={item.status} />
                        {item.score != null && (
                          <div className={`mt-1 text-xs font-medium ${item.score >= 90 ? 'text-success' : item.score >= 70 ? 'text-warning' : 'text-error'}`}>
                            {item.score}/100
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-muted">{fmtDuration(m?.pipeline_duration_ms)}</td>
                      <td className="px-4 py-3 text-right">{fmt(m?.ai_call_count ?? 0 - item.ai_call_failed)}</td>
                      <td className="px-4 py-3 text-right text-error">{fmt(item.ai_call_failed)}</td>
                      <td className="px-4 py-3 text-right">{fmt(m?.ai_call_count)}</td>
                      <td className="px-4 py-3 text-right font-mono text-xs">{fmt(m?.total_prompt_tokens)}</td>
                      <td className="px-4 py-3 text-right font-mono text-xs">{fmt(m?.total_completion_tokens)}</td>
                      <td className="px-4 py-3 text-right font-medium font-mono text-xs">
                        {m ? fmt(m.total_prompt_tokens + m.total_completion_tokens) : '-'}
                      </td>
                      <td className="px-4 py-3 text-right">{fmt(m?.chunk_count)}</td>
                      <td className="px-4 py-3 text-right">{fmt(m?.file_count)}</td>
                      <td className="px-4 py-3 text-right text-xs text-muted">
                        {item.create_time ? new Date(item.create_time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted">共 {total} 条</span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-40"
                >
                  上一页
                </button>
                <span className="flex items-center px-3 text-sm text-muted">{page} / {totalPages}</span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
