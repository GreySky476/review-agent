import { useState } from 'react'
import { useComments, useCreateComment, type Comment } from '@/hooks/use-comments'
import { Skeleton, EmptyState, ErrorState } from '@/components/ui/shared'
import { formatRelativeTime } from '@/lib/utils'

interface CommentSectionProps {
  reviewId: string
  findingId?: string
}

export function CommentSection({ reviewId, findingId }: CommentSectionProps) {
  const { data: comments, isLoading, error, refetch } = useComments(reviewId)
  const createComment = useCreateComment(reviewId)
  const [newComment, setNewComment] = useState('')
  const [author, setAuthor] = useState('')

  const filteredComments = findingId
    ? comments?.filter((c) => c.finding_id === findingId)
    : comments

  const handleSubmit = async () => {
    if (!newComment.trim() || !author.trim()) return
    try {
      await createComment.mutateAsync({
        finding_id: findingId,
        author,
        content: newComment,
      })
      setNewComment('')
    } catch {
      // Error handled by mutation
    }
  }

  if (error) {
    return <ErrorState message="评论加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-foreground">
        评论
        {filteredComments && (
          <span className="ml-1 text-muted-more">({filteredComments.length})</span>
        )}
      </h4>

      {isLoading ? (
        Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-16" />)
      ) : !filteredComments?.length ? (
        <EmptyState title="暂无评论" />
      ) : (
        <div className="space-y-2">
          {filteredComments.map((comment: Comment) => (
            <div
              key={comment.id}
              className="rounded-lg border border-border bg-surface p-3"
            >
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium text-foreground">{comment.author}</span>
                {comment.action === 'accepted' && (
                  <span className="text-xs text-success">✅ 已采纳</span>
                )}
                {comment.action === 'invalid' && (
                  <span className="text-xs text-error">❌ 已标为无效</span>
                )}
                <span className="ml-auto text-xs text-muted-more">
                  {formatRelativeTime(comment.create_time)}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted">{comment.content}</p>
            </div>
          ))}
        </div>
      )}

      {/* Add Comment */}
      <div className="space-y-2 rounded-lg border border-border bg-surface p-3">
        <input
          type="text"
          placeholder="你的名字..."
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
          className="w-full rounded border border-border bg-surface-alt px-3 py-1.5 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none"
        />
        <textarea
          placeholder="输入评论..."
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          rows={2}
          className="w-full rounded border border-border bg-surface-alt px-3 py-1.5 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none resize-none"
        />
        <button
          onClick={handleSubmit}
          disabled={!newComment.trim() || !author.trim() || createComment.isPending}
          className="rounded bg-primary px-4 py-1.5 text-sm font-medium text-on-primary transition-colors hover:bg-primary-hover disabled:opacity-50"
        >
          {createComment.isPending ? '发送中...' : '发送'}
        </button>
      </div>
    </div>
  )
}
