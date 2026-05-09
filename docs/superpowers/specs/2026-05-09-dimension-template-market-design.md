# Phase 3 高级功能设计文档：模板市场 + AI生成 + 文档导入

> **版本**: v1.0  
> **日期**: 2026-05-09  
> **状态**: 设计完成，待审查  
> **前置**: [CUSTOM_DIMENSION_PLAN.md](../CUSTOM_DIMENSION_PLAN.md)、[CUSTOM_DIMENSION_PHASE2_DESIGN.md](../CUSTOM_DIMENSION_PHASE2_DESIGN.md)

---

## 1. 设计目标

在 Phase 1（后端 API）和 Phase 2（前端维度管理 UI）完成后，实现三大高级功能：

1. **模板市场**：提供"案例研究通用"、"社会网络分析框架"、"Ostrom框架"三套预置模板
2. **AI 自动生成**：用户上传种子论文（PDF/MD），系统自动生成定制化维度模板
3. **文档导入**：支持用户上传 TXT/MD/JSON 文档，自动解析为维度集合

---

## 2. 预置模板设计

### 2.1 模板清单

| 模板名称 | 维度数 | 来源文档 | 适用领域 |
|----------|--------|----------|----------|
| **默认维度集**（现有） | 12 | 系统内置 | 计量/实证论文通用 |
| **案例研究通用框架** | 12 | `12维度案例分析.txt` | 案例研究方法论 |
| **社会网络分析框架** | 12 | `社会学案例分析.txt` | 社会网络、社会资本、嵌入性 |
| **Ostrom制度分析框架** | 20 | `基于Ostrom IAD与SES框架...txt` | 公共池塘资源、制度分析、SES |

### 2.2 标准化格式

所有预置模板统一为以下结构（适配 `dimension_items` 表）：

```yaml
dim_name: "维度名称（中文，6-12字）"
description: "维度描述（一句话概括核心分析对象，20-40字）"
default_question: "默认分析问题（用户未输入自定义问题时使用）"
prompt_content: |
  【分析维度：{dim_name}】
  
  {default_question}
  
  要求：
  1. {子问题1：事实识别层面，要求引用原文}
  2. {子问题2：逻辑评估层面，判断论证是否成立}
  3. {子问题3：批判判断层面，指出潜在缺陷或替代解释}
  4. 直接输出分析，不做铺垫性表述
group_name: "所属分组（核心维度/方法论维度/理论维度/批判维度）"
```

**特殊处理**：
- Ostrom 模板的"前导：框架定位"作为集合级别的 `description`
- 或通过 `group_name = "__preface"` 标记为前置说明，不进入 checkbox 列表

### 2.3 Ostrom 20 维度分组方案

为解决 20 维度在 UI 中的展示问题，采用**分组折叠**设计：

| 分组 | 维度 | 数量 |
|------|------|------|
| **核心行动情境** | 行动情境边界、参与者属性、互动结构 | 3 |
| **规则与制度** | 规则类型识别、规则起源演化、监督执行制裁 | 3 |
| **资源与治理** | 资源系统特征、治理系统配置、使用者社会属性、外部环境嵌套 | 4 |
| **评估与对话** | 设计原则对照、本土化适配、治理绩效评估、系统韧性、跨尺度互动、多中心评估、框架规范性、学术对话、核心发现、根本局限 | 10 |

**UI 展示规则**：
- 默认展开前 2 组（6 个维度），折叠后 2 组
- 每组内双列排列，节省垂直空间
- 提供"展开全部"按钮

---

## 3. 数据库设计

### 3.1 新增表：dimension_templates（模板市场）

```sql
CREATE TABLE dimension_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,              -- "Ostrom制度分析框架"
    description     TEXT,                       -- 模板描述
    category        TEXT NOT NULL,              -- "制度分析"/"社会网络"/"案例研究"
    dim_count       INTEGER NOT NULL,           -- 维度数量
    preview_json    TEXT,                       -- 前3个维度的预览（JSON）
    group_config    TEXT,                       -- 分组配置（JSON，如 {"groups": [...]}）
    is_featured     INTEGER DEFAULT 1,          -- 是否在市场显示
    sort_order      INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE template_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER NOT NULL REFERENCES dimension_templates(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,              -- 维度英文标识
    dim_name        TEXT NOT NULL,              -- 中文显示名
    description     TEXT,
    prompt_content  TEXT NOT NULL,
    default_question TEXT NOT NULL,
    sort_order      INTEGER,
    group_name      TEXT,                       -- 所属分组
    is_builtin      INTEGER DEFAULT 1
);
```

### 3.2 种子数据填充

在 `main.py` 启动时调用：

```python
async def ensure_dimension_templates(db: AsyncSession) -> None:
    """确保系统预置模板存在"""
    templates = [
        {
            "name": "案例研究通用框架",
            "description": "适用于案例研究类论文的通用分析框架，涵盖研究设计、因果机制、可推广性等核心维度",
            "category": "案例研究",
            "dim_count": 12,
            "group_config": None,  # 12维无需分组
            "dimensions": [...]  # 从 12维度案例分析.txt 解析
        },
        {
            "name": "社会网络分析框架", 
            "description": "聚焦社会网络、社会资本与嵌入性，以资深社会学家视角展开系统性精读",
            "category": "理论分析",
            "dim_count": 12,
            "group_config": None,
            "dimensions": [...]  # 从 社会学案例分析.txt 解析
        },
        {
            "name": "Ostrom制度分析框架",
            "description": "基于IAD框架与SES框架，系统解析公共池塘资源、集体行动与治理制度的案例研究",
            "category": "制度分析",
            "dim_count": 20,
            "group_config": json.dumps({
                "groups": [
                    {"name": "核心行动情境", "order": 0},
                    {"name": "规则与制度", "order": 1},
                    {"name": "资源与治理", "order": 2},
                    {"name": "评估与对话", "order": 3}
                ]
            }),
            "dimensions": [...]  # 从 Ostrom IAD...txt 解析
        }
    ]
    # ... 检查存在性并填充
```

---

## 4. 模板市场 UI 设计

### 4.1 入口位置

在 `PromptsTab` 中增加第三个子 Tab："模板市场"

```
┌─ 提示词管理 ─┬─ 维度管理 ─┬─ 模板市场 ─┐
```

### 4.2 界面布局

```
┌─ 模板市场 ───────────────────────────────────────────┐
│                                                      │
│  [全部] [案例研究] [制度分析] [社会网络] [AI生成]       │
│                                                      │
│  ┌─ Ostrom制度分析框架 ──────────────┐               │
│  │ ⭐ 推荐 · 20个维度 · 制度分析       │               │
│  │                                    │               │
│  │ 基于IAD框架与SES框架，系统解析...   │               │
│  │                                    │               │
│  │ 预览：行动情境边界、规则类型识别、  │               │
│  │        设计原则对照、多中心治理...  │               │
│  │                                    │               │
│  │ [查看详情] [一键导入]              │               │
│  └────────────────────────────────────┘               │
│                                                      │
│  ┌─ 社会网络分析框架 ────────────────┐               │
│  │ 12个维度 · 理论分析               │               │
│  │ ...                               │               │
│  │ [查看详情] [一键导入]             │               │
│  └────────────────────────────────────┘               │
│                                                      │
│  ┌─ 案例研究通用框架 ────────────────┐               │
│  │ 12个维度 · 案例研究               │               │
│  │ ...                               │               │
│  │ [查看详情] [一键导入]             │               │
│  └────────────────────────────────────┘               │
│                                                      │
│  ┌─ 🪄 AI生成专属模板 ──────────────┐               │
│  │ 上传种子论文，自动生成定制化      │               │
│  │ 分析维度...                       │               │
│  │ [开始生成]                        │               │
│  └────────────────────────────────────┘               │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 4.3 模板详情弹窗

点击"查看详情"后弹出：

```
┌─ Ostrom制度分析框架 ──────────── [X] ┐
│                                     │
│ 20个分析维度 · 制度分析            │
│                                     │
│ 基于IAD框架与SES框架...             │
│                                     │
│ ┌─ 维度列表 ─────────────────────┐ │
│ │ 1. 行动情境的边界界定          │ │
│ │ 2. 参与者的位置与属性          │ │
│ │ 3. 行动与互动结构              │ │
│ │ ...                            │ │
│ │ 20. 根本局限与改进方向         │ │
│ └────────────────────────────────┘ │
│                                     │
│ [一键导入到我的集合]                │
└─────────────────────────────────────┘
```

---

## 5. AI 自动生成设计

### 5.1 用户流程

```
用户打开模板市场 → 点击"AI生成专属模板"
  → 弹出生成向导：
    
    步骤1：上传种子论文
    ┌─ 选择文件 ─────────────────────┐
    │ 支持 PDF / Markdown            │
    │ [拖拽文件到这里，或点击选择]   │
    │                                │
    │ 或从文献库选择：               │
    │ [▼ 选择已上传的论文]           │
    └────────────────────────────────┘
    
    步骤2：补充信息（可选）
    ┌─ 补充配置 ─────────────────────┐
    │ 学科领域：[▼ 自动识别/社会学...]│
    │ 期望维度数：[12 ▼] (8/12/16/20)│
    │ 分析深度：[标准 ▼] (标准/深入)  │
    └────────────────────────────────┘
    
    步骤3：生成中...
    ┌─ 生成进度 ─────────────────────┐
    │ 🔄 正在分析论文...             │
    │ ⏳ 正在设计维度...             │
    │ ⏳ 正在生成提示词...           │
    │                                │
    │ [取消]                         │
    └────────────────────────────────┘
    
    步骤4：预览与编辑
    ┌─ 生成结果预览 ─────────────────┐
    │ 识别结果：                     │
    │ · 学科：经济学—产业经济学      │
    │ · 类型：定量实证               │
    │ · 理论：技术变革理论           │
    │                                │
    │ 生成维度（14个）：             │
    │ ☑ 研究问题定位                 │
    │ ☑ 理论框架评估                 │
    │ ☑ AI词典构建方法论             │
    │ ...                            │
    │                                │
    │ [重新生成] [编辑维度] [保存]   │
    └────────────────────────────────┘
```

### 5.2 元提示词设计（最终版）

基于测试对比（v1/v2 通过，v3 超时），采用 **v2 优化版**：

```markdown
你是一位资深的学术论文分析专家。请根据以下论文内容，设计一套系统性的案例分析维度体系。

【论文内容】
{{paper_text}}

【任务说明】
1. 先对论文进行快速解析，识别：学科归属、研究类型、理论传统、核心变量(X→Y)、方法论特征
2. 基于识别结果，从以下维度池中选择最适合该论文的 {{dim_count}} 个维度：

   基础维度（必选）：研究问题定位、理论框架评估、数据来源与方法论、因果机制分析、可推广性评估、整体评价
   
   条件维度（根据论文特征选择）：
   - 案例研究类：案例选择逻辑、案例呈现方式、过程追踪
   - 定量实证类：识别策略、统计结果解读、稳健性检验
   - 制度分析类：制度情境、规则体系、治理结构
   - 网络/关系类：网络结构、社会资本、嵌入性
   - 产业经济类：市场结构、价值链、产业政策
   - 公共资源类：行动情境、设计原则、多中心治理
   - 政策评估类：政策含义、因果识别

3. 为每个维度生成完整的提示词

【输出格式】
严格按以下 JSON 输出，不要添加任何解释或markdown标记：

{
  "paper_analysis": {
    "discipline": "一级学科—二级学科",
    "research_type": "研究类型",
    "theory_tradition": "理论传统",
    "core_x": "解释变量",
    "core_y": "被解释变量",
    "methodology": "方法论特征"
  },
  "template": {
    "name": "模板名称（学科+研究类型+分析框架）",
    "description": "该模板适用于什么类型的论文",
    "category": "案例研究/定量实证/混合方法/理论建构",
    "dimension_count": 12
  },
  "dimensions": [
    {
      "dim_name": "维度名称（6-12字，专业术语）",
      "description": "分析焦点（20-40字）",
      "default_question": "默认分析问题",
      "prompt_content": "【分析维度：维度名称】\n\n默认问题\n\n要求：\n1. 子问题1（事实识别：引用原文段落/数据/方法）\n2. 子问题2（逻辑评估：判断论证是否成立）\n3. 子问题3（批判判断：指出潜在缺陷或替代解释）\n4. 直接输出分析，不做铺垫性表述",
      "group_name": "核心维度/方法论维度/理论维度/批判维度",
      "rationale": "为什么选这个维度的简要说明"
    }
  ]
}

【质量规范】
1. 维度名称使用学科专业术语，避免通用表达
2. 子问题从"事实识别→逻辑评估→批判判断"递进
3. 至少一个维度包含对典型方法论缺陷的质疑
4. 全篇术语统一，使用同一理论传统的话语体系
5. 维度之间互补不重复
```

### 5.3 技术实现

**后端服务**：

```python
# backend/services/ai_template_generator.py

from typing import Optional
import json
from openai import OpenAI
from backend.utils.api_key import validate_deepseek_key

MODEL = "deepseek-chat"  # 使用 chat 模型，比 reasoner 更快
MAX_TOKENS = 4000

async def generate_template_from_paper(
    paper_text: str,
    api_key: str,
    dim_count: int = 12,
    discipline_hint: Optional[str] = None,
) -> dict:
    """
    基于论文内容生成维度模板
    """
    api_key = validate_deepseek_key(api_key)
    
    # 截取前 8000 字（约 150k 字符的 1/3，控制成本）
    text = paper_text[:8000]
    
    # 构建元提示词
    meta_prompt = f"""你是一位资深的学术论文分析专家..."""  # 见上文
    
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个专业的学术论文分析助手，擅长设计多维度的论文精读分析框架。你必须严格按照用户要求的JSON格式输出，不要添加任何markdown标记或解释性文字。"},
            {"role": "user", "content": meta_prompt}
        ],
        temperature=0.7,
        max_tokens=MAX_TOKENS,
    )
    
    content = response.choices[0].message.content
    
    # 解析 JSON
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()
        
        result = json.loads(json_str)
        return result
    except json.JSONDecodeError:
        # 返回原始内容，让上层处理
        return {"error": "JSON解析失败", "raw_content": content}
```

**API 路由**：

```python
# backend/routers/dimensions.py

@router.post("/templates/generate")
async def generate_template(
    request: Request,
    file_id: Optional[int] = None,  # 从文献库选择
    file_upload: Optional[UploadFile] = None,  # 直接上传
    dim_count: int = 12,
    api_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """AI生成维度模板"""
    # 1. 获取论文文本
    if file_id:
        file_record = await db.get(File, file_id)
        text = extract_text_from_file(file_record.path)
    elif file_upload:
        text = await extract_text_from_upload(file_upload)
    else:
        raise HTTPException(400, "请提供 file_id 或 file_upload")
    
    # 2. 调用生成服务
    result = await generate_template_from_paper(
        paper_text=text,
        api_key=api_key,
        dim_count=dim_count,
    )
    
    if "error" in result:
        raise HTTPException(500, result["error"])
    
    # 3. 返回生成结果（不自动保存，让用户预览后确认）
    return result
```

### 5.4 成本与性能优化

| 优化策略 | 说明 |
|----------|------|
| **文本截取** | 仅取前 8000 字符（约 2-3 页），足够识别论文特征 |
| **模型选择** | 使用 `deepseek-chat`（比 reasoner 快 3-5 倍，成本低 50%） |
| **结果缓存** | 同一论文 MD5 哈希结果缓存 24 小时 |
| **流式输出** | 使用 SSE 流式返回，用户可实时看到生成进度 |
| **重试机制** | JSON 解析失败时自动重试 2 次，每次调整 temperature |

---

## 6. 文档导入设计

### 6.1 支持格式

| 格式 | 说明 | 优先级 |
|------|------|--------|
| **.txt** | 纯文本，如现有的三个预置文档 | P0 |
| **.md** | Markdown，支持标准格式 | P0 |
| **.json** | 标准化 JSON，便于与其他工具集成 | P1 |

### 6.2 解析规则

对于 txt/md 格式，采用启发式解析：

```python
def parse_dimension_document(text: str) -> dict:
    """
    解析维度文档为标准格式
    支持格式：
    - # 标题（模板名称）
    - > 描述（模板描述）
    - ## 维度 N：维度名称 / ## 前导：框架定位
    - **描述：** 维度描述
    - **默认问题：** 默认问题
    - ``` 提示词内容 ```
    """
    result = {
        "template_name": "",
        "description": "",
        "dimensions": []
    }
    
    lines = text.split('\n')
    current_dim = None
    in_code_block = False
    code_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # 模板标题
        if stripped.startswith('# ') and not result["template_name"]:
            result["template_name"] = stripped[2:].strip()
        
        # 模板描述
        elif stripped.startswith('> ') and not result["description"]:
            result["description"] = stripped[2:].strip()
        
        # 维度标题（支持多种格式）
        elif stripped.startswith('## '):
            # 保存上一个维度
            if current_dim and not in_code_block:
                if code_content:
                    current_dim["prompt_content"] = '\n'.join(code_content)
                    code_content = []
                result["dimensions"].append(current_dim)
            
            dim_title = stripped[3:].strip()
            # 解析 "维度 1：名称" 或 "前导：框架定位"
            if '：' in dim_title or ':' in dim_title:
                parts = dim_title.replace(':', '：').split('：', 1)
                prefix = parts[0].strip()
                name = parts[1].strip()
                
                current_dim = {
                    "dim_name": name,
                    "prefix": prefix,
                    "description": "",
                    "default_question": "",
                    "prompt_content": "",
                    "group_name": "核心维度"  # 默认分组
                }
        
        # 维度描述
        elif stripped.startswith('**描述：**') and current_dim and not in_code_block:
            current_dim["description"] = stripped.replace('**描述：**', '').strip()
        
        # 默认问题
        elif stripped.startswith('**默认问题：**') and current_dim and not in_code_block:
            current_dim["default_question"] = stripped.replace('**默认问题：**', '').strip()
        
        # 代码块（提示词内容）
        elif stripped.startswith('```'):
            if in_code_block:
                # 结束代码块
                current_dim["prompt_content"] = '\n'.join(code_content)
                code_content = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
        elif in_code_block and current_dim:
            code_content.append(line)
    
    # 保存最后一个维度
    if current_dim and not in_code_block:
        if code_content:
            current_dim["prompt_content"] = '\n'.join(code_content)
        result["dimensions"].append(current_dim)
    
    return result
```

### 6.3 用户流程

```
用户打开维度管理 → 点击"从文档导入"
  → 弹出导入向导：
    
    步骤1：上传文件
    ┌─ 上传维度文档 ───────────────────┐
    │ 支持 .txt / .md / .json         │
    │ [拖拽文件到这里，或点击选择]    │
    │                                 │
    │ 提示：可从其他大模型生成提示词  │
    │ 后导出为txt/md，再导入此处      │
    └─────────────────────────────────┘
    
    步骤2：预览解析结果
    ┌─ 解析预览 ──────────────────────┐
    │ 识别到模板：Ostrom制度分析框架   │
    │ 共 20 个维度                     │
    │                                  │
    │ ┌─ 维度列表 ──────────────────┐ │
    │ │ ☑ 行动情境的边界界定        │ │
    │ │ ☑ 参与者的位置与属性        │ │
    │ │ ☑ 行动与互动结构            │ │
    │ │ ...                         │ │
    │ └─────────────────────────────┘ │
    │                                  │
    │ [编辑] [重新解析] [确认导入]    │
    └─────────────────────────────────┘
    
    步骤3：保存为集合
    ┌─ 保存设置 ──────────────────────┐
    │ 集合名称：[Ostrom制度分析框架]   │
    │ 描述：[基于IAD与SES框架...]     │
    │                                  │
    │ [设为激活集合] ☑                 │
    │                                  │
    │ [保存]                           │
    └─────────────────────────────────┘
```

### 6.4 错误处理

文档导入失败时，前端显示明确错误信息：

```
┌─ 导入失败 ──────────────────────────┐
│ ⚠️ 文档解析失败                      │
│                                      │
│ 无法识别该文档的维度结构。           │
│                                      │
│ 可能原因：                           │
│ • 文档格式不符合标准（缺少维度标题） │
│ • PDF 文件过大导致解析超时           │
│                                      │
│ 建议操作：                           │
│ 1. 检查文档是否包含 "## 维度 N："   │
│    格式的标题                        │
│ 2. 如为 PDF 文件，可前往百度        │
│    PaddleOCR 将 PDF 转换为          │
│    Markdown 后重试                   │
│                                      │
│ [重新上传] [查看格式示例]            │
└─────────────────────────────────────┘
```

**错误类型映射**：

| 错误类型 | 提示信息 | 建议操作 |
|----------|----------|----------|
| `INVALID_FORMAT` | 文档格式不符合标准 | 查看格式示例，确保包含维度标题 |
| `NO_DIMENSIONS_FOUND` | 未识别到任何维度 | 检查文档结构，参考模板示例 |
| `PDF_PARSE_ERROR` | PDF 解析失败 | 转换为 Markdown 后重试 |
| `FILE_TOO_LARGE` | 文件超过 5MB 限制 | 压缩或拆分文档 |
| `UNSUPPORTED_ENCODING` | 编码格式不支持 | 保存为 UTF-8 编码后重试 |

### 6.5 与 AI 生成的联动

用户可以在其他大模型（如 Claude、GPT-4）中使用我们的元提示词生成维度模板，导出为 txt/md 后导入本系统：

```markdown
## 跨平台工作流

1. 在本系统下载"元提示词模板"（一个标准的 prompt 文件）
2. 将元提示词 + 种子论文提交给 Claude/GPT-4
3. 获得生成的维度体系（txt/md 格式）
4. 将生成的文档导入本系统
5. 自动解析为维度集合，可直接使用
```

---

## 7. API 设计

### 7.1 模板市场 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/dimensions/templates` | GET | 获取所有预置模板列表 |
| `/api/dimensions/templates/{id}` | GET | 获取模板详情（含维度列表） |
| `/api/dimensions/templates/{id}/import` | POST | 导入模板到用户集合 |

### 7.2 AI 生成 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/dimensions/generate` | POST | 上传论文生成维度模板（返回预览，不保存） |
| `/api/dimensions/generate/save` | POST | 将预览的生成结果保存为集合 |

### 7.3 文档导入 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/dimensions/import/preview` | POST | 上传文档，返回解析预览 |
| `/api/dimensions/import/confirm` | POST | 确认导入，保存为集合 |

---

## 8. 实施顺序

| 阶段 | 内容 | 预估工时 | 产出 |
|------|------|----------|------|
| **Phase 3a** | 1. 标准化三个预置模板<br>2. 设计 group_config 分组机制<br>3. 数据库迁移（dimension_templates + template_items）<br>4. 种子数据填充<br>5. 模板市场 UI<br>6. "一键导入"功能<br>7. LongTab 分组适配 | 3-4 天 | 用户可使用三个预置模板 |
| **Phase 3b** | 1. AI 生成元提示词优化<br>2. 论文上传/选择 UI<br>3. 生成进度展示<br>4. 生成结果预览/编辑<br>5. 后端生成服务<br>6. 结果缓存 | 3-4 天 | 用户可从论文生成维度模板 |
| **Phase 3c** | 1. 文档上传/解析 UI<br>2. txt/md/json 解析器<br>3. 解析结果预览/编辑<br>4. 跨平台工作流文档 | 2-3 天 | 用户可上传文档创建集合 |

---

## 9. 测试计划

### 9.1 预置模板测试

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 新用户打开模板市场 | 显示3个预置模板 |
| 2 | 导入 Ostrom 框架 | 创建20维度集合，分组正确 |
| 3 | LongTab 显示 Ostrom 维度 | 双列分组展示，默认折叠后2组 |
| 4 | 导入社会网络框架 | 12维度，无分组，单列展示 |

### 9.2 AI 生成测试

| # | 场景 | 验证点 |
|---|------|--------|
| 5 | 上传 PDF 生成模板 | 正确提取文本，生成12-16维度 |
| 6 | 上传 MD 生成模板 | 正确解析，生成结果合理 |
| 7 | 生成结果预览 | 显示论文分析 + 维度列表 |
| 8 | 保存生成结果 | 创建新集合，可激活使用 |
| 9 | 同一论文再次生成 | 命中缓存，快速返回 |

### 9.3 文档导入测试

| # | 场景 | 验证点 |
|---|------|--------|
| 10 | 导入 Ostrom txt | 正确解析20维度 |
| 11 | 导入社会网络 txt | 正确解析12维度 |
| 12 | 导入不标准文档 | 给出错误提示或部分解析 |
| 13 | 导入后编辑维度 | 可修改名称/提示词/分组 |

---

## 10. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| AI 生成质量不稳定 | 提供"重新生成"按钮；允许用户编辑后再保存 |
| 20维度在移动端显示拥挤 | 小屏设备自动改为单列 + 虚拟滚动 |
| 文档解析失败 | **直接报错，不显示部分结果**。提示用户检查文档格式，或前往百度 PaddleOCR 将 PDF 转换为 Markdown 后上传 |
| 元提示词被滥用 | 生成结果加水印/标识；限制生成频率 |
| PDF 文本提取失败 | 自动回退到 OCR；提供"粘贴文本"备用方案 |
| 生成耗时过长 | 使用流式输出；显示进度条；支持取消 |

---

## 11. 与现有系统的关系

| 组件 | 改造后行为 | 兼容性 |
|------|-----------|--------|
| `dimension_sets` | 用户集合表，不变 | 兼容 |
| `dimension_items` | 用户维度表，不变 | 兼容 |
| `dimension_templates` | **新增**：系统预置模板 | 新表 |
| `template_items` | **新增**：模板维度条目 | 新表 |
| `PromptsTab` | 增加"模板市场"子 Tab | 向后兼容 |
| `LongTab` | 支持分组展示（当 group_config 存在时） | 向后兼容 |
| `conversation_engine.py` | 不变，继续复用 | 无影响 |

---

## 12. 附录：元提示词完整版

### 12.1 用于系统 AI 生成的元提示词

```markdown
你是一位资深的学术论文分析专家。请根据以下论文内容，设计一套系统性的案例分析维度体系。

【论文内容】
{{paper_text}}

【任务说明】
1. 先对论文进行快速解析，识别：学科归属、研究类型、理论传统、核心变量(X→Y)、方法论特征
2. 基于识别结果，从以下维度池中选择最适合该论文的 {{dim_count}} 个维度：

   基础维度（必选）：
   - 研究问题与学科定位
   - 理论框架与概念体系
   - 数据来源与方法论
   - 因果机制与论证链条
   - 可推广性与理论贡献
   - 整体评价与核心局限
   
   条件维度（根据论文特征选择）：
   - 案例研究类：案例选择逻辑、案例呈现方式、过程追踪
   - 定量实证类：识别策略与内生性处理、统计结果解读、稳健性检验
   - 制度分析类：制度情境与历史脉络、规则体系分析、治理结构
   - 网络/关系类：社会网络结构、社会资本类型、嵌入性分析
   - 产业经济类：市场结构、价值链治理、产业政策
   - 公共资源类：行动情境边界、设计原则对照、多中心治理
   - 政策评估类：政策含义与实践转化、政策因果识别

3. 为每个维度生成完整的提示词，遵循以下规范：
   - 维度名称：6-12字，使用学科专业术语
   - 描述：一句话说明分析焦点（20-40字）
   - 默认问题：用户可见的默认分析问题
   - 提示词内容：包含3条操作化要求 + 固定结尾
   - 分组：核心维度/方法论维度/理论维度/批判维度

【输出格式】
严格按以下 JSON 输出，不要添加任何解释或markdown标记：

{
  "paper_analysis": {
    "discipline": "一级学科—二级学科",
    "research_type": "研究类型",
    "theory_tradition": "理论传统",
    "core_x": "解释变量",
    "core_y": "被解释变量",
    "methodology": "方法论特征"
  },
  "template": {
    "name": "模板名称（学科+研究类型+分析框架）",
    "description": "该模板适用于什么类型的论文",
    "category": "案例研究/定量实证/混合方法/理论建构",
    "dimension_count": 12
  },
  "dimensions": [
    {
      "dim_name": "维度名称（6-12字，专业术语）",
      "description": "分析焦点（20-40字）",
      "default_question": "默认分析问题",
      "prompt_content": "【分析维度：维度名称】\n\n默认问题\n\n要求：\n1. 子问题1（事实识别：引用原文段落/数据/方法）\n2. 子问题2（逻辑评估：判断论证是否成立）\n3. 子问题3（批判判断：指出潜在缺陷或替代解释）\n4. 直接输出分析，不做铺垫性表述",
      "group_name": "核心维度/方法论维度/理论维度/批判维度",
      "rationale": "为什么选这个维度的简要说明"
    }
  ]
}

【质量规范】
1. 维度名称使用学科专业术语，避免通用表达
2. 子问题从"事实识别→逻辑评估→批判判断"递进
3. 至少一个维度包含对典型方法论缺陷的质疑
4. 全篇术语统一，使用同一理论传统的话语体系
5. 维度之间互补不重复
6. 维度总数控制在 {{dim_count}} 个左右（±2）
```

### 12.2 用于跨平台分享的简化元提示词

```markdown
请根据以下论文，生成一套多维度精读分析框架。

论文：{{paper_text}}

要求：
1. 生成 10-16 个分析维度
2. 每个维度包含：名称、描述、默认问题、3条分析要求
3. 最后一条要求固定为"直接输出分析，不做铺垫性表述"
4. 按以下格式输出（可复制到文本编辑器保存为 .md）：

# [模板名称]
> [模板描述]

## 维度 1：[名称]
**描述：** [一句话描述]
**默认问题：** [问题]
```
[分析要求]
```

## 维度 2：[名称]
...
```

---

## 文档历史

| 日期 | 版本 | 变更说明 |
|------|------|----------|
| 2026-05-09 | v1.0 | 初始设计文档，包含模板市场、AI生成、文档导入三大功能 |
