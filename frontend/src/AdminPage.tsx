import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from './store/auth'

type AdminUser = {
  id: number
  username: string
  email?: string | null
  role: 'admin' | 'vip' | 'normal'
  is_active: number
  warning_msg?: string | null
}

type AdminInvite = {
  id: number
  code: string
  created_by_user_id: number
  max_uses: number
  used_count: number
  expires_at: string | null
  note: string | null
  created_at: string
  is_expired: boolean
}

type AdminFeedback = {
  id: number
  owner_user_id: number
  owner?: {
    id: number
    username: string
    email?: string | null
    role: string
  } | null
  feedback_type: string
  title: string
  content: string
  status: 'open' | 'triaged' | 'in_progress' | 'resolved' | 'closed' | 'reopened'
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  route?: string | null
  related_job_id?: string | null
  public_reply?: string | null
  internal_note?: string | null
  created_at: string
  updated_at: string
}

type AdminFeedbackList = {
  items: AdminFeedback[]
  total: number
  open_count: number
}

type CreateInviteForm = {
  code: string
  maxUses: string
  expiresAt: string
  note: string
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : typeof data?.message === 'string'
          ? data.message
          : '请求失败。'
    throw new Error(detail)
  }
  return data as T
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

export default function AdminPage() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [invites, setInvites] = useState<AdminInvite[]>([])
  const [feedback, setFeedback] = useState<AdminFeedback[]>([])
  const [feedbackOpenCount, setFeedbackOpenCount] = useState(0)
  const [roleDrafts, setRoleDrafts] = useState<Record<number, AdminUser['role']>>({})
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<number, { status: AdminFeedback['status']; priority: AdminFeedback['priority']; public_reply: string; internal_note: string }>>({})
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [savingUserId, setSavingUserId] = useState<number | null>(null)
  const [deletingInviteId, setDeletingInviteId] = useState<number | null>(null)
  const [inviteForm, setInviteForm] = useState<CreateInviteForm>({
    code: '',
    maxUses: '1',
    expiresAt: '',
    note: '',
  })

  const stats = useMemo(() => {
    const adminCount = users.filter((item) => item.role === 'admin').length
    const vipCount = users.filter((item) => item.role === 'vip').length
    const normalCount = users.filter((item) => item.role === 'normal').length
    const activeCount = users.filter((item) => item.is_active === 1).length
    const expiredInviteCount = invites.filter((item) => item.is_expired).length
    const p0FeedbackCount = feedback.filter((item) => item.priority === 'P0' && !['resolved', 'closed'].includes(item.status)).length
    return {
      totalUsers: users.length,
      adminCount,
      vipCount,
      normalCount,
      activeCount,
      totalInvites: invites.length,
      expiredInviteCount,
      totalFeedback: feedback.length,
      openFeedback: feedbackOpenCount,
      p0FeedbackCount,
    }
  }, [feedback, feedbackOpenCount, invites, users])

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [usersResponse, invitesResponse, feedbackResponse] = await Promise.all([
        fetch('/api/admin/users'),
        fetch('/api/admin/invite_codes'),
        fetch('/api/feedback/admin'),
      ])
      const [usersData, inviteData, feedbackData] = await Promise.all([
        parseJsonOrThrow<AdminUser[]>(usersResponse),
        parseJsonOrThrow<AdminInvite[]>(invitesResponse),
        parseJsonOrThrow<AdminFeedbackList>(feedbackResponse),
      ])
      setUsers(usersData)
      setInvites(inviteData)
      setFeedback(feedbackData.items || [])
      setFeedbackOpenCount(feedbackData.open_count || 0)
      setRoleDrafts(
        Object.fromEntries(usersData.map((item) => [item.id, item.role])) as Record<number, AdminUser['role']>,
      )
      setFeedbackDrafts(
        Object.fromEntries(
          (feedbackData.items || []).map((item) => [
            item.id,
            {
              status: item.status,
              priority: item.priority,
              public_reply: item.public_reply || '',
              internal_note: item.internal_note || '',
            },
          ]),
        ) as Record<number, { status: AdminFeedback['status']; priority: AdminFeedback['priority']; public_reply: string; internal_note: string }>,
      )
    } catch (loadError: any) {
      setError(loadError.message || '加载管理员后台失败。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  async function patchUser(userId: number, payload: Record<string, unknown>, successMessage: string) {
    setSavingUserId(userId)
    setMessage('')
    setError('')
    try {
      const response = await fetch(`/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      await parseJsonOrThrow<{ message: string }>(response)
      setMessage(successMessage)
      await loadData()
    } catch (patchError: any) {
      setError(patchError.message || '用户更新失败。')
    } finally {
      setSavingUserId(null)
    }
  }

  async function handleRoleSave(target: AdminUser) {
    const nextRole = roleDrafts[target.id]
    if (!nextRole || nextRole === target.role) return
    await patchUser(target.id, { role: nextRole }, `已将 ${target.username} 调整为 ${nextRole}。`)
  }

  async function handleToggleActive(target: AdminUser) {
    await patchUser(
      target.id,
      { is_active: target.is_active === 1 ? 0 : 1 },
      target.is_active === 1 ? `已停用 ${target.username}。` : `已重新启用 ${target.username}。`,
    )
  }

  async function handleResetPassword(target: AdminUser) {
    const nextPassword = window.prompt(`请输入 ${target.username} 的新密码（至少 8 位）`)
    if (!nextPassword) return
    await patchUser(target.id, { new_password: nextPassword }, `已重置 ${target.username} 的密码。`)
  }

  async function handleCreateInvite() {
    setMessage('')
    setError('')
    try {
      const payload: Record<string, unknown> = {
        max_uses: Number(inviteForm.maxUses) || 1,
        note: inviteForm.note || undefined,
      }
      if (inviteForm.code.trim()) payload.code = inviteForm.code.trim()
      if (inviteForm.expiresAt) payload.expires_at = new Date(inviteForm.expiresAt).toISOString()

      const response = await fetch('/api/admin/invite_codes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      await parseJsonOrThrow<AdminInvite>(response)
      setInviteForm({ code: '', maxUses: '1', expiresAt: '', note: '' })
      setMessage('邀请码创建成功。')
      await loadData()
    } catch (createError: any) {
      setError(createError.message || '创建邀请码失败。')
    }
  }

  async function handleDeleteInvite(invite: AdminInvite) {
    if (!window.confirm(`确定删除邀请码 ${invite.code} 吗？`)) return
    setDeletingInviteId(invite.id)
    setMessage('')
    setError('')
    try {
      const response = await fetch(`/api/admin/invite_codes/${invite.id}`, { method: 'DELETE' })
      await parseJsonOrThrow<{ message: string }>(response)
      setMessage(`邀请码 ${invite.code} 已删除。`)
      await loadData()
    } catch (deleteError: any) {
      setError(deleteError.message || '删除邀请码失败。')
    } finally {
      setDeletingInviteId(null)
    }
  }

  async function handleSaveFeedback(item: AdminFeedback) {
    const draft = feedbackDrafts[item.id]
    if (!draft) return
    setMessage('')
    setError('')
    try {
      const response = await fetch(`/api/feedback/admin/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: draft.status,
          priority: draft.priority,
          public_reply: draft.public_reply,
          internal_note: draft.internal_note,
        }),
      })
      await parseJsonOrThrow<AdminFeedback>(response)
      setMessage(`反馈 #${item.id} 已更新。`)
      await loadData()
    } catch (saveError: any) {
      setError(saveError.message || '更新反馈失败。')
    }
  }

  const feedbackTypeLabel: Record<string, string> = {
    bug: '问题',
    feature: '建议',
    question: '疑问',
    data_issue: '数据',
    translation: '翻译',
    reading_quality: '精读质量',
    other: '其他',
  }

  const feedbackStatusLabel: Record<string, string> = {
    open: '待处理',
    triaged: '已分流',
    in_progress: '处理中',
    resolved: '已解决',
    closed: '已关闭',
    reopened: '重开',
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-8">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-medium text-violet-600">管理员后台</div>
              <h1 className="mt-1 text-2xl font-bold text-gray-900">用户与邀请码管理</h1>
              <p className="mt-2 text-sm text-gray-500">当前登录：admin {user?.username}。这里可以管理用户角色、账号状态和邀请码。</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                to="/workspace"
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm text-gray-700 hover:border-emerald-300 hover:text-emerald-700"
              >
                返回工作台
              </Link>
              <button
                onClick={() => void loadData()}
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm text-gray-700 hover:border-emerald-300 hover:text-emerald-700"
                type="button"
              >
                {loading ? '刷新中...' : '刷新数据'}
              </button>
              <button
                onClick={async () => {
                  await logout()
                }}
                className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600 hover:bg-red-100"
                type="button"
              >
                退出登录
              </button>
            </div>
          </div>

          {(message || error) && (
            <div className="mt-4 space-y-2">
              {message && <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</div>}
              {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
            </div>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-gray-500">用户总数</div>
            <div className="mt-2 text-3xl font-bold text-gray-900">{stats.totalUsers}</div>
            <div className="mt-2 text-xs text-gray-400">启用中 {stats.activeCount} 人</div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-gray-500">角色分布</div>
            <div className="mt-2 text-sm text-gray-700">admin {stats.adminCount}</div>
            <div className="mt-1 text-sm text-gray-700">vip {stats.vipCount}</div>
            <div className="mt-1 text-sm text-gray-700">normal {stats.normalCount}</div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-gray-500">邀请码总数</div>
            <div className="mt-2 text-3xl font-bold text-gray-900">{stats.totalInvites}</div>
            <div className="mt-2 text-xs text-gray-400">已过期 {stats.expiredInviteCount} 个</div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-gray-500">待处理反馈</div>
            <div className="mt-2 text-3xl font-bold text-gray-900">{stats.openFeedback}</div>
            <div className="mt-2 text-xs text-gray-400">P0 未关闭 {stats.p0FeedbackCount} 条，总计 {stats.totalFeedback} 条</div>
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
          <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-100 px-5 py-4">
              <h2 className="text-base font-semibold text-gray-900">用户列表</h2>
              <p className="mt-1 text-sm text-gray-500">支持调整角色、停用/启用账号，以及触发密码重置。</p>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-500">
                  <tr>
                    <th className="px-5 py-3 font-medium">用户</th>
                    <th className="px-5 py-3 font-medium">邮箱</th>
                    <th className="px-5 py-3 font-medium">角色</th>
                    <th className="px-5 py-3 font-medium">状态</th>
                    <th className="px-5 py-3 font-medium">提醒</th>
                    <th className="px-5 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {users.map((item) => (
                    <tr key={item.id}>
                      <td className="px-5 py-4">
                        <div className="font-medium text-gray-900">{item.username}</div>
                        <div className="mt-1 text-xs text-gray-400">ID {item.id}</div>
                      </td>
                      <td className="px-5 py-4 text-gray-600">{item.email || '未设置'}</td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <select
                            value={roleDrafts[item.id] || item.role}
                            onChange={(event) =>
                              setRoleDrafts((current) => ({
                                ...current,
                                [item.id]: event.target.value as AdminUser['role'],
                              }))
                            }
                            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                          >
                            <option value="admin">admin</option>
                            <option value="vip">vip</option>
                            <option value="normal">normal</option>
                          </select>
                          <button
                            onClick={() => void handleRoleSave(item)}
                            disabled={savingUserId === item.id || (roleDrafts[item.id] || item.role) === item.role}
                            className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                            type="button"
                          >
                            保存
                          </button>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            item.is_active === 1 ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'
                          }`}
                        >
                          {item.is_active === 1 ? '启用中' : '已停用'}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-xs text-gray-500">
                        {item.warning_msg ? <span className="line-clamp-2">{item.warning_msg}</span> : '无'}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => void handleToggleActive(item)}
                            disabled={savingUserId === item.id}
                            className="rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-700 hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-50"
                            type="button"
                          >
                            {item.is_active === 1 ? '停用' : '启用'}
                          </button>
                          <button
                            onClick={() => void handleResetPassword(item)}
                            disabled={savingUserId === item.id}
                            className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                            type="button"
                          >
                            重置密码
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-5">
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-gray-900">创建邀请码</h2>
              <div className="mt-4 space-y-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500">邀请码文本</span>
                  <input
                    value={inviteForm.code}
                    onChange={(event) => setInviteForm({ ...inviteForm, code: event.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    placeholder="留空则自动生成 VIP-xxxx"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500">最大使用次数</span>
                  <input
                    value={inviteForm.maxUses}
                    onChange={(event) =>
                      setInviteForm({ ...inviteForm, maxUses: event.target.value.replace(/[^\d]/g, '') || '1' })
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500">过期时间</span>
                  <input
                    type="datetime-local"
                    value={inviteForm.expiresAt}
                    onChange={(event) => setInviteForm({ ...inviteForm, expiresAt: event.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-500">备注</span>
                  <textarea
                    value={inviteForm.note}
                    onChange={(event) => setInviteForm({ ...inviteForm, note: event.target.value })}
                    rows={3}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                    placeholder="例如：答辩季体验账号 / 课程班专用"
                  />
                </label>
                <button
                  onClick={() => void handleCreateInvite()}
                  className="w-full rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700"
                  type="button"
                >
                  创建邀请码
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-4">
                <h2 className="text-base font-semibold text-gray-900">邀请码列表</h2>
              </div>
              <div className="divide-y divide-gray-100">
                {invites.length === 0 ? (
                  <div className="px-5 py-8 text-sm text-gray-400">还没有邀请码记录。</div>
                ) : (
                  invites.map((invite) => (
                    <div key={invite.id} className="px-5 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-gray-900">{invite.code}</span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                                invite.is_expired ? 'bg-gray-200 text-gray-600' : 'bg-emerald-100 text-emerald-700'
                              }`}
                            >
                              {invite.is_expired ? '已过期' : '可用'}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-gray-500">
                            已用 {invite.used_count}/{invite.max_uses} 次
                          </div>
                          <div className="mt-1 text-xs text-gray-500">
                            创建于 {formatTime(invite.created_at)} · 过期于 {formatTime(invite.expires_at)}
                          </div>
                          {invite.note && <div className="mt-2 text-xs text-gray-600">{invite.note}</div>}
                        </div>
                        <button
                          onClick={() => void handleDeleteInvite(invite)}
                          disabled={deletingInviteId === invite.id}
                          className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600 hover:bg-red-100 disabled:opacity-50"
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        </div>

        <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h2 className="text-base font-semibold text-gray-900">用户反馈</h2>
            <p className="mt-1 text-sm text-gray-500">反馈是管理员运营数据，不进入用户 .dra 导出包。处理后用户可在“我的反馈”看到公开回复。</p>
          </div>
          <div className="divide-y divide-gray-100">
            {feedback.length === 0 ? (
              <div className="px-5 py-8 text-sm text-gray-400">还没有用户反馈。</div>
            ) : (
              feedback.map((item) => {
                const draft = feedbackDrafts[item.id] || {
                  status: item.status,
                  priority: item.priority,
                  public_reply: item.public_reply || '',
                  internal_note: item.internal_note || '',
                }
                return (
                  <div key={item.id} className="px-5 py-5">
                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            item.priority === 'P0' ? 'bg-red-100 text-red-700' :
                              item.priority === 'P1' ? 'bg-amber-100 text-amber-700' :
                                'bg-gray-100 text-gray-600'
                          }`}>
                            {item.priority}
                          </span>
                          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                            {feedbackTypeLabel[item.feedback_type] || item.feedback_type}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                            {feedbackStatusLabel[item.status] || item.status}
                          </span>
                        </div>
                        <div className="mt-3 text-base font-semibold text-gray-900">{item.title}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          #{item.id} · {item.owner?.username || `用户 ${item.owner_user_id}`} · {formatTime(item.created_at)}
                          {item.route ? ` · ${item.route}` : ''}
                        </div>
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-gray-700">{item.content}</p>
                        {item.related_job_id && (
                          <div className="mt-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500">
                            关联任务：{item.related_job_id}
                          </div>
                        )}
                      </div>
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                          <label className="block">
                            <span className="mb-1 block text-xs font-medium text-gray-500">状态</span>
                            <select
                              value={draft.status}
                              onChange={(event) =>
                                setFeedbackDrafts((current) => ({
                                  ...current,
                                  [item.id]: { ...draft, status: event.target.value as AdminFeedback['status'] },
                                }))
                              }
                              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                            >
                              <option value="open">待处理</option>
                              <option value="triaged">已分流</option>
                              <option value="in_progress">处理中</option>
                              <option value="resolved">已解决</option>
                              <option value="closed">已关闭</option>
                              <option value="reopened">重开</option>
                            </select>
                          </label>
                          <label className="block">
                            <span className="mb-1 block text-xs font-medium text-gray-500">优先级</span>
                            <select
                              value={draft.priority}
                              onChange={(event) =>
                                setFeedbackDrafts((current) => ({
                                  ...current,
                                  [item.id]: { ...draft, priority: event.target.value as AdminFeedback['priority'] },
                                }))
                              }
                              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                            >
                              <option value="P0">P0</option>
                              <option value="P1">P1</option>
                              <option value="P2">P2</option>
                              <option value="P3">P3</option>
                            </select>
                          </label>
                        </div>
                        <label className="block">
                          <span className="mb-1 block text-xs font-medium text-gray-500">公开回复（用户可见）</span>
                          <textarea
                            value={draft.public_reply}
                            onChange={(event) =>
                              setFeedbackDrafts((current) => ({
                                ...current,
                                [item.id]: { ...draft, public_reply: event.target.value },
                              }))
                            }
                            rows={3}
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                          />
                        </label>
                        <label className="block">
                          <span className="mb-1 block text-xs font-medium text-gray-500">内部备注</span>
                          <textarea
                            value={draft.internal_note}
                            onChange={(event) =>
                              setFeedbackDrafts((current) => ({
                                ...current,
                                [item.id]: { ...draft, internal_note: event.target.value },
                              }))
                            }
                            rows={3}
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
                          />
                        </label>
                        <button
                          onClick={() => void handleSaveFeedback(item)}
                          className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                          type="button"
                        >
                          保存反馈处理
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
