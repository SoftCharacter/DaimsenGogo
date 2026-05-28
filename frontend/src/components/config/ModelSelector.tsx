import { useConfigStore } from '../../stores/configStore'
import toast from 'react-hot-toast'

/**
 * 模型选择器组件
 * 展示可用模型列表，允许用户选择要使用的AI模型
 * 当前选中的模型会高亮显示并标注"当前使用"
 */
export default function ModelSelector() {
  /* ---------- 从Store获取状态 ---------- */
  const { config, selectModel } = useConfigStore()

  /** 可用模型列表 */
  const models = config?.available_models || []
  /** 当前选中的模型名称 */
  const selectedModel = config?.selected_model || ''

  /**
   * 处理模型选择事件
   * 调用store方法更新后端和本地状态
   * @param model - 被选择的模型名称
   */
  const handleSelect = async (model: string) => {
    await selectModel(model)
    toast.success(`已选择模型: ${model}`)
  }

  /* ---------- 无可用模型时展示提示 ---------- */
  if (models.length === 0) {
    return (
      <div
        className="rounded-lg p-6 border"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          borderColor: 'var(--color-border)',
        }}
      >
        <h3
          className="text-lg font-semibold mb-2"
          style={{ color: 'var(--color-text-primary)' }}
        >
          可用模型
        </h3>
        {/* 引导用户先配置供应商 */}
        <p
          className="text-sm"
          style={{ color: 'var(--color-text-muted)' }}
        >
          请先配置供应商并获取模型列表
        </p>
      </div>
    )
  }

  /* ---------- 模型列表渲染 ---------- */
  return (
    <div
      className="rounded-lg p-6 border"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* 标题显示模型总数 */}
      <h3
        className="text-lg font-semibold mb-4"
        style={{ color: 'var(--color-text-primary)' }}
      >
        可用模型 ({models.length})
      </h3>

      {/* 模型按钮列表 - 选中项高亮 */}
      <div className="space-y-2">
        {models.map((model) => {
          /** 当前模型是否被选中 */
          const isSelected = model === selectedModel
          return (
            <button
              key={model}
              onClick={() => handleSelect(model)}
              className="w-full text-left px-4 py-3 rounded-md border text-sm transition-colors flex items-center justify-between"
              style={{
                backgroundColor: isSelected
                  ? 'var(--color-accent)'
                  : 'var(--color-bg-primary)',
                borderColor: isSelected
                  ? 'var(--color-accent)'
                  : 'var(--color-border)',
                color: isSelected ? '#ffffff' : 'var(--color-text-primary)',
              }}
            >
              {/* 模型名称 */}
              <span>{model}</span>
              {/* 选中标记徽章 */}
              {isSelected && (
                <span className="text-xs bg-white/20 px-2 py-0.5 rounded">
                  当前使用
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
