# 管理后台 UI/UX 设计规范

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联：`docs/project-design.md`
> 生成工具：UI/UX Pro Max — Enterprise Gateway | Dark Mode (OLED)

---

## 一、设计系统

### 1.1 风格定位

| 属性 | 选定值 |
|------|--------|
| **Pattern** | Enterprise Gateway — 专业、可靠、数据密集 |
| **Style** | Dark Mode (OLED) — 开发者友好、代码工具质感 |
| **关键词** | dark, professional, data-dense, technical, precise |
| **适合场景** | 仪表盘、数据分析、后台管理、代码工具 |

### 1.2 色彩体系

```css
/* 语义化色彩 Token（Tailwind CSS 扩展） */
:root {
  /* 主色 — 专业蓝 */
  --color-primary:       #2563EB;   /* blue-600 */
  --color-on-primary:    #FFFFFF;
  --color-primary-hover: #1D4ED8;   /* blue-700 */

  /* 辅色 */
  --color-secondary:     #3B82F6;   /* blue-500 */
  --color-accent:        #059669;   /* emerald-600 — 通过/成功 */

  /* 表面 & 背景 */
  --color-background:    #0F172A;   /* slate-900 — 主背景 */
  --color-surface:       #1E293B;   /* slate-800 — 卡片/侧栏 */
  --color-surface-hover: #334155;   /* slate-700 — hover 状态 */

  /* 文字 */
  --color-foreground:    #F8FAFC;   /* slate-50 — 主文字 */
  --color-muted:         #94A3B8;   /* slate-400 — 次要文字 */
  --color-muted-more:    #64748B;   /* slate-500 — 辅助信息 */

  /* 边框 & 分割线 */
  --color-border:        #334155;   /* slate-700 */
  --color-border-light:  #1E293B;   /* slate-800 */

  /* 语义色 */
  --color-success:       #10B981;   /* emerald-500 */
  --color-warning:       #F59E0B;   /* amber-500 */
  --color-error:         #EF4444;   /* red-500 */
  --color-info:          #3B82F6;   /* blue-500 */

  /* 平台色 — 用于标识来源 */
  --color-github:        #FFFFFF;
  --color-gitlab:        #FC6D26;
  --color-gitee:         #C71D23;

  /* 评审状态色 */
  --color-severity-critical: #EF4444;
  --color-severity-warning:  #F59E0B;
  --color-severity-info:     #3B82F6;

  /* PR 状态色 */
  --color-pr-open:       #22C55E;   /* green-500 */
  --color-pr-merged:     #A855F7;   /* purple-500 */
  --color-pr-closed:     #6B7280;   /* gray-500 */

  /* 特效 */
  --color-ring:          #2563EB;
  --color-destructive:   #DC2626;
}
```

### 1.3 字体系统

```css
/* Fira Sans（UI）/ Fira Code（代码） */
:root {
  --font-sans:  'Fira Sans', system-ui, -apple-system, sans-serif;
  --font-mono:  'Fira Code', 'JetBrains Mono', 'SF Mono', monospace;
}

/* 字号层级 */
--text-xs:   0.75rem;    /* 12px — 辅助文本 */
--text-sm:   0.875rem;   /* 14px — 表格/标签 */
--text-base: 1rem;       /* 16px — 正文 */
--text-lg:   1.125rem;   /* 18px */
--text-xl:   1.25rem;    /* 20px */
--text-2xl:  1.5rem;     /* 24px — 页面标题 */
--text-3xl:  1.875rem;   /* 30px — 仪表盘数字 */

/* 行高 */
--leading-tight:  1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.625;
```

### 1.4 间距体系

基于 4px 基数的 8dp 增量系统：

```css
--space-1:  0.25rem;  /* 4px  */
--space-2:  0.5rem;   /* 8px  */
--space-3:  0.75rem;  /* 12px */
--space-4:  1rem;     /* 16px */
--space-5:  1.25rem;  /* 20px */
--space-6:  1.5rem;   /* 24px */
--space-8:  2rem;     /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
```

### 1.5 圆角 & 阴影

```css
--radius-sm:    0.375rem;  /* 6px  — 标签/徽章 */
--radius-md:    0.5rem;    /* 8px  — 卡片 */
--radius-lg:    0.75rem;   /* 12px — 模态框 */
--radius-xl:    1rem;      /* 16px — 较大的卡片 */
--radius-full:  9999px;    /* 圆形 */

--shadow-sm:   0 1px 2px rgba(0,0,0,0.3);
--shadow-md:   0 4px 6px rgba(0,0,0,0.4);
--shadow-lg:   0 10px 15px rgba(0,0,0,0.5);
--shadow-glow: 0 0 20px rgba(37,99,235,0.15);  /* 主色辉光 */
```

---

## 二、布局结构

### 2.1 整体布局

```
┌─────────────────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────────────────────────────┐ │
│  │          │  │  Header                          │ │
│  │  Sidebar │  │  [搜索] [项目选择器] [头像]       │ │
│  │  (w-64)  │  ├──────────────────────────────────┤ │
│  │          │  │                                  │ │
│  │  ● 仪表盘 │  │  Main Content Area              │ │
│  │  ● 项目   │  │  (flex-1, overflow-y-auto)      │ │
│  │  ● 异常   │  │                                  │ │
│  │          │  │  ┌── Breadcrumb ────────────────┐ │ │
│  │          │  │  │  项目 / repo-name / PR #42   │ │ │
│  │          │  │  └──────────────────────────────┘ │ │
│  │          │  │                                  │ │
│  │          │  │  [Page Content]                  │ │
│  │          │  │                                  │ │
│  └──────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.2 侧边栏导航（桌面 ≥ 1024px）

| 导航项 | 图标 | 路径 | 说明 |
|--------|------|------|------|
| 仪表盘 | LayoutDashboard | `/dashboard` | 全局概览 |
| 项目 | GitFork | `/projects` | 项目列表与详情 |
| 异常监控 | AlertTriangle | `/errors` | 评审异常日志 |
| ← 分割线 → | | | |
| 待规划 | | | |
| 成员分析 | Users | `/members` | M2 阶段 |
| 规范知识库 | BookOpen | `/rules` | M2 阶段 |
| 设置 | Settings | `/settings` | M2 阶段 |

### 2.3 响应式断点

| 断点 | 宽度 | 布局行为 |
|------|------|---------|
| Mobile | < 768px | Sidebar 收为抽屉（Sheet），内容区全宽 |
| Tablet | 768–1024px | Sidebar 收为图标栏（w-16），hover 展开 |
| Desktop | ≥ 1024px | Sidebar 展开（w-64），内容区自适应 |
| Wide | ≥ 1440px | 最大内容宽度 1280px，居中 |

### 2.4 Loading / Empty / Error 状态规范

| 状态 | 组件 | 行为 |
|------|------|------|
| **Loading** | `<Skeleton />` (shadcn/ui) | 首屏：整页骨架屏。列表：行骨架 x3。图表：灰块 + 脉冲动画 |
| **Empty** | `<EmptyState />` | 图标 + 标题 + 描述 + CTA（如"添加第一个项目"） |
| **Error** | `<ErrorState />` | 错误图标 + 描述 + 重试按钮（调用 refetch） |
| **Partial Error** | `<Toast />` | 底部弹出，3-5s 自动消失，提供重试操作 |

---

## 三、页面设计

### 3.1 仪表盘 (`/dashboard`)

```
┌──────────────────────────────────────────────────────────┐
│  仪表盘                                                    │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ 📦 仓库   │  │ 📝 今日   │  │ ⭐ 平均   │  │ ⚠️ 异常   │ │
│  │  **12**   │  │  **8**    │  │  **86**   │  │  **3**    │ │
│  │  接入仓库  │  │  评审次数  │  │  评分     │  │  待处理    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                           │
│  ┌────────────────────────────────────┐  ┌────────────┐  │
│  │  平台连通性                          │  │ 问题分布    │  │
│  │  ┌──────────────────────────┐      │  │ ┌────────┐ │  │
│  │  │  🟢 GitHub   1403ms 活跃  │      │  │ │ Donut  │ │  │
│  │  │  🔴 Gitee    269ms 认证失败│      │  │ │ Chart  │ │  │
│  │  │  ⚪ GitLab   —     未检测  │      │  │ │        │ │  │
│  │  └──────────────────────────┘      │  │ └────────┘ │  │
│  │                                    │  │ Security 45%│  │
│  │  数据源: GET /health/platforms     │  │ Bug      25%│  │
│  │  后台每1分钟自动更新                │  │ Perf     15%│  │
│  └────────────────────────────────────┘  └────────────┘  │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  质量趋势 (30天)                                       │ │
│  │  ┌──────────────────────────────────────────┐        │ │
│  │  │  📈 Line Chart (Recharts)                 │        │ │
│  │  │  项目筛选 ▼  [周] [月]                    │        │ │
│  │  └──────────────────────────────────────────┘        │ │
│  │                                                        │ │
│  │  各项目独立线条，hover tooltip 显示精确值 + 项目名     │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**组件分解：**
- `StatCard` — 图标 / 数字 (text-3xl font-bold) / 标签 / 微趋势箭头
- `TrendChart` — 多系列折线图，项目筛选下拉，时间粒度切换
- `CategoryPieChart` — 6 类别环形图，点击筛选下钻
- `DashboardFilters` — 项目多选、日期范围选择器

**数据流动：**
```
<DashboardPage>
  ├── useQuery('/api/v1/dashboard/stats')           → DashboardStats
  ├── useQuery('/api/v1/dashboard/quality-trends')   → TrendDataPoint[]
  └── useQuery('/api/v1/dashboard/category-dist')    → {security: N, ...}
```

### 3.2 项目列表 (`/projects`)

```
┌──────────────────────────────────────────────────────────┐
│  项目                                       [+ 添加项目] │
│                                                           │
│  [🔍 搜索仓库名...]    平台: [全部 ▼]                      │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  仓库名       平台  Webhook  最近评审       操作      │ │
│  │  ├───────────┼────┼────────┼────────────┼─────────┤ │
│  │  │ frontend   │ ⬡  │ 🟢 已连接 │ 10分钟前   │ 👁 ⚙️ │ │
│  │  │ backend    │ ⬡  │ 🔴 未连接 │ —          │ 👁 ⚙️ │ │
│  │  │ mobile-app │ ⬡  │ 🟢 已连接 │ 2小时前    │ 👁 ⚙️ │ │
│  │  │ docs       │ ⬡  │ 🟡 待配置 │ —          │ 👁 ⚙️ │ │
│  │  └───────────┴────┴────────┴────────────┴─────────┘ │
│  │                                        ← 1-4 of 12 → │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**平台标识：**
| 平台 | 图标 | 色值 |
|------|------|------|
| GitHub | `<GithubIcon />` | `#FFFFFF` |
| GitLab | `<GitlabIcon />` | `#FC6D26` |
| Gitee | `<GiteeIcon />` | `#C71D23` |

**组件分解：**
- `ProjectTable` — DataTable (shadcn/ui) + 自定义列渲染
- `PlatformBadge` — 图标 + 平台名，按平台着色
- `WebhookStatus` — 绿/黄/红圆点 + 状态文字
- `SearchInput` — 带防抖（300ms）的搜索框
- `PlatformFilter` — 下拉多选

**交互细节：**
- 搜索：300ms debounce，URL query 同步 → 支持分享
- Webhook 状态：hover 显示详情（上次活跃时间 + 失败次数）
- 操作列：查看（→ `/projects/:id`）、设置（抽屉面板）
- 空状态："还没有接入任何仓库" + "添加第一个项目" 按钮

**状态处理：**
```
Loading  → <Skeleton /> 行 × 4
Empty    → <EmptyState icon={GitFork} title="还没有接入仓库" cta="添加项目" />
Error    → <ErrorState message="加载失败" onRetry={refetch} />
```

### 3.3 项目详情 (`/projects/:id`)

```
┌──────────────────────────────────────────────────────────┐
│  项目 / frontend  [⚙️ 设置]                              │
│  platform: github  |  webhook: 🟢 已连接  |  last: 10min │
│                                                           │
│  ┌── Tab ───────────────────────────────────────────────┐ │
│  │  [📋 PR 列表]  [📤 提交]  [📈 质量趋势]               │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  PR #   标题        作者    状态     AI 评审   评分 │ │
│  │  142    feat: add    alice   🟢 open  ✅ 完成   92  │ │
│  │  141    fix: login   bob     🟣 merged ✅ 完成   85  │ │
│  │  140    chore: ...   alice   ⚪ closed ⏳ 等待   —   │ │
│  │  139    refactor:..  carol   🟢 open  ❌ 失败   —   │ │
│  │                                        ← 1-4 of 20 → │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Tab 内容：**

| Tab | 子组件 | API |
|-----|--------|-----|
| PR 列表 | `PullRequestTable` — 状态徽章（open: 绿 / merged: 紫 / closed: 灰）+ AI 评审标签（pending: 黄 / running: 蓝 / completed: 绿 / failed: 红）+ 评分柱 | `GET /api/v1/projects/:id/pull-requests` |
| 提交 | `CommitList` — SHA（截短7位，mono font）+ 作者头像 + 消息（截断一行）+ 分支标签 + "Review" 按钮 | `GET /api/v1/projects/:id/commits` |
| 质量 | `QualityTrendsView` — 折线图 + 时间粒度 + 叠加所有月份的首次提交质量 | `GET /api/v1/dashboard/quality-trends?project_id=:id` |

**状态标签规范：**

| 类型 | 值 | Tailwind |
|------|----|----------|
| AI 状态: pending | ⌛ 等待中 | `bg-yellow-500/10 text-yellow-500` |
| AI 状态: running | 🔄 进行中 | `bg-blue-500/10 text-blue-500` |
| AI 状态: completed | ✅ 已完成 | `bg-green-500/10 text-green-500` |
| AI 状态: failed | ❌ 失败 | `bg-red-500/10 text-red-500` |
| PR 状态: open | 🟢 Open | `bg-green-500/10 text-green-500 border-green-500` |
| PR 状态: merged | 🟣 Merged | `bg-purple-500/10 text-purple-500 border-purple-500` |
| PR 状态: closed | ⚪ Closed | `bg-gray-500/10 text-gray-400 border-gray-500` |

### 3.4 评审详情 (`/projects/:id/prs/:pr_number`)

```
┌──────────────────────────────────────────────────────────┐
│  PR #142  feat: add user auth module                     │
│  author: alice  |  open  |  score: 92/100  🟢 优秀     │
│                                                           │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │ 📁 文件树     │  │  Finding 详情                    │ │
│  │              │  │                                   │ │
│  │  src/        │  │  ┌──────────────────────────────┐ │ │
│  │  ├── auth.py │  │  │  🔴 CRITICAL                 │ │ │
│  │  ├── routes  │  │  │  SQL Injection in query      │ │ │
│  │  │   └─ ... │  │  │  src/auth.py:42              │ │ │
│  │  └── utils   │  │  │  ─────────────────────      │ │ │
│  │      └─ ...  │  │  │  用户输入未参数化直接拼接    │ │ │
│  │              │  │  │  💡 使用参数化查询           │ │ │
│  │              │  │  │                              │ │ │
│  │              │  │  │  [✅ 采纳]  [❌ 无效]  [💬]   │ │ │
│  │              │  │  └──────────────────────────────┘ │ │
│  │              │  │                                   │ │
│  │              │  │  ┌─ 评论 ────────────────────────┐ │ │
│  │              │  │  │  bob: 已修复合入              │ │ │
│  │              │  │  │  alice: LGTM                  │ │ │
│  │              │  │  └──────────────────────────────┘ │ │
│  └──────────────┘  └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**组件分解：**
- `FileTree` — 可折叠树，高亮有 Finding 的文件（红点标记数量）
- `FindingCard` — 严重性图标 + 标题 + 位置 + 描述 + 建议，可展开/收起
- `FeedbackActions` — 采纳 / 无效 / 评论三个操作按钮
- `CommentThread` — 评论列表 + 输入框

**交互细节：**
- 点击文件树 → 右侧只显示该文件的 Findings
- Finding 默认折叠，点击展开显示完整描述和建议
- 反馈操作后即时更新状态 + toast 确认
- "采纳" 和 "无效" 可切换（再点取消）

### 3.5 异常监控 (`/errors`)

```
┌──────────────────────────────────────────────────────────┐
│  异常监控                                                   │
│                                                           │
│  项目: [全部 ▼]    类型: [全部 ▼]    日期: [范围选择]     │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  📊 错误类型分布                                      │ │
│  │  ┌──────────────────────────────────────────┐       │ │
│  │  │  ████████████ ai_call_failed       12    │       │ │
│  │  │  ██████████  git_api_failed        10    │       │ │
│  │  │  ██████      parse_failed           6    │       │ │
│  │  │  ███         timeout                3    │       │ │
│  │  └──────────────────────────────────────────┘       │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  时间         项目       类型             消息        │ │
│  │  2026-06-08   frontend   🔴 ai_call_failed  "Model..│ │
│  │  10:30:42               🟢 Recovered                   │ │
│  │  2026-06-08   backend    🔴 git_api_failed  "Rate... │ │
│  │  09:15:00                                             │ │
│  │  2026-06-07   mobile     🟡 parse_failed    "JSON..  │ │
│  │  18:00:00                                             │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**组件分解：**
- `ErrorTypeBarChart` — 水平柱状图，每种类型一种颜色
- `ErrorTable` — 行包含：时间 / 项目链接 / 类型标签（红: 未恢复 / 绿: 已恢复）/ 消息截断
- `ErrorFilters` — 项目下拉 / 类型下拉 / 日期范围选择器

**交互细节：**
- 点击柱状图类型 → 自动筛选该类型
- 错误消息截断（单行），hover 显示全部
- 恢复状态使用绿色"🟢 Recovered"标签 vs 红色类型标签

---

## 四、组件树

```
<App>
  <QueryClientProvider>
    <Router>
      <AppLayout>
        ├── <Sidebar>
        │   ├── <Logo />
        │   ├── <NavItem icon={LayoutDashboard} to="/dashboard" label="仪表盘" />
        │   ├── <NavItem icon={GitFork} to="/projects" label="项目" />
        │   ├── <NavItem icon={AlertTriangle} to="/errors" label="异常监控" />
        │   └── <UserMenu />
        ├── <Header>
        │   ├── <Breadcrumb />
        │   ├── <ProjectSelector />      (全局项目切换)
        │   └── <UserAvatar />
        └── <main>
            ├── Routes
            │   ├── /dashboard → <DashboardPage>
            │   │   ├── <StatsGrid>
            │   │   │   └── <StatCard /> × 4
            │   │   ├── <TrendChart />          (Recharts LineChart)
            │   │   ├── <CategoryPieChart />    (Recharts PieChart)
            │   │   └── <DashboardFilters />
            │   │
            │   ├── /projects → <ProjectsPage>
            │   │   ├── <PageHeader title="项目" action={AddProjectButton} />
            │   │   ├── <SearchAndFilters>
            │   │   │   ├── <SearchInput />
            │   │   │   └── <PlatformFilter />
            │   │   └── <ProjectTable>
            │   │       ├── <DataTable>
            │   │       │   ├── <PlatformBadge />
            │   │       │   ├── <WebhookStatus />
            │   │       │   └── <TableActions />
            │   │       └── <Pagination />
            │   │
            │   ├── /projects/:id → <ProjectDetailPage>
            │   │   ├── <ProjectHeader />
            │   │   ├── <Tabs>
            │   │   │   ├── Tab: PRs → <PullRequestTable>
            │   │   │   │   ├── <PRStatusBadge />
            │   │   │   │   ├── <ReviewStatusBadge />
            │   │   │   │   └── <ScoreBar />
            │   │   │   ├── Tab: Commits → <CommitList>
            │   │   │   │   ├── <CommitRow />
            │   │   │   │   └── <ReviewTriggerButton />
            │   │   │   └── Tab: Quality → <QualityTrendsView>
            │   │   │       └── <TrendChart />
            │   │   └── <Pagination />
            │   │
            │   ├── /projects/:id/prs/:pr → <ReviewDetailPage>
            │   │   ├── <ReviewHeader>
            │   │   │   ├── <ScoreDisplay />
            │   │   │   └── <PRStatusBadge />
            │   │   ├── <SplitView>
            │   │   │   ├── <FileTree /> (left)
            │   │   │   └── <FindingsPanel> (right)
            │   │   │       ├── <FindingCard /> × N
            │   │   │       └── <FeedbackActions />
            │   │   └── <CommentSection>
            │   │       ├── <CommentThread />
            │   │       └── <CommentInput />
            │   │
            │   └── /errors → <ErrorsPage>
            │       ├── <ErrorFilters />
            │       ├── <ErrorTypeBarChart />
            │       └── <ErrorTable>
            │           ├── <ErrorTypeBadge />
            │           ├── <RecoveredBadge />
            │           └── <Pagination />
            │
            └── Shared Components
                ├── <Skeleton />
                ├── <EmptyState />
                ├── <ErrorState />
                ├── <Toast />
                └── <LoadingSpinner />
```

---

## 五、数据流动

### 5.1 TanStack Query 查询策略

| Query Key | API | Stale Time | Refetch |
|-----------|-----|-----------|---------|
| `['dashboard', 'stats']` | `GET /api/v1/dashboard/stats` | 5 min | 窗口聚焦时 |
| `['health', 'platforms']` | `GET /health/platforms` | 30s | 自动刷新（1分钟后台轮询） |
| `['dashboard', 'trends', {project_id, period}]` | `GET /api/v1/dashboard/quality-trends` | 10 min | 筛选变化时 |
| `['projects', {search, platform, page}]` | `GET /api/v1/projects` | 2 min | 手动刷新 |
| `['projects', id]` | `GET /api/v1/projects/:id` | 10 min | — |
| `['projects', id, 'prs', {state, page}]` | `GET /api/v1/projects/:id/pull-requests` | 1 min | 窗口聚焦时 |
| `['projects', id, 'commits', {branch, page}]` | `GET /api/v1/projects/:id/commits` | 2 min | — |
| `['reviews', reviewId]` | `GET /api/v1/projects/:id/reviews/:taskId` | 30s (polling) | 轮询（status !== completed） |
| `['errors', {filters}]` | `GET /api/v1/errors` | 30s | 自动刷新 |
| `['errors', 'stats']` | `GET /api/v1/errors/stats` | 1 min | 自动刷新 |

### 5.2 Zustand 客户端状态

```typescript
interface UIStore {
  sidebar: 'expanded' | 'collapsed' | 'mobile-closed';
  theme: 'dark' | 'light';
  // actions
  toggleSidebar: () => void;
  setTheme: (theme: 'dark' | 'light') => void;
}

interface FilterStore {
  globalProjectFilter: string | null;   // 全局项目筛选（仪表盘用）
  // actions
  setGlobalProjectFilter: (id: string | null) => void;
}
```

---

## 六、API Client 封装

```typescript
// src/lib/api-client.ts
import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// 响应拦截 — 统一错误处理
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      // 重定向到登录
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

---

## 七、实施清单

### Phase 2 — 前端骨架

- [ ] `npm create vite@latest ui -- --template react-ts`
- [ ] 安装 tailwindcss, postcss, autoprefixer
- [ ] 配置 tailwind.config.ts + globals.css（深色主题）
- [ ] 安装 shadcn/ui 并配置
- [ ] 安装 recharts, @tanstack/react-query, react-router-dom, axios, zustand
- [ ] 实现 AppLayout（Sidebar + Header + Content）
- [ ] 实现路由配置
- [ ] 实现 api-client.ts + hooks
- [ ] 实现 DashboardPage（StatCard + TrendChart）
- [ ] 实现 ProjectsPage（ProjectTable + Search + Filters）
- [ ] 实现 ProjectDetailPage（Tabs + PRTable + CommitList）

### Phase 3 — 评审 + 质量 + 异常

- [ ] 实现 ReviewDetailPage（FileTree + FindingCard + Feedback）
- [ ] 实现 ErrorsPage（ErrorTable + BarChart + Filters）
- [ ] 实现 QualityTrendsView（Enhanced TrendChart）
- [ ] 补全 Loading / Empty / Error 状态
- [ ] 响应式适配测试

### Phase 4 — 企业级加固

- [ ] 认证路由守卫
- [ ] RBAC 权限控制（菜单项按角色显示/隐藏）
- [ ] 审计日志
- [ ] 深色/浅色主题切换
