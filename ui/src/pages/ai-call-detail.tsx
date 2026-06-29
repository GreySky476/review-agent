import { useParams, useNavigate } from 'react-router-dom'
import { useReviewDetail, useReviewAICalls } from '@/hooks/use-reviews'
import { Skeleton, ErrorState, Badge } from '@/components/ui/shared'

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString()
}

export function AICallDetailPage() {
  const { reviewId } = useParams<{ reviewId: string }>()
  const navigate = useNavigate()
  const { data: review, isLoading: loadingReview, error } = useReviewDetail(reviewId ?? '')
  const { data: aiCalls, isLoading: loadingCalls } = useReviewAICalls(reviewId ?? '')

  if (error) return <ErrorState message="加载失败" />
  if (loadingReview) return <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
  if (!review) return <ErrorState message="评审不存在" />

  const m = review.metrics
  const failedCount = aiCalls?.filter(c => c.status === 'failed').length ?? 0
  const successCount = (m?.ai_call_count ?? 0) - failedCount

  return (
    <div className="space-y-6">

      {/* Back navigation */}
      <button onClick={() => navigate('/tokens')} className="text-sm text-muted hover:text-foreground">
        ← 返回 Token 消耗列表
      </button>

      {/* Review header */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-foreground">
              {review.project_name || 'unknown'} {review.pr_number ? `#${review.pr_number}` : ''}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
              <span className="font-mono text-xs">{review.head_sha?.slice(0, 8) || '-'}</span>
              <Badge variant={
                review.status === 'completed' ? 'success' :
                review.status === 'completed_with_errors' ? 'warning' : 'error'
              }>
                {review.status}
              </Badge>
              <span>score: {review.score ?? '-'}/100</span>
              <span>findings: {review.findings_count}</span>
            </div>
          </div>
        </div>
      </div>

      {/* AI Call Summary */}
      {m && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">AI 调用汇总</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">总调用</div>
              <div className="mt-1 text-lg font-bold text-foreground">{m.ai_call_count}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">成功</div>
              <div className="mt-1 text-lg font-bold text-success">{successCount}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">失败</div>
              <div className="mt-1 text-lg font-bold text-error">{failedCount}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">成功率</div>
              <div className="mt-1 text-lg font-bold text-foreground">
                {m.ai_call_count > 0 ? `${((successCount / m.ai_call_count) * 100).toFixed(0)}%` : '-'}
              </div>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">Input Token</div>
              <div className="mt-1 text-lg font-bold text-foreground">{fmt(m.total_prompt_tokens)}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">Output Token</div>
              <div className="mt-1 text-lg font-bold text-foreground">{fmt(m.total_completion_tokens)}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">Total Token</div>
              <div className="mt-1 text-lg font-bold text-foreground">{fmt(m.total_prompt_tokens + m.total_completion_tokens)}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">流水线耗时</div>
              <div className="mt-1 text-lg font-bold text-foreground">
                {m.pipeline_duration_ms ? `${(m.pipeline_duration_ms / 1000).toFixed(1)}s` : '-'}
              </div>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">分块数</div>
              <div className="mt-1 text-lg font-bold text-foreground">{m.chunk_count}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">文件数</div>
              <div className="mt-1 text-lg font-bold text-foreground">{m.file_count}</div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">平均调用耗时</div>
              <div className="mt-1 text-lg font-bold text-foreground">
                {m.ai_call_count > 0 && m.pipeline_duration_ms
                  ? `${(m.pipeline_duration_ms / m.ai_call_count / 1000).toFixed(1)}s`
                  : '-'}
              </div>
            </div>
            <div className="rounded-md bg-stone-50 p-3">
              <div className="text-xs text-muted">发现数</div>
              <div className="mt-1 text-lg font-bold text-foreground">{review.findings_count}</div>
            </div>
          </div>
        </div>
      )}

      {/* AI Call Detail Table */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">AI 调用明细</h2>
        {loadingCalls ? (
          <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
        ) : !aiCalls?.length ? (
          <div className="py-8 text-center text-sm text-muted">暂无 AI 调用记录</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted">
                  <th className="pb-2 pr-4 font-medium">#</th>
                  <th className="pb-2 pr-4 font-medium">模型</th>
                  <th className="pb-2 pr-4 font-medium text-right">Input</th>
                  <th className="pb-2 pr-4 font-medium text-right">Output</th>
                  <th className="pb-2 pr-4 font-medium text-right">Total</th>
                  <th className="pb-2 pr-4 font-medium text-right">耗时</th>
                  <th className="pb-2 pr-4 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {aiCalls.map((call) => (
                  <tr key={call.id} className="border-b border-border/50">
                    <td className="py-2 pr-4 text-muted">{call.batch_idx + 1}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{call.model || 'deepseek-v4-flash'}</td>
                    <td className="py-2 pr-4 text-right font-mono text-xs">{fmt(call.prompt_tokens)}</td>
                    <td className="py-2 pr-4 text-right font-mono text-xs">{fmt(call.completion_tokens)}</td>
                    <td className="py-2 pr-4 text-right font-medium font-mono text-xs">{fmt(call.total_tokens)}</td>
                    <td className="py-2 pr-4 text-right">{(call.duration_ms / 1000).toFixed(1)}s</td>
                    <td className="py-2 pr-4">
                      <Badge variant={call.status === 'success' ? 'success' : 'error'}>
                        {call.status === 'success' ? '✅' : '❌'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  )
}
