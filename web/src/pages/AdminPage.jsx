import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api.js'

export default function AdminPage() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'analyst', display_name: '' })
  const [error, setError] = useState('')

  const loadUsers = async () => {
    try {
      const res = await api.get('/api/admin/users')
      setUsers(res.data.users || [])
    } catch (err) {
      if (err.response?.status === 403) {
        setError('Admin access required')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadUsers() }, [])

  const createUser = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await api.post('/api/admin/users', newUser)
      setNewUser({ username: '', password: '', role: 'analyst', display_name: '' })
      setShowCreate(false)
      loadUsers()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create user')
    }
  }

  const deleteUser = async (username) => {
    if (!window.confirm(`Delete user "${username}"? This cannot be undone.`)) return
    try {
      await api.delete(`/api/admin/users/${username}`)
      loadUsers()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete user')
    }
  }

  const resetPassword = async (username) => {
    const newPassword = window.prompt(`New password for ${username}:`)
    if (!newPassword) return
    try {
      await api.put(`/api/admin/users/${username}`, { password: newPassword })
      setError('')
      alert('Password updated')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update password')
    }
  }

  const toggleRole = async (username, currentRole) => {
    const newRole = currentRole === 'admin' ? 'analyst' : 'admin'
    try {
      await api.put(`/api/admin/users/${username}`, { role: newRole })
      loadUsers()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update role')
    }
  }

  if (loading) return <div className="font-mono text-sm text-dim">Loading...</div>
  if (error === 'Admin access required') {
    return <div className="font-mono text-sm text-danger">Admin access required to view this page.</div>
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-accent">User Management</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4" /> Add User
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 font-mono text-xs text-danger">
          {error}
        </div>
      )}

      {showCreate && (
        <div className="mb-6 panel p-5">
          <div className="mb-3 font-mono text-xs uppercase tracking-[0.16em] text-accent">New User</div>
          <form onSubmit={createUser} className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-dim mb-1">Username</label>
              <input className="input" value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} required />
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-dim mb-1">Password</label>
              <input className="input" type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required />
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-dim mb-1">Display Name</label>
              <input className="input" value={newUser.display_name} onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })} />
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-[0.14em] text-dim mb-1">Role</label>
              <select className="input" value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div className="col-span-2 flex gap-2">
              <button className="btn btn-primary" type="submit">Create</button>
              <button className="btn" type="button" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="panel">
        <div className="border-b border-border px-5 py-3 font-mono text-xs uppercase tracking-[0.18em] text-accent">
          Users ({users.length})
        </div>
        <div className="divide-y divide-border">
          {users.map((u) => (
            <div key={u.username} className="flex items-center justify-between p-4">
              <div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold text-text">{u.display_name || u.username}</span>
                  <span className={`badge ${u.role === 'admin' ? 'badge-accent' : 'badge-dim'}`}>{u.role}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] text-dim">
                  @{u.username} — last login: {u.last_login ? new Date(u.last_login).toLocaleString() : 'never'}
                </div>
              </div>
              <div className="flex gap-2">
                <button className="btn text-[10px]" onClick={() => toggleRole(u.username, u.role)}>
                  {u.role === 'admin' ? 'Demote' : 'Promote'}
                </button>
                <button className="btn text-[10px]" onClick={() => resetPassword(u.username)}>
                  Reset PW
                </button>
                {u.username !== 'admin' && (
                  <button className="btn btn-danger text-[10px]" onClick={() => deleteUser(u.username)}>
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
