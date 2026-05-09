import { useEffect, useState } from 'react'

interface DimSet {
  id: number
  name: string
  description: string | null
  is_default: boolean
  is_system: boolean
  item_count: number
  sort_order: number
}

interface DimItem {
  id: number
  dim_key: string
  dim_name: string
  description: string | null
  prompt_content: string
  default_question: string
  sort_order: number
  is_builtin: boolean
}

export default function DimensionManager() {
  const [sets, setSets] = useState<DimSet[]>([])
  const [selectedSetId, setSelectedSetId] = useState<number | null>(null)
  const [showNewSetForm, setShowNewSetForm] = useState(false)
  const [newSetName, setNewSetName] = useState('')

  const [items, setItems] = useState<DimItem[]>([])
  const [showNewItemForm, setShowNewItemForm] = useState(false)
  const [newItemName, setNewItemName] = useState('')
  const [newItemDesc, setNewItemDesc] = useState('')
  const [newItemPrompt, setNewItemPrompt] = useState('')
  const [newItemQuestion, setNewItemQuestion] = useState('')

  const [editingItem, setEditingItem] = useState<DimItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editPrompt, setEditPrompt] = useState('')
  const [editQuestion, setEditQuestion] = useState('')

  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const loadSets = async () => {
    try {
      const res = await fetch('/api/dimensions/sets')
      if (!res.ok) throw new Error('加载集合失败')
      const data: DimSet[] = await res.json()
      setSets(data)
      const active = data.find(s => s.is_default)
      if (active && selectedSetId === null) {
        setSelectedSetId(active.id)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setMessage(`❌ ${msg}`)
    }
  }

  const loadItems = async (setId: number | null) => {
    if (setId === null) { setItems([]); return }
    try {
      const res = await fetch(`/api/dimensions/sets/${setId}/items`)
      if (!res.ok) throw new Error('加载维度失败')
      setItems(await res.json())
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setMessage(`❌ ${msg}`)
    }
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadSets() }, [])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setEditingItem(null)
    setShowNewItemForm(false)
    loadItems(selectedSetId)
  }, [selectedSetId])
  /* eslint-enable react-hooks/set-state-in-effect */

  const createSet = async () => {
    if (!newSetName.trim()) return
    setLoading(true); setMessage('')
    try {
      const body: any = { name: newSetName.trim() }
      if (selectedSetId !== null) body.clone_from_set_id = selectedSetId
      const res = await fetch('/api/dimensions/sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '创建失败')
      const created = await res.json()
      setShowNewSetForm(false); setNewSetName('')
      await loadSets()
      setSelectedSetId(created.id)
      setMessage('✓ 集合已创建')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const deleteSet = async (id: number) => {
    if (!confirm('确定删除此集合？')) return
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error((await res.json()).detail || '删除失败')
      if (selectedSetId === id) setSelectedSetId(null)
      await loadSets()
      setMessage('✓ 集合已删除')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const activateSet = async (id: number) => {
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${id}/activate`, { method: 'POST' })
      if (!res.ok) throw new Error((await res.json()).detail || '激活失败')
      await loadSets()
      setMessage('✓ 已切换为当前激活集合')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const cloneSet = async (id: number) => {
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${id}/clone`, { method: 'POST' })
      if (!res.ok) throw new Error((await res.json()).detail || '复制失败')
      const created = await res.json()
      await loadSets()
      setSelectedSetId(created.id)
      setMessage('✓ 集合已复制')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const resetSet = async (id: number) => {
    if (!confirm('将删除所有自定义维度并恢复默认，确定？')) return
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${id}/reset`, { method: 'POST' })
      if (!res.ok) throw new Error((await res.json()).detail || '恢复失败')
      await loadItems(id)
      setMessage('✓ 已恢复默认维度')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const createItem = async () => {
    if (!newItemName.trim() || !selectedSetId) return
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${selectedSetId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dim_name: newItemName.trim(),
          description: newItemDesc.trim() || null,
          prompt_content: newItemPrompt,
          default_question: newItemQuestion,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '添加失败')
      setShowNewItemForm(false)
      setNewItemName(''); setNewItemDesc(''); setNewItemPrompt(''); setNewItemQuestion('')
      await loadItems(selectedSetId)
      setMessage('✓ 维度已添加')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const startEdit = (item: DimItem) => {
    setEditingItem(item)
    setEditName(item.dim_name)
    setEditDesc(item.description || '')
    setEditPrompt(item.prompt_content)
    setEditQuestion(item.default_question)
  }

  const saveEdit = async () => {
    if (!editingItem || !selectedSetId) return
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${selectedSetId}/items/${editingItem.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dim_name: editName.trim(),
          description: editDesc.trim() || null,
          prompt_content: editPrompt,
          default_question: editQuestion,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '保存失败')
      setEditingItem(null)
      await loadItems(selectedSetId)
      setMessage('✓ 维度已更新')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const deleteItem = async (item: DimItem) => {
    if (!confirm('确定删除此维度？') || !selectedSetId) return
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${selectedSetId}/items/${item.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error((await res.json()).detail || '删除失败')
      if (editingItem?.id === item.id) setEditingItem(null)
      await loadItems(selectedSetId)
      setMessage('✓ 维度已删除')
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const moveItem = async (item: DimItem, direction: 'up' | 'down') => {
    if (!selectedSetId) return
    const idx = items.findIndex(i => i.id === item.id)
    if (idx < 0) return
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= items.length) return
    const orders = [
      { id: item.id, sort_order: items[swapIdx].sort_order },
      { id: items[swapIdx].id, sort_order: item.sort_order },
    ]
    setLoading(true); setMessage('')
    try {
      const res = await fetch(`/api/dimensions/sets/${selectedSetId}/items/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orders }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '排序失败')
      await loadItems(selectedSetId)
    } catch (e: unknown) { setMessage(`❌ ${e instanceof Error ? e.message : String(e)}`) }
    setLoading(false)
  }

  const selectedSet = sets.find(s => s.id === selectedSetId)

  return (
    <div className="w-full space-y-4">
      {/* Set selector */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">维度集合</h3>
          <button
            onClick={() => { setShowNewSetForm(true); setNewSetName('') }}
            className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 transition-all"
          >+ 新建集合</button>
        </div>

        {showNewSetForm && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 mb-3 flex items-center gap-2">
            <input
              value={newSetName}
              onChange={e => setNewSetName(e.target.value)}
              placeholder="集合名称"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              onKeyDown={e => { if (e.key === 'Enter') createSet() }}
            />
            <button onClick={createSet} disabled={loading} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">创建</button>
            <button onClick={() => setShowNewSetForm(false)} className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-200">取消</button>
          </div>
        )}

        <div className="space-y-1">
          {sets.map(s => (
            <div
              key={s.id}
              onClick={() => setSelectedSetId(s.id)}
              className={`flex items-center justify-between rounded-lg p-3 cursor-pointer transition-colors ${
                selectedSetId === s.id
                  ? 'bg-emerald-50 border border-emerald-200'
                  : 'hover:bg-gray-50 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-medium text-gray-800 truncate">{s.name}</span>
                {s.is_default && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 shrink-0">激活</span>}
                {s.is_system && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700 shrink-0">系统</span>}
                <span className="text-xs text-gray-400 shrink-0">({s.item_count} 维度)</span>
              </div>
              <div className="flex items-center gap-1 shrink-0 ml-2">
                {!s.is_default && (
                  <button onClick={e => { e.stopPropagation(); activateSet(s.id) }} title="激活" className="rounded px-1.5 py-0.5 text-[10px] text-emerald-600 hover:bg-emerald-100">激活</button>
                )}
                {!s.is_system && (
                  <>
                    <button onClick={e => { e.stopPropagation(); cloneSet(s.id) }} title="复制" className="rounded px-1.5 py-0.5 text-[10px] text-gray-500 hover:bg-gray-100">复制</button>
                    <button onClick={e => { e.stopPropagation(); deleteSet(s.id) }} title="删除" className="rounded px-1.5 py-0.5 text-[10px] text-red-500 hover:bg-red-50">删除</button>
                  </>
                )}
              </div>
            </div>
          ))}
          {sets.length === 0 && <div className="text-sm text-gray-400 py-4 text-center">暂无集合</div>}
        </div>
      </div>

      {message && <div className={`text-sm ${message.startsWith('✓') ? 'text-emerald-600' : 'text-red-600'}`}>{message}</div>}

      {/* Item list */}
      {selectedSet && (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">维度列表 — {selectedSet.name}</h3>
            <div className="flex items-center gap-2">
              {selectedSet.is_system && (
                <button onClick={() => resetSet(selectedSet.id)} disabled={loading} className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50">恢复默认</button>
              )}
              <button
                onClick={() => { setShowNewItemForm(true); setNewItemName(''); setNewItemDesc(''); setNewItemPrompt(''); setNewItemQuestion('') }}
                className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 transition-all"
              >+ 添加</button>
            </div>
          </div>

          {showNewItemForm && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 mb-3 space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input value={newItemName} onChange={e => setNewItemName(e.target.value)} placeholder="维度名称 *" className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
                <input value={newItemQuestion} onChange={e => setNewItemQuestion(e.target.value)} placeholder="默认问题" className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
              </div>
              <input value={newItemDesc} onChange={e => setNewItemDesc(e.target.value)} placeholder="描述（可选）" className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
              <textarea value={newItemPrompt} onChange={e => setNewItemPrompt(e.target.value)} placeholder="提示词内容" rows={4} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-emerald-500 focus:outline-none" />
              <div className="flex gap-2">
                <button onClick={createItem} disabled={loading} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">添加</button>
                <button onClick={() => setShowNewItemForm(false)} className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-200">取消</button>
              </div>
            </div>
          )}

          <div className="space-y-1">
            {items.map((item, idx) => (
              <div key={item.id} className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-gray-50">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-gray-400 w-5 shrink-0">{idx + 1}.</span>
                  <span className="text-sm text-gray-800">{item.dim_name}</span>
                  {item.is_builtin && selectedSet.is_system && (
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">内置</span>
                  )}
                </div>
                <div className="flex items-center gap-0.5 shrink-0 ml-2">
                  <button onClick={() => moveItem(item, 'up')} disabled={idx === 0} title="上移" className="rounded px-1 py-0.5 text-xs text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30">↑</button>
                  <button onClick={() => moveItem(item, 'down')} disabled={idx === items.length - 1} title="下移" className="rounded px-1 py-0.5 text-xs text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30">↓</button>
                  <button onClick={() => startEdit(item)} className="rounded px-1.5 py-0.5 text-xs text-blue-600 hover:bg-blue-50">编辑</button>
                  {!(selectedSet.is_system && item.is_builtin) && (
                    <button onClick={() => deleteItem(item)} className="rounded px-1.5 py-0.5 text-xs text-red-500 hover:bg-red-50">删除</button>
                  )}
                </div>
              </div>
            ))}
            {items.length === 0 && <div className="text-sm text-gray-400 py-4 text-center">暂无维度</div>}
          </div>
        </div>
      )}

      {/* Edit panel */}
      {editingItem && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/30 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">编辑：{editingItem.dim_name}</h3>
            <button onClick={() => setEditingItem(null)} className="text-xs text-gray-500 hover:text-gray-700">关闭</button>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">维度名称</label>
            <input value={editName} onChange={e => setEditName(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">描述</label>
            <input value={editDesc} onChange={e => setEditDesc(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">默认问题</label>
            <input value={editQuestion} onChange={e => setEditQuestion(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">提示词</label>
            <textarea value={editPrompt} onChange={e => setEditPrompt(e.target.value)} rows={10} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-emerald-500 focus:outline-none" />
          </div>
          <div className="flex gap-2">
            <button onClick={saveEdit} disabled={loading} className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:from-emerald-700 hover:to-emerald-600 disabled:opacity-50 transition-all">保存</button>
            <button onClick={() => startEdit(editingItem)} className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200">重置</button>
          </div>
        </div>
      )}
    </div>
  )
}
