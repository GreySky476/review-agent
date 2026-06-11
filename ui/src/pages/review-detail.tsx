import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { usePullRequestDetail } from '@/hooks/use-reviews'
import { Skeleton, ErrorState, Button } from '@/components/ui/shared'
import { FindingCard } from '@/components/reviews/finding-card'
import { FileTree } from '@/components/reviews/file-tree'
import { CommentSection } from '@/components/reviews/comment-section'
import { api } from '@/lib/api-client'
import { cn } from '@/lib/utils'

export function ReviewDetailPage() {
  const { id, prNumber } = useParams<{ id: string; prNumber: string }>()
  const navigate = useNavigate()
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [activeFindingId, setActiveFindingId] = useState<string | null>(null)
  const [showComments, setShowComments] = useState(false)

  const { data, isLoading, error, refetch } = usePullRequestDetail(
    id!,
    Number(prNumber),
  )

  const findings: any[] = data?.findings ?? []

  // Build file tree data
  const fileMap = new Map<string, { count: number; severities: Record<string, number> }>()
  for (const f of findings) {
    if (!fileMap.has(f.file_path)) {
      fileMap.set(f.file_path, { count: 0, severities: {} })
    }
    const entry = fileMap.get(f.file_path)!
    entry.count++
    entry.severities[f.severity] = (entry.severities[f.severity] || 0) + 1
  }
  const fileNodes = Array.from(fileMap.entries()).map(([path, info]) => ({
    path,
    findingCount: info.count,
    severityCounts: info.severities,
  }))

  const filteredFindings = selectedFile
    ? findings.filter((f: any) => f.file_path === selectedFile)
    : findings

  const handleFeedback = async (findingId: string, action: string) => {
    if (action === 'comment') {
      setShowComments(true)
      return
    }
    try {
      const reviewId = data?.reviews?.[0]?.id
      if (!reviewId) return
      await api.post(
        `/reviews/${reviewId}/findings/${findingId}/feedback`,
        { action },
      )
    } catch {
      // silently fail — feedback is non-critical
    }
  }

  if (error) {
    return <ErrorState message="评审详情加载失败" onRetry={refetch} />
  }

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

  const pr = data?.pull_request ?? {}
  const score = pr.review_score

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <button
          onClick={() => navigate(`/projects/${id}`)}
          className="mb-2 text-sm text-muted hover:text-foreground"
        >
          ← 返回项目
        </button>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              PR #{prNumber} {pr.title ? `— ${pr.title}` : ''}
            </h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-muted">
              <span>作者: {pr.author || '-'}</span>
              <span>·</span>
              {score != null && (
                <>
                  <span
                    className={cn(
                      'font-medium',
                      score >= 90 ? 'text-success' : score >= 70 ? 'text-warning' : 'text-error',
                    )}
                  >
                    评分: {score}/100
                  </span>
                  <span>·</span>
                </>
              )}
              <span>{findings.length} 个 Finding</span>
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setShowComments(!showComments)}>
            💬 评论 ({data?.comments?.length ?? 0})
          </Button>
        </div>
      </div>

      {/* Warning Banner for Partial Failure */}
      {data?.reviews?.[0]?.status === 'completed_with_errors' && (
        <div className="rounded-lg border border-warning bg-warning/10 p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg shrink-0">⚠️</span>
            <div>
              <p className="text-sm font-medium text-foreground">评审不完整</p>
              <p className="mt-1 text-sm text-muted">
                {data.reviews[0].error_message || '部分文件无法获取源码，评审结果不完整。'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Main split view */}
      <div className="flex gap-6">
        {/* File Tree (left) */}
        <div className="w-56 shrink-0 rounded-lg border border-border bg-surface p-3">
          <FileTree files={fileNodes} selectedFile={selectedFile} onSelect={setSelectedFile} />
        </div>

        {/* Findings (right) */}
        <div className="min-w-0 flex-1 space-y-4">
          {selectedFile && (
            <button
              onClick={() => setSelectedFile(null)}
              className="text-xs text-muted hover:text-foreground"
            >
              ← 显示所有文件
            </button>
          )}
          {filteredFindings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-lg text-muted">✅ 该文件未发现问题</p>
            </div>
          ) : (
            filteredFindings.map((f: any) => (
              <FindingCard
                key={f.id}
                finding={f}
                selected={activeFindingId === f.id}
                onSelect={() => setActiveFindingId(f.id === activeFindingId ? null : f.id)}
                onFeedback={(action) => handleFeedback(f.id, action)}
              />
            ))
          )}
        </div>
      </div>

      {/* Comments Section */}
      {showComments && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <CommentSection reviewId={data?.reviews?.[0]?.id ?? ''} />
        </div>
      )}
    </div>
  )
}
