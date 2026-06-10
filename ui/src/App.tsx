import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLayout } from '@/components/layout/app-layout'
import { DashboardPage } from '@/pages/dashboard'
import { ProjectsPage } from '@/pages/projects'
import { ProjectDetailPage } from '@/pages/project-detail'
import { ReviewDetailPage } from '@/pages/review-detail'
import { ReviewsPage } from '@/pages/reviews'
import { ReviewHistoryDetailPage } from '@/pages/review-history-detail'
import { RulesPage } from '@/pages/rules'
import { ErrorsPage } from '@/pages/errors'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/projects/:id/prs/:prNumber" element={<ReviewDetailPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:reviewId" element={<ReviewHistoryDetailPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/errors" element={<ErrorsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
