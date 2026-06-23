import { Button } from '@/components/ui/shared'

interface ForceReviewDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  prNumber: number
}

export function ForceReviewDialog({
  open,
  onClose,
  onConfirm,
  prNumber,
}: ForceReviewDialogProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg">
        <h2 className="text-lg font-bold text-foreground mb-1">
          强制重审 PR #{prNumber}
        </h2>
        <p className="text-sm text-muted mb-4">
          强制重审将忽略所有之前的评审状态，对 PR 的所有 commit 重新执行完整评审。
          此操作不可撤销，评审将消耗 AI 调用额度。
        </p>

        <div className="rounded-lg border border-warning bg-warning/10 p-3 text-sm text-warning mb-4">
          当前所有已有评审记录不会被删除，新的评审记录将追加到时间线中。
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>取消</Button>
          <Button variant="primary" size="sm" onClick={onConfirm}>确认强制重审</Button>
        </div>
      </div>
    </div>
  )
}
