import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { usePullRequestDetail, useReviewDetail, useSyncPullRequest, useTriggerPRReview } from '@/hooks/use-reviews'
import { useTriggerCommitReview } from '@/hooks/use-commits'
import { Skeleton, ErrorState, Badge, Button } from '@/components/ui/shared'
import { FindingCard } from '@/components/reviews/finding-card'
import { FileTree } from '@/components/reviews/file-tree'
import { CommentSection } from '@/components/reviews/comment-section'
import { ReReviewDialog } from '@/components/reviews/re-review-dialog'
import { ForceReviewDialog } from '@/components/reviews/force-review-dialog'
import { cn } from '@/lib/utils'

const reviewStatusLabel: Record<string, string> = {
  completed: '已完成', pending: '等待中', running: '进行中', failed: '失败',
  completed_with_errors: '已完成（有异常）',
}

const categoryLabel: Record<string, string> = {
  security: '安全', bug: 'Bug', performance: '性能',
  style: '代码规范', dependency: '依赖', structure: '结构',
}

/* ── PR 状态徽章 ─────────────────────────────────────────────── */
function PRStateBadge({ state, isMerged }: { state: string; isMerged: boolean }) {
  if (isMerged) return <Badge variant="purple">Merged</Badge>
  if (state === 'open') return <Badge variant="success">Open</Badge>
  return <Badge variant="default">Closed</Badge>
}

/* ── 时间辅助函数 ──────────────────────────────────────────── */
function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const now = Date.now()
  const d = new Date(dateStr).getTime()
  const diff = Math.floor((now - d) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

/* ── Commit 时间线条目 ─────────────────────────────────────── */
interface CommitEntry {
  sha: string
  message: string
  author: string | null
  date: string | null
  review_id: string | null
  review_status: string | null
  review_score: number | null
  reviewed_files?: Array<{ path: string; max_severity: string | null }> | null
}

const statusDot: Record<string, string> = {
  completed: 'text-success',
  completed_with_errors: 'text-warning',
  running: 'text-info',
  pending: 'text-warning',
  failed: 'text-error',
}

const statusLabel: Record<string, { label: string; variant: 'success' | 'warning' | 'info' | 'error' | 'default' }> = {
  completed: { label: '已完成', variant: 'success' },
  running: { label: '进行中', variant: 'info' },
  pending: { label: '等待中', variant: 'warning' },
  failed: { label: '失败', variant: 'error' },
  completed_with_errors: { label: '已完成（有异常）', variant: 'warning' },
}

function severityBadgeColor(sev: string | null): 'error' | 'warning' | 'success' {
  if (sev === 'critical') return 'error'
  if (sev === 'warning') return 'warning'
  return 'success'
}

function TimelineEntry({
  commit,
  projectId,
  prNumber,
  onReview,
  onReReview,
}: {
  commit: CommitEntry
  projectId: string
  prNumber: string
  onReview: (sha: string) => void
  onReReview: (sha: string, reviewedFiles: CommitEntry['reviewed_files']) => void
}) {
  const navigate = useNavigate()
  const sha8 = commit.sha.slice(0, 8)
  const hasReview = !!commit.review_id && !!commit.review_status
  const cfg = hasReview ? (statusLabel[commit.review_status!] || { label: commit.review_status, variant: 'default' as const }) : null
  const reviewedFiles = commit.reviewed_files ?? []
  const hasIssues = reviewedFiles.some((f) => f.max_severity !== null)
  const isReviewed = hasReview && cfg && cfg.variant !== 'error'

  return (
    <div className="rounded-lg border border-border bg-surface p-4 transition-colors hover:bg-surface-hover/50">
      <div className="flex items-start justify-between gap-4">
        {/* Left: SHA + message + meta */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`block h-3 w-3 shrink-0 rounded-full ${hasReview ? (statusDot[commit.review_status!] || 'text-muted') : 'text-stone-300'}`} />
            <span className="font-mono text-xs font-bold text-primary">{sha8}</span>
            <span className="truncate text-sm font-medium text-foreground">{commit.message || '(无提交信息)'}</span>
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs text-muted">
            <span>{commit.author || '未知作者'}</span>
            <span>{timeAgo(commit.date)}</span>
            {cfg && (
              <>
                <Badge variant={cfg.variant}>{cfg.label}</Badge>
                {commit.review_score != null && (
                  <span className={cn(
                    'font-medium',
                    commit.review_score >= 90 ? 'text-success' : commit.review_score >= 70 ? 'text-warning' : 'text-error',
                  )}>
                    评分 {commit.review_score}
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        {/* Right: actions */}
        <div className="flex shrink-0 items-center gap-2">
          {isReviewed && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(`/projects/${projectId}/reviews/${commit.review_id}?from_pr=${prNumber}`)}
            >
              📋 查看详情
            </Button>
          )}
          {!hasReview && (
            <Button
              variant="primary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onReview(commit.sha)
              }}
            >
              🚀 评审
            </Button>
          )}
          {isReviewed && (
            <Button
              variant="secondary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onReReview(commit.sha, commit.reviewed_files)
              }}
            >
              🔁 重新评审
            </Button>
          )}
        </div>
      </div>

      {/* Severity breakdown */}
      {hasIssues && (
        <div className="mt-2 ml-5 flex flex-wrap gap-2">
          {reviewedFiles.filter((f) => f.max_severity !== null).map((f) => (
            <Badge key={f.path} variant={severityBadgeColor(f.max_severity)}>
              <span className={f.max_severity === 'critical' ? 'text-error' : f.max_severity === 'warning' ? 'text-warning' : 'text-success'}>●</span>
              {' '}{f.path.split('/').pop()} — {f.max_severity?.toUpperCase()}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── PR Mode (Commit Timeline) ──────────────────────────────── */
function PRReviewContent({
  projectId,
  prNumber,
}: {
  projectId: string
  prNumber: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isPolling, setIsPolling] = useState(false)
  const [skipReason, setSkipReason] = useState<string | null>(null)
  const [forceReviewOpen, setForceReviewOpen] = useState(false)
  const [reReviewSha, setReReviewSha] = useState<string | null>(null)
  const [reReviewFiles, setReReviewFiles] = useState<CommitEntry['reviewed_files']>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reReviewShaRef = useRef<string | null>(null)

  const { data, isLoading, error, refetch } = usePullRequestDetail(
    projectId,
    Number(prNumber),
  )

  const { mutate: triggerReview, isPending: isTriggering } = useTriggerPRReview(
    projectId,
    Number(prNumber),
  )

  const { mutate: syncCommits, isPending: isSyncing } = useSyncPullRequest(
    projectId,
    Number(prNumber),
  )

  const commitMutation = useTriggerCommitReview(projectId)

  const commits: CommitEntry[] = data?.commits ?? []
  const pr = data?.pull_request ?? {}
  const hasCommits = commits.length > 0

  // Build a review map from the reviews array for finding details
  const reviewBySha = new Map<string, any>()
  for (const rv of (data?.reviews ?? [])) {
    if (rv.head_sha && !reviewBySha.has(rv.head_sha)) {
      reviewBySha.set(rv.head_sha, rv)
    }
  }
  // Enrich commits with reviewed_files from matching review
  const enrichedCommits = commits.map((c: any) => {
    const matchingReview = reviewBySha.get(c.sha)
    return {
      ...c,
      reviewed_files: c.reviewed_files || matchingReview?.reviewed_files || null,
    }
  })

  // Poll PR detail after trigger until latest review completes
  useEffect(() => {
    if (!isPolling) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
      return
    }

    // 同步 ref，setInterval 闭包能读到最新的 reReviewSha
    reReviewShaRef.current = reReviewSha

    pollingRef.current = setInterval(async () => {
      const result = await refetch()

      // 检查 commit 级别的 review（pr_number=None，不在 reviews 数组中）
      const targetedSha = reReviewShaRef.current
      if (targetedSha) {
        const commitsList: any[] = result.data?.commits ?? []
        const targeted = commitsList.find((c: any) => c.sha === targetedSha)
        if (
          targeted &&
          targeted.review_status &&
          targeted.review_status !== 'pending' &&
          targeted.review_status !== 'running'
        ) {
          setIsPolling(false)
          return
        }
      }

      // 同时检查 PR 级别的 review
      const items: any[] = result.data?.reviews ?? []
      const latest = items[items.length - 1]
      if (latest && latest.status !== 'pending' && latest.status !== 'running') {
        setIsPolling(false)
      }
    }, 3000)

    const timeout = setTimeout(() => setIsPolling(false), 300_000)

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
      clearTimeout(timeout)
    }
  }, [isPolling, refetch])

  const handlePRTrigger = (force = false) => {
    setSkipReason(null)
    triggerReview(force ? true : undefined, {
      onSuccess: (resp: any) => {
        if (resp?.status === 'skipped') {
          setSkipReason(resp.reason || 'SHA 未变更，无需重新评审')
        } else {
          setIsPolling(true)
        }
      },
    })
  }

  const handleForceReview = () => {
    setForceReviewOpen(false)
    handlePRTrigger(true)
  }

  const handleReview = (sha: string) => {
    commitMutation.mutate(
      { sha, force: false, skipLevels: '' },
      {
        onSuccess: () => setIsPolling(true),
        onError: (err: any) => {
          const msg = err?.response?.data?.reason || err?.message || ''
          if (msg === 'review_in_progress') {
            alert('该 commit 已有评审正在执行中')
          }
        },
      },
    )
  }

  const handleReReview = (sha: string, reviewedFiles: CommitEntry['reviewed_files']) => {
    setReReviewSha(sha)
    setReReviewFiles(reviewedFiles)
  }

  const handleReReviewConfirm = (skipLevels: string) => {
    if (!reReviewSha) return
    commitMutation.mutate(
      { sha: reReviewSha, force: true, skipLevels },
      {
        onSuccess: () => {
          setIsPolling(true)
          queryClient.invalidateQueries({
            queryKey: ['pull-request', projectId, Number(prNumber)],
          })
        },
        onError: (err: any) => {
          const msg = err?.response?.data?.reason || err?.message || ''
          if (msg === 'review_in_progress') {
            alert('该 commit 已有评审正在执行中')
          }
        },
      },
    )
    setReReviewSha(null)
    setReReviewFiles(null)
  }

  if (error) {
    return <ErrorState message="PR 详情加载失败" onRetry={refetch} />
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-6 w-96" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <button
          onClick={() => navigate(`/projects/${projectId}`)}
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
              <PRStateBadge state={pr.state} isMerged={pr.is_merged} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              onClick={() => handlePRTrigger(false)}
              disabled={isTriggering || isPolling}
            >
              {isTriggering ? '⏳ 提交中...' : isPolling ? '⏳ 执行中...' : '🚀 PR触发评审'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setForceReviewOpen(true)}
              disabled={isTriggering || isPolling}
            >
              🔄 强制重审
            </Button>
            {hasCommits && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => window.open(`/api/v1/projects/${projectId}/pull-requests/${prNumber}/export/md`)}
              >
                📥 导出 MD
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => syncCommits()}
              disabled={isSyncing}
            >
              {isSyncing ? '⏳ 同步中...' : '🔄 刷新'}
            </Button>
          </div>
        </div>
      </div>

      {/* Warning Banner */}
      {(data?.reviews ?? []).some((r: any) => r.status === 'completed_with_errors') && (
        <div className="rounded-lg border border-warning bg-warning/10 p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg shrink-0">⚠️</span>
            <div>
              <p className="text-sm font-medium text-foreground">部分评审不完整</p>
              <p className="mt-1 text-sm text-muted">某些 commit 的评审存在异常，结果可能不完整。</p>
            </div>
          </div>
        </div>
      )}

      {/* Skip reason banner */}
      {skipReason && (
        <div className="rounded-lg border border-border bg-surface/50 p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg shrink-0">ℹ️</span>
            <div className="flex-1">
              <p className="text-sm text-muted">{skipReason}</p>
              <p className="mt-1 text-xs text-muted-more">
                SHA 无变更时自动跳过，如需强制重新评审请使用"强制重审"按钮
              </p>
            </div>
            <button
              onClick={() => setSkipReason(null)}
              className="text-xs text-muted hover:text-foreground"
            >
              关闭
            </button>
          </div>
        </div>
      )}

      {/* Polling progress */}
      {isPolling && (
        <div className="flex items-center justify-center gap-3 rounded-lg border border-border bg-surface/50 py-8 text-sm text-muted">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span>评审执行中，请稍候...</span>
        </div>
      )}

      {/* Commit Timeline */}
      {!hasCommits && !isPolling ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-lg text-muted mb-2">暂无评审记录</p>
          <p className="text-sm text-muted mb-6">
            点击上方按钮触发 AI 代码评审
          </p>
        </div>
      ) : hasCommits ? (
        <div className="space-y-3">
          {enrichedCommits.map((c: CommitEntry) => (
            <TimelineEntry
              key={c.sha}
              commit={c}
              projectId={projectId}
              prNumber={prNumber}
              onReview={handleReview}
              onReReview={handleReReview}
            />
          ))}
        </div>
      ) : null}

      {/* Force Review Dialog */}
      <ForceReviewDialog
        open={forceReviewOpen}
        onClose={() => setForceReviewOpen(false)}
        onConfirm={handleForceReview}
        prNumber={Number(prNumber)}
      />

      {/* Re-review Dialog */}
      <ReReviewDialog
        open={!!reReviewSha}
        onClose={() => { setReReviewSha(null); setReReviewFiles(null) }}
        onConfirm={handleReReviewConfirm}
        commitSha={reReviewSha || ''}
        reviewedFiles={reReviewFiles}
      />
    </div>
  )
}

/* ── Review Mode (from /projects/:id/reviews/:reviewId) ────── */
function SingleReviewContent({ reviewId }: { reviewId: string }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const fromPr = searchParams.get('from_pr')
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null)
  const [showComments, setShowComments] = useState(false)

  const { data: review, isLoading, error, refetch } = useReviewDetail(reviewId)

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
    return <ErrorState message="评审不存在" />
  }

  const sev = review.statistics?.severity ?? {}
  const cat = review.statistics?.category ?? {}
  const totalFindings = review.findings_count

  // Build file tree data
  const fileMap = new Map<string, { count: number; severities: Record<string, number> }>()
  for (const f of review.findings) {
    if (!fileMap.has(f.file_path)) {
      fileMap.set(f.file_path, { count: 0, severities: {} })
    }
    const entry = fileMap.get(f.file_path)!
    entry.count++
    entry.severities[f.severity] = (entry.severities[f.severity] || 0) + 1
  }
  const fileNodes = Array.from(fileMap.entries()).map(([path, info]) => ({
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
        <button
          onClick={() => navigate(
            fromPr
              ? `/projects/${review.project_id}/prs/${fromPr}`
              : review.pr_number != null
                ? `/projects/${review.project_id}/prs/${review.pr_number}`
                : `/projects/${review.project_id}`,
          )}
          className="mb-2 text-sm text-muted hover:text-foreground"
        >
          ← 返回项目
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
              <Badge variant={
                review.status === 'completed' ? 'success' :
                review.status === 'completed_with_errors' ? 'warning' :
                review.status === 'failed' ? 'error' : 'warning'
              }>
                {reviewStatusLabel[review.status] || review.status}
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

      {/* Warning Banner for Partial Failure */}
      {review.status === 'completed_with_errors' && (
        <div className="rounded-lg border border-warning bg-warning/10 p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg shrink-0">⚠️</span>
            <div>
              <p className="text-sm font-medium text-foreground">评审不完整</p>
              <p className="mt-1 text-sm text-muted">
                {review.error_message || '部分文件无法获取源码，评审结果不完整。'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Empty Review (completed, no findings) */}
      {review.status === 'completed' && review.findings_count === 0 && !review.error_message && (
        <div className="rounded-lg border border-success bg-success/10 p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg shrink-0">✅</span>
            <div>
              <p className="text-sm font-medium text-foreground">未发现问题</p>
              <p className="mt-1 text-sm text-muted">该次评审未检测到任何问题。</p>
            </div>
          </div>
        </div>
      )}

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
            <div className="flex items-center gap-2 ml-auto">
              <Button variant="secondary" size="sm" onClick={() => setShowComments(!showComments)}>
                ◉ 评论 ({0})
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => window.open(`/api/v1/reviews/${reviewId}/export/md`)}
              >
                📥 导出 MD
              </Button>
            </div>
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
          <CommentSection reviewId={reviewId} />
        </div>
      )}
    </div>
  )
}

/* ── Main Export ───────────────────────────────────────────── */
export function ReviewDetailPage() {
  const { id, prNumber, reviewId } = useParams<{ id: string; prNumber: string; reviewId: string }>()

  // PR context: /projects/:id/prs/:prNumber
  if (prNumber && id) {
    return <PRReviewContent projectId={id} prNumber={prNumber} />
  }

  // Review context: /projects/:id/reviews/:reviewId
  if (reviewId) {
    return <SingleReviewContent reviewId={reviewId} />
  }

  return <ErrorState message="无效的访问路径" />
}
