# 测试集与 P2 改进规划

> 日期：2026-05-03
> 状态：测试集创建中，等待完成后启动 P2

## 1. 当前进展

### 1.1 已完成

- **P1 PDF 题录/元数据在线匹配增强** (2026-05-03)
  - PDF 前 1-3 页提取：`backend/services/pdf_metadata_extract.py`
  - DeepSeek 元数据抽取：`backend/services/pdf_metadata_llm.py`
  - Crossref/OpenAlex 在线候选：`backend/services/crossref_source.py`, `openalex_source.py`
  - 统一评分服务：`backend/services/metadata_match_service.py`
  - 前端匹配面板：`frontend/src/MetadataMatchPanel.tsx`
  - 测试：8 个测试全部通过

- **技术文档更新**
  - `docs/FUNCTION_INDEX.md` - 新增 7 个模块函数索引
  - `docs/STATE_AND_API_MAP.md` - 新增 2 个 API 端点
  - `docs/TECHNICAL_OVERVIEW.md` - 新增元数据匹配功能描述
  - `docs/SYNTHESIS_CURRENT_DESIGN.md` - AI 综述功能现状梳理

### 1.2 进行中

- **测试集创建** - 三篇高标准农田论文正在批量精读
  - 论文 1：土地整治、农业新质生产力与耕地利用生态效率（朱乾隆等）
  - 论文 2：土地流转、高标准农田建设与农业高质量发展（操小娟等）
  - 论文 3：高标准农田建设对农业高质量发展的影响（李豪杰等）
  - 处理内容：七步法精读 + 四步法精读 + 长文本精读 + 参考文献梳理
  - 脚本：`scripts/batch_reading_test.py`

## 2. 测试集完成后任务

### 2.1 验证综述质量

用测试集的三篇论文，执行对比分析并生成 AI 综述，检查：

1. **参考文献目录格式**
   - 年份是否显示 `None`
   - 作者是否显示 `佚名`
   - 期刊信息是否完整

2. **正文引用质量**
   - 是否使用间注法（作者, 年份）
   - 是否退化为 `文献1/文献2`
   - 引用与目录是否对应

3. **综述内容质量**
   - 是否基于实际精读内容
   - 是否有捏造数据
   - 结构是否符合要求

### 2.2 P2 改进方向

根据验证结果，确定 P2 的具体改进范围：

| 问题 | 可能原因 | 改进方向 |
|------|----------|----------|
| 年份显示 `None` | `build_reference_list()` 未兜底 | 程序层修复 |
| 作者显示 `佚名` | 元数据缺失 | 程序层兜底 + 数据层补全 |
| 正文引用退化 | 提示词约束不够强 | 提示词层改进 |
| 引用与目录不对应 | 缺少强制锚点 | 提示词 + 程序联合改进 |

## 3. 相关文件索引

### 3.1 综述核心代码

| 文件 | 职责 |
|------|------|
| `backend/routers/compare.py` | 综述生成路由 + 提示词 + 参考文献生成 |
| `backend/routers/history.py` | 综述历史保存与查询 |
| `frontend/public/compare_7step.html` | 七步对比页面 |
| `frontend/public/compare_4step.html` | 四步对比页面 |
| `frontend/public/compare_long.html` | 长文本对比页面 |

### 3.2 关键函数

| 函数 | 位置 | 作用 |
|------|------|------|
| `SYSTEM_PROMPT` | compare.py:438 | 系统提示词 |
| `build_single_prompt()` | compare.py:448 | 单问题提示词 |
| `build_multi_prompt()` | compare.py:480 | 多问题提示词 |
| `build_cross_dim_prompt()` | compare.py:546 | 跨步骤提示词 |
| `build_reference_list()` | compare.py:390 | 参考文献目录生成 |
| `analyze_comparison()` | compare.py:634 | 综述端点 |

### 3.3 已有规划文档

| 文档 | 内容 |
|------|------|
| `docs/SYNTHESIS_CURRENT_DESIGN.md` | AI 综述功能现状梳理 |
| `docs/SYNTHESIS_PROMPT_PLAN.md` | 综述提示词重构规划（468 行） |
| `docs/PENDING_PLANS.md` | 待实施计划表（P2/P3/P4） |

## 4. P2 实施建议

### 4.1 第一步：修复参考文献目录兜底逻辑

**目标**：解决 `None`、`佚名` 等显示问题

**修改文件**：`backend/routers/compare.py`

**修改内容**：
```python
def build_reference_list(papers: list) -> str:
    # 年份兜底
    year = paper.get('year')
    if not year:
        year = "年份不详"
    
    # 作者兜底
    if not authors:
        author_str = "佚名"
    # ... 其他逻辑
```

### 4.2 第二步：强化提示词引用约束

**目标**：减少正文引用退化为 `文献1/文献2` 的情况

**修改文件**：`backend/routers/compare.py`

**修改内容**：
- 在 `SYSTEM_PROMPT` 中增加显式禁止项
- 为每篇文献生成明确的引用锚点
- 要求模型必须使用系统提供的锚点

### 4.3 第三步：测试验证

**方法**：
1. 用测试集三篇论文生成综述
2. 检查参考文献目录格式
3. 检查正文引用质量
4. 对比改进前后效果

## 5. 后续计划（P3/P4）

| 优先级 | 事项 | 依赖 |
|--------|------|------|
| P3 | 综述提示词纳入提示词管理 | P2 |
| P4 | 综述引用锚点强化 | P2/P3 |

## 6. 启动新任务时的上下文

当用户启动新任务时，需要提供的信息：

1. **测试集已创建**：三篇高标准农田论文已完成七步法/四步法/长文本精读 + 参考文献梳理
2. **下一步**：验证综述质量，然后启动 P2 改进
3. **关键文件**：
   - `docs/SYNTHESIS_CURRENT_DESIGN.md` - 综述功能现状
   - `backend/routers/compare.py` - 综述核心代码
   - `scripts/batch_reading_test.py` - 测试集创建脚本
