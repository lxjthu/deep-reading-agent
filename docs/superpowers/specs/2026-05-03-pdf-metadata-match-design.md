# PDF 题录/元数据在线匹配增强 - 设计文档

> 日期：2026-05-03
> 状态：已批准
> 关联规划：[PDF_METADATA_MATCH_PLAN.md](../../PDF_METADATA_MATCH_PLAN.md)

## 1. 背景与目标

### 1.1 当前问题

- 文件名不规范时，标题匹配会失效
- 仅靠本地标题相似度，无法补全缺失的 DOI、作者、期刊等元数据
- 没有"提取 PDF 前几页"的专门代码，只有全量提取后截取前 3000 字符

### 1.2 目标

构建一条更稳的 PDF 元数据匹配链路：

1. 从 PDF 前 1-3 页提取高价值文本线索
2. 调用 DeepSeek 抽取结构化元数据
3. 基于结构化线索做在线候选检索与排序
4. 对高置信度候选自动补空字段，对中等置信度候选交给用户确认

### 1.3 约束

- **保守模式**：只补空字段，不覆盖已有的标题/作者/年份
- **中文文献**：不接 CNKI，依赖 DOI 反查 + 本地匹配
- **DeepSeek 模型**：使用 `deepseek-v4-flash`

## 2. 架构设计

### 2.1 总体流程

```
PDF 上传/选择文献
       ↓
┌─────────────────────────────────────┐
│  阶段 1：增强识别                    │
│  ├─ PDF 前 1-3 页文本提取            │
│  ├─ DOI/ISBN 正则提取               │
│  ├─ DeepSeek 结构化元数据抽取        │
│  └─ 本地题录匹配增强                 │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│  阶段 2：在线候选检索                │
│  ├─ DOI 直接查询                    │
│  ├─ Crossref API                   │
│  └─ OpenAlex API                   │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│  阶段 3：候选打分 + 应用策略         │
│  ├─ 多因子评分                      │
│  ├─ 高置信度自动补空字段            │
│  └─ 中置信度人工确认                │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│  阶段 4：前端交互                    │
│  ├─ 单篇在线匹配                    │
│  ├─ 候选确认 UI                     │
│  └─ 批量补全工具                    │
└─────────────────────────────────────┘
```

### 2.2 实施策略

采用渐进式分阶段实施，每阶段验证通过后再进入下一阶段：

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| 1a | PDF 前 1-3 页提取 + DeepSeek 结构化抽取 | 后端服务 + API |
| 1b | DOI 正则 + 本地匹配增强 | 增强现有匹配逻辑 |
| 2 | Crossref + OpenAlex 接入 | 在线候选检索服务 |
| 3 | 中文文献覆盖（DOI 反查 + 本地） | 补充逻辑 |
| 4 | 前端批量工具 + 单篇匹配 UI | 前端标签页/组件 |

## 3. 阶段 1 详细设计

### 3.1 PDF 前 1-3 页文本提取服务

**新增文件**：`backend/services/pdf_metadata_extract.py`

**核心函数**：

```python
def extract_front_matter(pdf_path: str, max_pages: int = 3) -> dict:
    """
    从 PDF 提取前 1-3 页的文本内容。

    返回：
    - page_1_full: 第一页完整文本
    - page_2_header: 第二页页眉 + 前 5 行
    - page_3_header: 第三页页眉 + 前 5 行
    - doi_candidates: 正则提取的 DOI 列表
    - isbn_candidates: 正则提取的 ISBN 列表
    """
```

**实现要点**：

- 使用 `pdfplumber`（已验证支持双栏 PDF）
- 第一页提取完整文本
- 第二、三页只提取页眉区域 + 前几行
- 同时运行 DOI/ISBN 正则提取

### 3.2 DeepSeek 结构化元数据抽取

**新增文件**：`backend/services/pdf_metadata_llm.py`

**核心函数**：

```python
def extract_metadata_with_llm(
    front_matter: dict,
    filename: str,
    api_key: str | None = None,
) -> dict:
    """
    调用 DeepSeek v4-flash 从 PDF 前几页文本中抽取结构化元数据。

    返回：
    - title: 标题
    - authors: 作者列表
    - year: 年份
    - journal: 期刊名
    - doi: DOI
    - volume: 卷号
    - issue: 期号
    - pages: 页码范围
    - language: 语言 (zh/en)
    - confidence: 抽置信度
    """
```

**Prompt 设计要点**：

- 输入：文件名 + 第一页全文 + 第二三页页眉
- 输出：严格 JSON
- 强调：不确定字段填 null，不要编造

### 3.3 本地匹配增强

**修改文件**：`backend/db/utils.py`

**增强内容**：

- 现有 `title_match_score()` 保持不变
- 新增 `compute_metadata_match_score()` 函数，综合考虑：
  - 标题相似度（权重最高）
  - 第一作者姓氏匹配（+0.08）
  - 年份一致（+0.05）
  - DOI 精确匹配（直接返回 1.0）

## 4. 阶段 2 详细设计

### 4.1 数据源抽象层

**新增文件**：`backend/services/metadata_sources.py`

**核心接口**：

```python
class MetadataSource(ABC):
    """元数据在线检索源基类"""

    @abstractmethod
    async def search_by_doi(self, doi: str) -> list[CandidateMetadata]:
        """通过 DOI 查询"""

    @abstractmethod
    async def search_by_metadata(
        self, title: str, authors: list[str], year: int | None
    ) -> list[CandidateMetadata]:
        """通过标题/作者/年份查询"""

@dataclass
class CandidateMetadata:
    """候选元数据"""
    title: str
    authors: list[str]
    year: int | None
    journal: str | None
    doi: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    source: str  # crossref/openalex/local
    raw_data: dict  # 原始返回数据
```

### 4.2 Crossref 实现

**新增文件**：`backend/services/crossref_source.py`

**实现要点**：

- 使用 Crossref REST API（免费，无需 API Key）
- 支持 DOI 直接查询
- 支持标题模糊搜索
- 有频率限制（默认 10 req/s，用 `mailto` 可提升到 50 req/s）

**API 端点**：

- `GET https://api.crossref.org/works/{doi}`
- `GET https://api.crossref.org/works?query={title}&rows=5`

### 4.3 OpenAlex 实现

**新增文件**：`backend/services/openalex_source.py`

**实现要点**：

- OpenAlex API 完全免费
- 支持 DOI、标题、作者搜索
- 数据质量高，覆盖范围广

**API 端点**：

- `GET https://api.openalex.org/works/doi:{doi}`
- `GET https://api.openalex.org/works?search={title}&per_page=5`

## 5. 阶段 3 详细设计

### 5.1 统一评分服务

**新增文件**：`backend/services/metadata_match_service.py`

**评分因子**：

| 因子 | 权重 | 说明 |
|------|------|------|
| DOI 精确匹配 | 直接 1.0 | 最强信号 |
| 标题相似度 | 0.45 | 用现有 `title_match_score()` |
| 第一作者匹配 | 0.20 | 姓氏匹配 |
| 作者集合重合度 | 0.10 | Jaccard 相似度 |
| 年份一致 | 0.10 | 完全一致加分 |
| 期刊名匹配 | 0.10 | 模糊匹配 |
| 语言一致 | 0.05 | zh/en 一致加分 |

**分档策略**：

- `>= 0.92`：高置信度，自动补空字段
- `0.78 - 0.92`：中等置信度，前端展示候选让用户确认
- `< 0.78`：低置信度，不展示

### 5.2 应用策略

**修改文件**：`backend/routers/library.py`

**新增端点**：

```python
@router.post("/entries/{entry_id}/match-online")
async def match_online(entry_id: str, ...):
    """对单篇文献执行在线匹配，返回候选列表"""

@router.post("/entries/{entry_id}/apply-match")
async def apply_match(entry_id: str, candidate_index: int, ...):
    """应用用户选中的候选元数据（只补空字段）"""

@router.post("/match-missing")
async def match_missing_metadata(...):
    """批量扫描缺失元数据的文献并给出候选"""
```

## 6. 阶段 4 详细设计

### 6.1 单篇匹配 UI

**新增组件**：`frontend/src/MetadataMatchPanel.tsx`

**交互流程**：

1. 用户在文献库点击某篇文献
2. 如果元数据不完整（缺 DOI/作者/期刊），显示"在线匹配"按钮
3. 点击后调用 `/match-online` API
4. 展示候选列表，每个候选显示：标题、作者、年份、期刊、DOI、来源、置信度
5. 用户选择一个候选，点击"应用"
6. 调用 `/apply-match` API，只补空字段

### 6.2 批量补全工具

**新增组件**：`frontend/src/MetadataBatchPanel.tsx`

**交互流程**：

1. 显示当前用户所有缺失元数据的文献列表
2. 用户点击"批量扫描"
3. 后端逐篇执行在线匹配（异步任务）
4. 前端展示进度和结果
5. 高置信度结果自动应用
6. 中置信度结果待用户确认

## 7. 数据库变更

**无需新增表**，只需在现有 `BibEntry` 上操作。

可能需要新增字段（可选）：

- `online_match_status`：在线匹配状态（none/matched/confirmed）
- `online_match_confidence`：最近一次在线匹配的置信度
- `online_match_source`：匹配来源（crossref/openalex）

## 8. API 设计汇总

| 端点 | 方法 | 作用 |
|------|------|------|
| `/api/library/entries/{entry_id}/match-online` | POST | 单篇在线匹配 |
| `/api/library/entries/{entry_id}/apply-match` | POST | 应用候选元数据 |
| `/api/library/match-missing` | POST | 批量扫描缺失元数据 |

## 9. 风险控制

1. **API 依赖风险**：Crossref/OpenAlex 有频率限制，需要做请求队列
2. **数据覆盖风险**：保守模式只补空字段，不覆盖已有数据
3. **识别错误风险**：中置信度候选需人工确认
4. **中文文献风险**：不接 CNKI，依赖 DOI 反查 + 本地匹配

## 10. 测试规划

### 10.1 单元测试

- PDF 前几页文本提取
- DOI/ISBN 正则提取
- DeepSeek 元数据抽取
- 候选评分逻辑

### 10.2 集成测试

- 单篇完整匹配流程
- 批量匹配流程
- API 错误处理

### 10.3 数据质量验收

- 1 篇中文社科 PDF
- 1 篇英文论文 PDF
- 1 篇 DOI 明确的 PDF

## 11. 相关文件

### 新增文件

- `backend/services/pdf_metadata_extract.py`
- `backend/services/pdf_metadata_llm.py`
- `backend/services/metadata_sources.py`
- `backend/services/crossref_source.py`
- `backend/services/openalex_source.py`
- `backend/services/metadata_match_service.py`
- `frontend/src/MetadataMatchPanel.tsx`
- `frontend/src/MetadataBatchPanel.tsx`

### 修改文件

- `backend/db/utils.py` - 新增 `compute_metadata_match_score()`
- `backend/routers/library.py` - 新增在线匹配端点
- `backend/routers/upload.py` - 集成增强匹配逻辑
