import { useState } from 'react'

type ConflictOption = 'overwrite' | 'new' | 'incremental'

interface BatchConflictItem {
  file_id: string
  file_name: string
  has_conflict: true
  bib_entry: { id: string; title: string; reading_status: string }
  existing_job: {
    job_id: string
    job_type: string
    created_at: string | null
    dimensions: string[]
    mode_label: string
  }
  incremental_dims: string[]
}

interface BatchConflictDialogProps {
  conflicts: BatchConflictItem[]
  noConflictCount: number
  mode: 'long' | 'quant' | 'qual'
  onResolve: (resolution: ConflictOption) => void
  onCancel: () => void
}

export default function BatchConflictDialog({ conflicts, noConflictCount, mode, onResolve, onCancel }: BatchConflictDialogProps) {
  const hasIncremental = mode === 'long' && conflicts.some(c => c.incremental_dims && c.incremental_dims.length > 0)
  const [selected, setSelected] = useState<ConflictOption>(hasIncremental ? 'incremental' : 'overwrite')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 space-y-4 max-h-[80vh] flex flex-col">
        <h3 className="text-lg font-semibold text-gray-900">
          批量精读冲突检测
        </h3>

        <p className="text-sm text-gray-600">
          以下 {conflicts.length} 个文件已有精读结果：
        </p>

        <div className="overflow-y-auto flex-1 space-y-2 min-h-0">
          {conflicts.map((c) => (
            <div key={c.file_id} className="rounded-lg border border-gray-200 p-3">
              <p className="text-sm font-medium text-gray-800">{c.file_name}</p>
              <p className="text-xs text-gray-500">
                已有：{c.existing_job.mode_label}
                {c.existing_job.created_at && (
                  <>（{new Date(c.existing_job.created_at).toLocaleString('zh-CN')} 完成）</>
                )}
              </p>
              {mode === 'long' && c.existing_job.dimensions.length > 0 && (
                <p className="text-xs text-gray-500 mt-1">
                  已分析维度：{c.existing_job.dimensions.join('、')}
                </p>
              )}
              {c.incremental_dims && c.incremental_dims.length > 0 && (
                <p className="text-xs text-amber-600 mt-1">
                  新增维度：{c.incremental_dims.join('、')}
                </p>
              )}
            </div>
          ))}
        </div>

        {noConflictCount > 0 && (
          <p className="text-sm text-gray-500">
            {noConflictCount} 个文件无冲突，将直接精读。
          </p>
        )}

        <div className="space-y-2">
          {mode === 'long' && hasIncremental && (
            <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
              <input type="radio" name="batch-conflict" value="incremental"
                checked={selected === 'incremental'} onChange={() => setSelected('incremental')} />
              <div>
                <span className="font-medium">增量补充</span>
                <span className="text-xs text-gray-500 ml-1">（跳过已有维度）</span>
              </div>
            </label>
          )}

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="batch-conflict" value="overwrite"
              checked={selected === 'overwrite'} onChange={() => setSelected('overwrite')} />
            <div>
              <span className="font-medium">覆盖重跑</span>
              <span className="text-xs text-gray-500 ml-1">（删除旧结果，全部重新精读）</span>
            </div>
          </label>

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="batch-conflict" value="new"
              checked={selected === 'new'} onChange={() => setSelected('new')} />
            <div>
              <span className="font-medium">跳过已有</span>
              <span className="text-xs text-gray-500 ml-1">（保留旧结果，只精读新文件）</span>
            </div>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onClick={() => onResolve(selected)}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">确认开始</button>
        </div>
      </div>
    </div>
  )
}
