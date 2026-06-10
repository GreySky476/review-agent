import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useReviewDetail, useReviewStats } from '@/hooks/use-reviews'
import { Skeleton, ErrorState, Badge, Button } from '@/components/ui/shared'
import { FindingCard } from '@/components/reviews/finding-card'
import { FileTree } from '@/components/reviews/file-tree'
import { CommentSection } from '@/components/reviews/comment-section'
import { cn } from '@/lib/utils'

const statusLabel: Record<string, string> = {
  completed: '已完成', pending: '等待中', running: '进行中', failed: '失败',
}

const categoryLabel: Record<string, string> = {
  security: '安全', bug: 'Bug', performance: '性能',
  style: '代码规范', dependency: '依赖', structure: '结构',
}

interface FileNode {
  path: string
  findingCount: number
  severityCounts: Record<string, number>
}

export function ReviewHistoryDetailPage() {
  const { reviewId } = useParams<{ reviewId: string }>()
  const navigate = useNavigate()
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null)
  const [showComments, setShowComments] = useState(false)

  const { data: review, isLoading, error, refetch } = useReviewDetail(reviewId!)
  const { data: stats } = useReviewStats()

  if (error) return <ErrorState message="评审详情加载失败" onRetry={refetch} />
  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-64" />
        <div className="flex gap-6">
          <Skeleton className="h-96 w-64" />
          <Skeleton className="h-96 flex-1" />
        </div>
      </div>
    )
  }
  if (!review || 'error' in review) {
    return <ErrorState message="评审不存在" onRetry={() => navigate('/reviews')} />
  }

  const sev = review.statistics?.severity ?? {}
  const cat = review.statistics?.category ?? {}
  const totalFindings = review.findings_count

  // Build file tree data for FindingCard compat
  const fileMap = new Map<string, { count: number; severities: Record<string, number> }>()
  for (const f of review.findings) {
    if (!fileMap.has(f.file_path)) {
      fileMap.set(f.file_path, { count: 0, severities: {} })
    }
    const entry = fileMap.get(f.file_path)!
    entry.count++
    entry.severities[f.severity] = (entry.severities[f.severity] || 0) + 1
  }
  const fileNodes: FileNode[] = Array.from(fileMap.entries()).map(([path, info]) => ({
    path, findingCount: info.count, severityCounts: info.severities,
  }))

  const filteredFindings = selectedFile
    ? review.findings.filter((f) => f.file_path === selectedFile)
    : review.findings

  const scoreColor = review.score != null
    ? review.score >= 90 ? 'text-success' : review.score >= 70 ? 'text-warning' : 'text-error'
    : 'text-muted'

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <button onClick={() => navigate('/reviews')} className="mb-2 text-sm text-muted hover:text-foreground">
          ← 返回评审历史
        </button>
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-foreground truncate">
              {review.pr_title || '评审详情'}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
              <span>{review.project_name}</span>
              <span className="text-xs text-muted-more">·</span>
              <span className="font-mono text-xs">{review.head_sha?.slice(0, 8) || '-'}</span>
              <span className="text-xs text-muted-more">·</span>
              <Badge variant={review.status === 'completed' ? 'success' : review.status === 'failed' ? 'error' : 'warning'}>
                {statusLabel[review.status] || review.status}
              </Badge>
              {review.duration_seconds != null && (
                <>
                  <span className="text-xs text-muted-more">·</span>
                  <span>耗时 {review.duration_seconds}s</span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <div className="text-right">
              <div className={cn('text-3xl font-bold', scoreColor)}>{review.score ?? '-'}</div>
              <div className="text-xs text-muted">/100</div>
            </div>
          </div>
        </div>
      </div>

      {/* Statistics Panel */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-xs font-medium text-muted-more mb-3">严重性分布</h3>
          <div className="space-y-2">
            {[
              { key: 'critical', label: 'Critical', color: 'text-error', bg: 'bg-error/10' },
              { key: 'warning', label: 'Warning', color: 'text-warning', bg: 'bg-warning/10' },
              { key: 'info', label: 'Info', color: 'text-info', bg: 'bg-info/10' },
            ].map(({ key, label, color, bg }) => (
              <div key={key} className="flex items-center gap-3">
                <span className={`w-16 text-xs font-medium ${color}`}>{label}</span>
                <div className="flex-1 h-2 rounded-full bg-stone-100">
                  <div className={`h-2 rounded-full ${bg} ${color.replace('text-', 'bg-')}`}
                    style={{ width: totalFindings > 0 ? `${((sev[key] ?? 0) / totalFindings) * 100}%` : '0%' }} />
                </div>
                <span className="w-6 text-right text-xs font-medium text-foreground">{sev[key] ?? 0}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-xs font-medium text-muted-more mb-3">类别分布</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(cat).map(([key, count]) => (
              <div key={key} className="flex items-center gap-1.5 rounded-md bg-stone-50 px-2.5 py-1.5">
                <span className="text-xs text-muted">{categoryLabel[key] || key}</span>
                <span className="text-xs font-bold text-foreground">{count}</span>
              </div>
            ))}
            {Object.keys(cat).length === 0 && <span className="text-xs text-muted">暂无数据</span>}
          </div>
        </div>
      </div>

      {/* File Tree + Findings */}
      <div className="flex gap-6">
        <div className="w-56 shrink-0 rounded-lg border border-border bg-surface p-3">
          <FileTree files={fileNodes} selectedFile={selectedFile} onSelect={setSelectedFile} />
        </div>
        <div className="min-w-0 flex-1 space-y-4">
          <div className="flex items-center justify-between">
            {selectedFile && (
              <button onClick={() => setSelectedFile(null)} className="text-xs text-muted hover:text-foreground">
                ← 显示所有文件
              </button>
            )}
            <Button variant="secondary" size="sm" onClick={() => setShowComments(!showComments)}>
              ◉ 评论 ({0})
            </Button>
          </div>
          {filteredFindings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-lg text-muted">该文件未发现问题</p>
            </div>
          ) : (
            filteredFindings.map((f) => (
              <FindingCard
                key={f.id}
                finding={f}
                selected={expandedFinding === f.id}
                onSelect={() => setExpandedFinding(f.id === expandedFinding ? null : f.id)}
                onFeedback={(action) => {
                  if (action === 'comment') setShowComments(true)
                }}
              />
            ))
          )}
        </div>
      </div>

      {/* Comments */}
      {showComments && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <CommentSection reviewId={reviewId!} />
        </div>
      )}
    </div>
  )
}
