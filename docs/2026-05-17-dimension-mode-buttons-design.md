# 维度级模式按钮设计

## 目标

在对比综述（CompareView）的每个维度 accordion header 右侧增加三个模式按钮（编辑 / 点评 / AI总结），点击后该维度下所有卡片同时切换到对应的显示模式。每张卡片的实际操作（保存编辑、创建点评、触发AI总结）仍然是独立的单卡行为。

## 现状分析

### 当前架构

```
AccordionPanel（维度容器）
  ├── activeModeCard: string | null     ← 同维度只允许一张卡片活跃
  ├── cardModes: Record<paperId, CardMode>
  │
  └── papers.map → AnswerCard
        ├── cardMode: CardMode          ← 由 cardModes[paperId] 决定
        ├── isActive: boolean           ← paperId === activeModeCard
        └── onModeChange(paperId, mode) ← 通知 AccordionPanel 切换
```

### 现有限制

- `activeModeCard` 强制同一维度同一时刻只有一张卡片处于非 normal 模式
- 卡片 A 进入 editing 时，卡片 B 自动回到 normal
- 没有维度级的批量模式切换入口

## 设计

### 核心改动

1. **移除 `activeModeCard` 机制**：删除 `activeModeCard` state，每张卡片的 `isActive` 改为 `cardModes[paperId] !== undefined && cardModes[paperId] !== 'normal'`。
2. **新增维度级按钮**：在 accordion header 右侧（checkbox 和箭头之间或箭头左侧）放置三个小按钮，仅在 `state === 'full'` 时可见。
3. **批量设置 cardModes**：维度按钮点击时，将所有 paperId 的 cardModes 设为同一值；再次点击同一按钮时，全部回 normal。

### 状态模型

```
AccordionPanel（改动后）
  ├── cardModes: Record<paperId, CardMode>   ← 每张卡片独立模式
  ├── dimMode: CardMode                      ← derived: 当前维度的统一模式（用于按钮高亮）
  │
  └── papers.map → AnswerCard
        ├── cardMode: CardMode
        ├── isActive: boolean                ← cardModes[paperId] 存在且 !== 'normal'
        └── onModeChange(paperId, mode)      ← 单卡切换，允许与维度级不一致
```

`dimMode` 是计算属性：当所有活跃卡片的模式一致时返回该模式，否则返回 `'normal'`（按钮不高亮）。

### 单卡模式变更 vs 维度级模式变更

- **单卡按钮**（AnswerCard 内）：改变 `cardModes[paperId]`，不影响其他卡片。如果单卡切到与维度级不同的模式，维度按钮取消高亮。
- **维度级按钮**：批量设置所有 paperId 到同一 mode，或全部回 normal。

### 交互细节

| 场景 | 行为 |
|------|------|
| 点击维度"编辑"按钮 | 所有卡片进入 editing，按钮变为"退出编辑" |
| 点击维度"退出编辑" | 所有卡片回到 normal |
| 维度处于"编辑"，点击某张卡的"点评" | 该卡切到 annotating，其他卡保持 editing，维度按钮取消高亮 |
| 所有卡片手动回到 normal | 维度按钮恢复为三个未选中状态 |
| 收起维度（collapsed/preview） | 维度按钮隐藏，cardModes 不重置 |
| 重新展开到 full | 恢复之前的 cardModes 状态 |

### AnswerCard 无需改动

AnswerCard 的 props 接口和内部逻辑完全不变：
- 仍接收 `cardMode`、`isActive`、`onModeChange`
- 内部 editing/annotating/ai_summarizing 的渲染逻辑不变
- 唯一变化来自父组件传入的 `isActive` 计算方式

### UI 布局

```
┌─────────────────────────────────────────────────────┐
│ ☑ 研究方法与数据采集              [编辑][点评][AI总结] ▼ │  ← header
├─────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│ │ Paper A  │ │ Paper B  │ │ Paper C  │              │  ← 全部显示编辑态
│ │ [textarea]│ │ [textarea]│ │ [textarea]│              │
│ │ [保存][撤销]│ │ [保存][撤销]│ │ [保存][撤销]│              │
│ └──────────┘ └──────────┘ └──────────┘              │
│                                    [收起详细对比]      │
└─────────────────────────────────────────────────────┘
```

按钮样式：复用现有 `.compare-mode-btn` 样式，尺寸稍小（`.compare-dim-mode-btn`），激活态使用 `.compare-dim-mode-btn.active`。

## 改动清单

| 文件 | 改动 |
|------|------|
| `AccordionPanel.tsx` | 移除 `activeModeCard`，新增 `handleDimModeChange`，header 增加3个按钮，`isActive` 改为 derived |
| `compare.css` | 新增 `.compare-dim-mode-btn` 样式（约20行） |

AnswerCard.tsx、CompareView.tsx、其他文件均无改动。

## 风险与边界

- **性能**：同时渲染 5 张编辑态 textarea 无压力。若未来卡片数 > 10，可考虑虚拟化，当前无需。
- **数据一致性**：每张卡片的保存/回退/点评独立触发 `onRefresh`，不存在批量提交需求。
- **收起时状态保留**：用户可能展开→编辑几张卡→收起→再展开，期望编辑内容仍在。cardModes 不随 accordion 状态重置。
