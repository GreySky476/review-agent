import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'

const navItems = [
  { to: '/dashboard', label: '仪表盘', icon: '◉' },
  { to: '/projects', label: '项目', icon: '◈' },
  { to: '/tokens', label: 'Token 消耗', icon: '◆' },
  { to: '/rules', label: '评审规则', icon: '◇' },
  { to: '/errors', label: '异常监控', icon: '▲' },
]

export function Sidebar() {
  const { sidebar } = useUIStore()
  const collapsed = sidebar === 'collapsed'

  return (
    <aside
      className={cn(
        'flex flex-col border-r border-border bg-surface transition-all duration-200',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          'flex h-16 items-center border-b border-border px-4',
          collapsed && 'justify-center px-0',
        )}
      >
        {collapsed ? (
          <span className="text-xl font-bold text-primary">R</span>
        ) : (
          <span className="text-lg font-bold text-foreground">
            <span className="text-primary">Review</span>Agent
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-amber-50 text-amber-700'
                  : 'text-muted hover:bg-stone-50 hover:text-foreground',
                collapsed && 'justify-center px-2',
              )
            }
          >
            <span className="text-lg">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-border p-3">
        <button
          onClick={() => useUIStore.getState().toggleSidebar()}
          className="flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
        >
          {collapsed ? '→' : '← 收起'}
        </button>
      </div>
    </aside>
  )
}
