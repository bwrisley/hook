import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { api } from '../lib/api.js'

export default function NotificationBell() {
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)

  const load = async () => {
    try {
      const res = await api.get('/api/notifications')
      setNotifications(res.data.items || [])
      setUnread(res.data.unread || 0)
    } catch { /* not loaded yet */ }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  const markRead = async (id) => {
    await api.post(`/api/notifications/${id}/read`)
    load()
  }

  const markAllRead = async () => {
    await api.post('/api/notifications/read-all')
    load()
  }

  const handleClick = (notif) => {
    markRead(notif.id)
    setOpen(false)
    if (notif.conversation_id) {
      navigate(`/investigate/${notif.conversation_id}`)
    }
  }

  return (
    <div className="relative">
      <button
        className="relative text-dim hover:text-accent transition"
        onClick={() => setOpen(!open)}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-8 z-50 w-80 rounded-xl border border-border bg-panel shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <span className="font-mono text-xs uppercase tracking-[0.14em] text-accent">Notifications</span>
            {unread > 0 && (
              <button className="font-mono text-[10px] text-dim hover:text-accent" onClick={markAllRead}>
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-auto">
            {notifications.length === 0 ? (
              <div className="p-4 font-mono text-xs text-dim">No notifications</div>
            ) : (
              notifications.map((notif) => (
                <button
                  key={notif.id}
                  className={`w-full border-b border-border/50 p-3 text-left transition hover:bg-panel2 ${
                    !notif.read ? 'bg-accent/5' : ''
                  }`}
                  onClick={() => handleClick(notif)}
                >
                  <div className="flex items-center gap-2">
                    {!notif.read && <span className="h-2 w-2 rounded-full bg-accent" />}
                    <span className="font-mono text-xs font-bold text-text">{notif.title}</span>
                  </div>
                  <div className="mt-1 text-xs text-dim line-clamp-2">{notif.body}</div>
                  <div className="mt-1 font-mono text-[10px] text-dim">
                    {new Date(notif.created_at).toLocaleString()}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
