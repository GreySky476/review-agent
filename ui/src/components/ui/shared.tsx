import { type ComponentProps, forwardRef } from 'react'
import { cn } from '@/lib/utils'

/* ── Skeleton ─────────────────────────────────────────────── */
export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-surface', className)}
      {...props}
    />
  )
}

/* ── Badge ─────────────────────────────────────────────────── */
interface BadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'purple'
  children: React.ReactNode
  className?: string
}

const badgeVariants: Record<string, string> = {
  default: 'bg-gray-500/10 text-gray-400 border-gray-500/30',
  success: 'bg-green-500/10 text-green-500 border-green-500/30',
  warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
  error: 'bg-red-500/10 text-red-500 border-red-500/30',
  info: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  purple: 'bg-purple-500/10 text-purple-500 border-purple-500/30',
}

export function Badge({ variant = 'default', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        badgeVariants[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}

/* ── StatCard ──────────────────────────────────────────────── */
interface StatCardProps {
  title: string
  value: string | number
  icon?: React.ReactNode
  trend?: { value: number; positive: boolean }
  className?: string
}

export function StatCard({ title, value, icon, trend, className }: StatCardProps) {
  return (
    <div className={cn('rounded-lg border border-border bg-surface p-5', className)}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted">{title}</p>
          <p className="mt-1 text-3xl font-bold tracking-tight text-foreground">
            {value}
          </p>
          {trend && (
            <p
              className={cn(
                'mt-1 text-xs',
                trend.positive ? 'text-success' : 'text-error',
              )}
            >
              {trend.positive ? '↑' : '↓'} {trend.value}%
            </p>
          )}
        </div>
        {icon && <div className="text-muted-more">{icon}</div>}
      </div>
    </div>
  )
}

/* ── EmptyState ────────────────────────────────────────────── */
interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="mb-4 text-muted-more">{icon}</div>}
      <h3 className="text-lg font-medium text-foreground">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/* ── ErrorState ────────────────────────────────────────────── */
interface ErrorStateProps {
  message?: string
  onRetry?: () => void
}

export function ErrorState({
  message = '加载失败，请稍后重试',
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 text-2xl text-error">⚠</div>
      <h3 className="text-lg font-medium text-foreground">出错了</h3>
      <p className="mt-1 text-sm text-muted">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary transition-colors hover:bg-primary-hover"
        >
          重试
        </button>
      )}
    </div>
  )
}

/* ── PlatformBadge ─────────────────────────────────────────── */
interface PlatformBadgeProps {
  platform: 'github' | 'gitlab' | 'gitee'
}

const platformConfig = {
  github: { label: 'GitHub', color: 'text-github' },
  gitlab: { label: 'GitLab', color: 'text-gitlab' },
  gitee: { label: 'Gitee', color: 'text-gitee' },
}

export function PlatformBadge({ platform }: PlatformBadgeProps) {
  const cfg = platformConfig[platform]
  return (
    <span className={cn('inline-flex items-center gap-1 text-sm font-medium', cfg.color)}>
      <span className="inline-block h-3 w-3 rounded-full bg-current" />
      {cfg.label}
    </span>
  )
}

/* ── StatusDot / WebhookStatus ────────────────────────────── */
interface StatusDotProps {
  status: 'connected' | 'disconnected' | 'pending'
}

const dotConfig: Record<string, string> = {
  connected: 'bg-success shadow-[0_0_6px_rgba(16,185,129,0.5)]',
  disconnected: 'bg-error shadow-[0_0_6px_rgba(239,68,68,0.5)]',
  pending: 'bg-warning shadow-[0_0_6px_rgba(245,158,11,0.5)]',
}

export function WebhookStatus({
  status,
}: {
  status: string
}) {
  const config: Record<string, { dot: string; label: string; description?: string }> = {
    connected: {
      dot: 'connected',
      label: '已连接',
    },
    never_connected: {
      dot: 'pending',
      label: '等待连接',
      description: 'Webhook 已启用但未收到任何事件',
    },
    inactive: {
      dot: 'pending',
      label: '连接超时',
      description: '超过 24 小时未收到 Webhook 事件',
    },
    disconnected: {
      dot: 'disconnected',
      label: '未连接',
    },
  }
  const cfg = config[status] || { dot: 'disconnected', label: status }
  return (
    <span className="inline-flex items-center gap-1.5" title={cfg.description}>
      <span
        className={cn(
          'inline-block h-2 w-2 rounded-full',
          dotConfig[cfg.dot] || dotConfig.disconnected,
        )}
      />
      <span className="text-sm text-muted">{cfg.label}</span>
    </span>
  )
}

/* ── Button ────────────────────────────────────────────────── */
interface ButtonProps extends ComponentProps<'button'> {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          variant === 'primary' &&
            'bg-primary text-on-primary hover:bg-primary-hover',
          variant === 'secondary' &&
            'border border-border bg-surface text-foreground hover:bg-surface-hover',
          variant === 'ghost' && 'text-muted hover:text-foreground hover:bg-surface',
          size === 'sm' && 'px-2.5 py-1.5 text-xs',
          size === 'md' && 'px-4 py-2 text-sm',
          size === 'lg' && 'px-6 py-3 text-base',
          className,
        )}
        {...props}
      >
        {children}
      </button>
    )
  },
)
Button.displayName = 'Button'
