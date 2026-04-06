import { NavLink } from 'react-router-dom'
import { Activity, Bot, ClipboardList, FileText, LogOut, Rss, Settings, Shield, Users } from 'lucide-react'
import { logout } from '../lib/api.js'
import NotificationBell from './NotificationBell.jsx'

export default function Layout({ children, user, onLogout }) {
  const links = [
    { to: '/investigate', label: 'INVESTIGATE', icon: Bot },
    { to: '/agents', label: 'AGENTS', icon: Activity },
    { to: '/investigations', label: 'HISTORY', icon: FileText },
    { to: '/feeds', label: 'FEEDS', icon: Rss },
    { to: '/settings', label: 'SETTINGS', icon: Settings },
  ]

  if (user?.role === 'admin') {
    links.push({ to: '/audit', label: 'AUDIT', icon: ClipboardList })
    links.push({ to: '/admin', label: 'USERS', icon: Users })
  }

  const handleLogout = async () => {
    await logout()
    onLogout()
  }

  return (
    <div className="flex h-full bg-shell text-text">
      <aside className="flex w-64 flex-col border-r border-border bg-panel">
        <div className="border-b border-border p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-accent/40 bg-accent/10 p-2 text-accent">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <div className="font-mono text-sm font-bold tracking-[0.22em] text-accent">SHADOWBOX</div>
              <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-dim">by punch cyber</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg border px-3 py-3 font-mono text-xs tracking-[0.16em] transition ` +
                (isActive
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-transparent text-dim hover:border-border hover:bg-panel2 hover:text-text')
              }
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-xs text-text">{user?.display_name || user?.username}</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">{user?.role}</div>
            </div>
            <button
              className="text-dim hover:text-danger transition"
              onClick={handleLogout}
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border bg-panel px-6">
          <div className="font-mono text-xs uppercase tracking-[0.22em] text-dim">
            SOC Operations Console
          </div>
          <div className="flex items-center gap-4">
            <NotificationBell />
            <div className="badge badge-accent">online</div>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  )
}
