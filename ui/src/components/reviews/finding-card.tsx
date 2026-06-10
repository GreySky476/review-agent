import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/shared'

export interface FindingData {
  id: string
  file_path: string
  line_start: number | null
  line_end: number | null
  category: string
  severity: string
  title: string
  description: string
  suggestion: string
  is_valid: boolean
}

const severityConfig: Record<string, { label: string; variant: 'error' | 'warning' | 'info'; icon: string }> = {
  critical: { label: 'Critical', variant: 'error', icon: '🔴' },
  warning: { label: 'Warning', variant: 'warning', icon: '🟡' },
  info: { label: 'Info', variant: 'info', icon: '🔵' },
}

const categoryLabels: Record<string, string> = {
  security: '安全',
  bug: 'Bug',
  performance: '性能',
  style: '代码规范',
  dependency: '依赖',
  structure: '结构',
}

interface FindingCardProps {
  finding: FindingData
  selected?: boolean
  onSelect?: () => void
  onFeedback?: (action: 'accepted' | 'invalid' | 'comment') => void
}

export function FindingCard({ finding, selected, onSelect, onFeedback }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false)
  const sev = severityConfig[finding.severity] ?? severityConfig.info

  return (
    <div
      className={cn(
        'rounded-lg border transition-colors',
        selected ? 'border-amber-500 bg-amber-50/40' : 'border-border bg-surface',
        'cursor-pointer',
      )}
      onClick={() => {
        setExpanded(!expanded)
        onSelect?.()
      }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <span className="mt-0.5 text-sm">{sev.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge variant={sev.variant}>{sev.label}</Badge>
            <Badge variant="default">{categoryLabels[finding.category] || finding.category}</Badge>
            <span className="text-xs text-muted-more font-mono">
              {finding.file_path}:{finding.line_start ?? '?'}
            </span>
          </div>
          <h4 className="mt-1 text-sm font-medium text-foreground">{finding.title}</h4>
        </div>
        <span className="text-xs text-muted-more">{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded Detail */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3 space-y-3">
          <p className="text-sm text-muted leading-relaxed">{finding.description}</p>
          {finding.suggestion && (
            <div className="rounded-md bg-surface-alt p-3">
              <p className="text-xs text-muted-more mb-1">💡 建议</p>
              <p className="text-sm text-foreground">{finding.suggestion}</p>
            </div>
          )}
          {onFeedback && (
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={(e) => { e.stopPropagation(); onFeedback('accepted') }}
                className="rounded px-2.5 py-1 text-xs font-medium text-success hover:bg-success/10 transition-colors"
              >
                ✅ 采纳
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onFeedback('invalid') }}
                className="rounded px-2.5 py-1 text-xs font-medium text-muted hover:text-error hover:bg-error/10 transition-colors"
              >
                ❌ 无效
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onFeedback('comment') }}
                className="rounded px-2.5 py-1 text-xs font-medium text-info hover:bg-info/10 transition-colors"
              >
                💬 评论
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
