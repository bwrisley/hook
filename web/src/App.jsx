import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { getMe } from './lib/api.js'
import Layout from './components/Layout.jsx'
import LoginPage from './pages/LoginPage.jsx'
import InvestigatePage from './pages/InvestigatePage.jsx'
import AgentsPage from './pages/AgentsPage.jsx'
import InvestigationsPage from './pages/InvestigationsPage.jsx'
import FeedsPage from './pages/FeedsPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import AdminPage from './pages/AdminPage.jsx'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    getMe().then((data) => {
      if (data.status === 'ok') {
        setUser(data.user)
      }
    }).catch(() => {}).finally(() => setChecking(false))
  }, [])

  if (checking) {
    return <div className="flex h-full items-center justify-center bg-shell text-dim font-mono text-sm">Loading...</div>
  }

  if (!user) {
    return <LoginPage onLogin={(u) => setUser(u)} />
  }

  return (
    <Layout user={user} onLogout={() => setUser(null)}>
      <Routes>
        <Route path="/" element={<Navigate to="/investigate" replace />} />
        <Route path="/investigate" element={<InvestigatePage />} />
        <Route path="/investigate/:conversationId" element={<InvestigatePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/investigations" element={<InvestigationsPage />} />
        <Route path="/feeds" element={<FeedsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {user.role === 'admin' && <Route path="/admin" element={<AdminPage />} />}
      </Routes>
    </Layout>
  )
}
