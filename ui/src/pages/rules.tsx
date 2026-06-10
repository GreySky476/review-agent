import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import { Skeleton, ErrorState, EmptyState, Badge, Button } from '@/components/ui/shared'

interface Rule {
  id: string
  name: string
  content: string
  category: string
  severity: string
  languages: string
  tags: string
  version: number
  is_active: boolean
  create_time: string | null
}

const categoryOptions = [
  { value: 'security', label: '安全' },
  { value: 'bug', label: 'Bug' },
  { value: 'performance', label: '性能' },
  { value: 'style', label: '代码规范' },
  { value: 'dependency', label: '依赖' },
  { value: 'structure', label: '结构' },
]

const severityOptions = [
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
]

export function RulesPage() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<Rule | null>(null)
  const [form, setForm] = useState({ name: '', content: '', category: 'style', severity: 'warning', languages: '["python"]' })
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false)
  const [severityDropdownOpen, setSeverityDropdownOpen] = useState(false)
  const categoryDropdownRef = useRef<HTMLDivElement>(null)
  const severityDropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (categoryDropdownRef.current && !categoryDropdownRef.current.contains(e.target as Node)) {
        setCategoryDropdownOpen(false)
      }
      if (severityDropdownRef.current && !severityDropdownRef.current.contains(e.target as Node)) {
        setSeverityDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['rules'],
    queryFn: async () => {
      const { data } = await api.get('/rules')
      return data as { items: Rule[]; total: number }
    },
    staleTime: 60 * 1000,
  })

  const createMutation = useMutation({
    mutationFn: async (body: typeof form) => {
      const { data } = await api.post('/rules', body)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      setShowModal(false)
    },
  })

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      const { data } = await api.patch(`/rules/${id}`, { is_active })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.delete(`/rules/${id}`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })

  const handleSubmit = () => {
    if (!form.name.trim() || !form.content.trim()) return
    createMutation.mutate(form)
  }

  if (error) {
    return <ErrorState message="规则加载失败" onRetry={refetch} />
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">评审规则</h1>
        <Button variant="primary" size="md" onClick={() => { setEditingRule(null); setForm({ name: '', content: '', category: 'style', severity: 'warning', languages: '["python"]' }); setShowModal(true) }}>
          + 添加规则
        </Button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-muted-more">
              <th className="px-4 py-3 font-medium">规则名</th>
              <th className="px-4 py-3 font-medium">类别</th>
              <th className="px-4 py-3 font-medium">严重性</th>
              <th className="px-4 py-3 font-medium">语言</th>
              <th className="px-4 py-3 font-medium">版本</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="px-4 py-4"><Skeleton className="h-4 w-16" /></td>
                  ))}
                </tr>
              ))
            ) : !data?.items?.length ? (
              <tr>
                <td colSpan={7} className="px-4 py-12">
                  <EmptyState title="暂无评审规则" description="添加第一条规则开始自定义评审规范" />
                </td>
              </tr>
            ) : (
              data.items.map((rule) => {
                const lang = JSON.parse(rule.languages || '[]')
                return (
                  <tr key={rule.id} className="border-b border-border/50 transition-colors hover:bg-surface-hover/50">
                    <td className="px-4 py-4 font-medium text-foreground">{rule.name}</td>
                    <td className="px-4 py-4">
                      <Badge variant="default">{categoryOptions.find(c => c.value === rule.category)?.label || rule.category}</Badge>
                    </td>
                    <td className="px-4 py-4">
                      <Badge variant={rule.severity === 'critical' ? 'error' : rule.severity === 'warning' ? 'warning' : 'info'}>
                        {rule.severity}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 text-muted">{lang.join(', ')}</td>
                    <td className="px-4 py-4 text-muted">v{rule.version}</td>
                    <td className="px-4 py-4">
                      <Badge variant={rule.is_active ? 'success' : 'default'}>
                        {rule.is_active ? '启用' : '禁用'}
                      </Badge>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                          className="text-xs text-muted hover:text-foreground transition-colors"
                        >
                          {rule.is_active ? '禁用' : '启用'}
                        </button>
                        <button
                          onClick={() => deleteMutation.mutate(rule.id)}
                          className="text-xs text-muted hover:text-error transition-colors"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Create Rule Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-lg">
            <h2 className="text-lg font-bold text-foreground">添加规则</h2>
            <p className="mt-1 text-sm text-muted">新增企业自定义评审规范</p>

            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">规则名 *</label>
                <input
                  type="text"
                  placeholder="如：SQL 注入检测"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">类别</label>
                  <div className="relative" ref={categoryDropdownRef}>
                    <button
                      onClick={() => { setCategoryDropdownOpen(!categoryDropdownOpen); setSeverityDropdownOpen(false) }}
                      className="flex items-center gap-2 w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors"
                    >
                      <span className="flex-1 text-left">
                        {categoryOptions.find((o) => o.value === form.category)?.label || form.category}
                      </span>
                      <svg className={`h-4 w-4 text-muted transition-transform ${categoryDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {categoryDropdownOpen && (
                      <div className="absolute left-0 top-full z-30 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
                        {categoryOptions.map((opt) => (
                          <button
                            key={opt.value}
                            onClick={() => {
                              setForm({ ...form, category: opt.value })
                              setCategoryDropdownOpen(false)
                            }}
                            className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                              form.category === opt.value ? 'text-primary' : 'text-foreground'
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">严重性</label>
                  <div className="relative" ref={severityDropdownRef}>
                    <button
                      onClick={() => { setSeverityDropdownOpen(!severityDropdownOpen); setCategoryDropdownOpen(false) }}
                      className="flex items-center gap-2 w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground hover:bg-surface-hover transition-colors"
                    >
                      <span className="flex-1 text-left">
                        {severityOptions.find((o) => o.value === form.severity)?.label || form.severity}
                      </span>
                      <svg className={`h-4 w-4 text-muted transition-transform ${severityDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {severityDropdownOpen && (
                      <div className="absolute left-0 top-full z-30 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
                        {severityOptions.map((opt) => (
                          <button
                            key={opt.value}
                            onClick={() => {
                              setForm({ ...form, severity: opt.value })
                              setSeverityDropdownOpen(false)
                            }}
                            className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover ${
                              form.severity === opt.value ? 'text-primary' : 'text-foreground'
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">规则内容 *</label>
                <textarea
                  placeholder="描述规则内容或正则表达式..."
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  rows={4}
                  className="w-full rounded-md border border-border bg-surface-alt px-3 py-2 text-sm text-foreground placeholder:text-muted-more focus:border-primary focus:outline-none resize-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Button variant="secondary" size="md" onClick={() => setShowModal(false)}>取消</Button>
                <Button variant="primary" size="md" onClick={handleSubmit} disabled={createMutation.isPending}>
                  {createMutation.isPending ? '创建中...' : '确认创建'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
