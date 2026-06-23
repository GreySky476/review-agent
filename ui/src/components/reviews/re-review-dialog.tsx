import { useState } from 'react'
import { Button } from '@/components/ui/shared'

interface ReviewedFileInfo {
  path: string
  max_severity: string | null
}

interface ReReviewDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: (skipLevels: string) => void
  commitSha: string
  reviewedFiles?: ReviewedFileInfo[] | null
}

export function ReReviewDialog({
  open,
  onClose,
  onConfirm,
  commitSha,
  reviewedFiles,
}: ReReviewDialogProps) {
  const [skipCritical, setSkipCritical] = useState(false)
  const [skipWarning, setSkipWarning] = useState(false)
  const [skipInfo, setSkipInfo] = useState(true)
  const [skipClean, setSkipClean] = useState(true)

  if (!open) return null

  // Count files by severity
  const counts = { critical: 0, warning: 0, info: 0, clean: 0 }
  for (const f of reviewedFiles ?? []) {
    if (f.max_severity === 'critical') counts.critical++
    else if (f.max_severity === 'warning') counts.warning++
    else if (f.max_severity === 'info') counts.info++
    else counts.clean++
  }

  const handleConfirm = () => {
    const levels: string[] = []
    if (skipCritical) levels.push('critical')
    if (skipWarning) levels.push('warning')
    if (skipInfo) levels.push('info')
    if (skipClean) levels.push('clean')
    onConfirm(levels.join(','))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg">
        <h2 className="text-lg font-bold text-foreground mb-1">
          重新评审 <span className="font-mono text-primary">{commitSha.slice(0, 8)}</span>
        </h2>
        <p className="text-sm text-muted mb-4">
          选择本次需要跳过（不评审）的文件级别：
        </p>

        <div className="space-y-3">
          <label className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm cursor-pointer hover:bg-surface-hover/50">
            <input type="checkbox" checked={skipCritical} onChange={(e) => setSkipCritical(e.target.checked)} className="accent-primary" />
            <div className="flex-1">
              <span className="text-error font-medium">Critical</span>
              <span className="text-muted ml-2">({counts.critical} 个文件，需验证修复)</span>
            </div>
          </label>

          <label className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm cursor-pointer hover:bg-surface-hover/50">
            <input type="checkbox" checked={skipWarning} onChange={(e) => setSkipWarning(e.target.checked)} className="accent-primary" />
            <div className="flex-1">
              <span className="text-warning font-medium">Warning</span>
              <span className="text-muted ml-2">({counts.warning} 个文件，需验证修复)</span>
            </div>
          </label>

          <label className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm cursor-pointer hover:bg-surface-hover/50">
            <input type="checkbox" checked={skipInfo} onChange={(e) => setSkipInfo(e.target.checked)} className="accent-primary" />
            <div className="flex-1">
              <span className="text-info font-medium">Info</span>
              <span className="text-muted ml-2">({counts.info} 个文件，低优先级)</span>
            </div>
          </label>

          <label className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm cursor-pointer hover:bg-surface-hover/50">
            <input type="checkbox" checked={skipClean} onChange={(e) => setSkipClean(e.target.checked)} className="accent-primary" />
            <div className="flex-1">
              <span className="text-muted font-medium">无问题</span>
              <span className="text-muted ml-2">({counts.clean} 个文件，已通过)</span>
            </div>
          </label>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>取消</Button>
          <Button variant="primary" size="sm" onClick={handleConfirm}>确认评审</Button>
        </div>
      </div>
    </div>
  )
}
