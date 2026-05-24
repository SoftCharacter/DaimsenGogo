import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import AppLayout from './components/layout/AppLayout'
import ConfigPage from './pages/ConfigPage'
import AnalysisPage from './pages/AnalysisPage'
import DashboardPage from './pages/DashboardPage'
import { useHeartbeat } from './hooks/useHeartbeat'

/**
 * 应用根组件
 * 配置路由、全局Toast通知和后端心跳
 */
function App() {
  /* 向后端发送心跳，浏览器关闭后后端自动退出 */
  useHeartbeat()

  return (
    <BrowserRouter>
      {/* 全局Toast通知 - 深色主题样式 */}
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#151c2c',
            color: '#e2e8f0',
            border: '1px solid #1e293b',
          },
        }}
      />
      {/* 路由配置 */}
      <Routes>
        <Route element={<AppLayout />}>
          {/* 默认跳转到大屏看板 */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/analysis/:id/edit" element={<AnalysisPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/:id" element={<DashboardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
