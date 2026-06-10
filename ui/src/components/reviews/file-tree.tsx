import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/shared'

interface FileNode {
  path: string
  findingCount: number
  severityCounts: Record<string, number>
}

interface FileTreeProps {
  files: FileNode[]
  selectedFile: string | null
  onSelect: (path: string) => void
}

function buildTree(paths: string[]): Record<string, any> {
  const tree: Record<string, any> = {}
  for (const p of paths) {
    const parts = p.split('/')
    let current = tree
    for (const part of parts) {
      if (!current[part]) current[part] = {}
      current = current[part]
    }
  }
  return tree
}

export function FileTree({ files, selectedFile, onSelect }: FileTreeProps) {
  const fileMap = new Map(files.map((f) => [f.path, f]))
  const paths = files.map((f) => f.path)
  const tree = buildTree(paths)

  const renderNode = (node: Record<string, any>, prefix = ''): React.ReactNode[] => {
    return Object.entries(node).map(([name, children]) => {
      const fullPath = prefix ? `${prefix}/${name}` : name
      const file = fileMap.get(fullPath)
      const isLeaf = Object.keys(children).length === 0
      const hasIssues = file && file.findingCount > 0

      return (
        <div key={fullPath}>
          <button
            onClick={() => isLeaf && onSelect(fullPath)}
            className={cn(
              'flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors',
              selectedFile === fullPath
                ? 'bg-amber-50 text-amber-700'
                : isLeaf
                  ? 'text-muted hover:bg-stone-50 hover:text-foreground'
                  : 'text-muted-more',
              !isLeaf && 'cursor-default',
            )}
          >
            <span>{isLeaf ? '📄' : '📁'}</span>
            <span className="truncate flex-1">{name}</span>
            {hasIssues && (
              <Badge variant="error" className="text-[10px] px-1.5 py-0">
                {file!.findingCount}
              </Badge>
            )}
          </button>
          {!isLeaf && (
            <div className="ml-3 border-l border-border pl-2">
              {renderNode(children, fullPath)}
            </div>
          )}
        </div>
      )
    })
  }

  return (
    <div className="space-y-1">
      <h4 className="px-2 text-xs font-medium text-muted-more uppercase tracking-wider">文件</h4>
      <div className="max-h-[500px] overflow-y-auto">
        {files.length === 0 ? (
          <p className="px-2 text-xs text-muted-more">无文件</p>
        ) : (
          renderNode(tree)
        )}
      </div>
    </div>
  )
}
