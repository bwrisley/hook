import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import InvestigatePage from './pages/InvestigatePage.jsx'
import AgentsPage from './pages/AgentsPage.jsx'
import InvestigationsPage from './pages/InvestigationsPage.jsx'
import FeedsPage from './pages/FeedsPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/investigate" replace />} />
        <Route path="/investigate" element={<InvestigatePage />} />
        <Route path="/investigate/:conversationId" element={<InvestigatePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/investigations" element={<InvestigationsPage />} />
        <Route path="/feeds" element={<FeedsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  )
}
