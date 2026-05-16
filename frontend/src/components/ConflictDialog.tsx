import { useState } from 'react'

type ConflictOption = 'overwrite' | 'new' | 'incremental'

interface ConflictInfo {
  has_conflict: true
  existing_job: {
    job_id: string
    job_type: string
    created_at: string | null
    dimensions: string[]
    mode_label: string
  }
  incremental_dims: string[]
  bib_entry: { id: string; title: string; reading_status: string }
}

interface ConflictDialogProps {
  conflict: ConflictInfo
  mode: 'long' | 'quant' | 'qual'
  onResolve: (resolution: ConflictOption) => void
  onCancel: () => void
}

export default function ConflictDialog({ conflict, mode, onResolve, onCancel }: ConflictDialogProps) {
  const [selected, setSelected] = useState<ConflictOption>(
    mode === 'long' && conflict.incremental_dims.length > 0 ? 'incremental' : 'overwrite'
  )
  const isLong = mode === 'long'
  const hasIncremental = isLong && conflict.incremental_dims.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">
          该文献已有{conflict.existing_job.mode_label}结果
        </h3>

        {conflict.existing_job.created_at && (
          <p className="text-sm text-gray-500">
            完成时间：{new Date(conflict.existing_job.created_at).toLocaleString('zh-CN')}
          </p>
        )}

        {isLong && conflict.existing_job.dimensions.length > 0 && (
          <div className="text-sm">
            <p className="text-gray-600">已分析维度：{conflict.existing_job.dimensions.join('、')}</p>
            {hasIncremental && (
              <p className="text-amber-600 mt-1">本次新增维度：{conflict.incremental_dims.join('、')}</p>
            )}
          </div>
        )}

        <div className="space-y-2">
          {isLong && hasIncremental && (
            <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
              <input type="radio" name="conflict" value="incremental"
                checked={selected === 'incremental'} onChange={() => setSelected('incremental')} />
              <div>
                <span className="font-medium">增量补充</span>
                <span className="text-xs text-gray-500 ml-1">（跳过已有维度）</span>
              </div>
            </label>
          )}

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="conflict" value="overwrite"
              checked={selected === 'overwrite'} onChange={() => setSelected('overwrite')} />
            <div>
              <span className="font-medium">覆盖重跑</span>
              <span className="text-xs text-gray-500 ml-1">（删除同模式旧结果）</span>
            </div>
          </label>

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="conflict" value="new"
              checked={selected === 'new'} onChange={() => setSelected('new')} />
            <div>
              <span className="font-medium">新增独立记录</span>
              <span className="text-xs text-gray-500 ml-1">（旧结果保留）</span>
            </div>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onClick={() => onResolve(selected)}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">确认</button>
        </div>
      </div>
    </div>
  )
}
