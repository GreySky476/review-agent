import { useLocation } from 'react-router-dom'

const breadcrumbMap: Record<string, string> = {
  dashboard: '仪表盘',
  projects: '项目',
  errors: '异常监控',
}

export function Header() {
  const location = useLocation()
  const segments = location.pathname.split('/').filter(Boolean)

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-surface px-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted">
        {segments.length > 0 ? (
          segments.map((seg, i) => {
            const label = breadcrumbMap[seg] || seg
            const isLast = i === segments.length - 1
            return (
              <span key={seg} className="flex items-center gap-2">
                {i > 0 && <span>/</span>}
                <span className={isLast ? 'text-foreground' : ''}>{label}</span>
              </span>
            )
          })
        ) : (
          <span className="text-foreground">仪表盘</span>
        )}
      </nav>

      {/* Right area */}
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted">管理后台</span>
      </div>
    </header>
  )
}
