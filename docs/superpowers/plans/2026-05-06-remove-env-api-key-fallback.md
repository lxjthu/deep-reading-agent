# 移除 env API Key 回退，强制使用前端用户 Key

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 所有 Web 后端路径只使用前端传入的用户 DeepSeek API Key，不读 .env 兜底；key 无效时给出明确错误提示引导用户去 DeepSeek 平台重新生成。

**Architecture:** 创建统一的 `validate_deepseek_key()` 验证函数，消除后端 service 层的 `os.getenv` 回退，将混合模式（参数优先 + env 兜底）改为纯参数模式。CLI/离线脚本保持 env 读取但统一错误格式。

**Tech Stack:** Python, FastAPI, OpenAI SDK

---

## 文件变更清单

| 操作 | 文件 | 职责 |
|------|------|------|
| **创建** | `backend/utils/__init__.py` | 包初始化 |
| **创建** | `backend/utils/api_key.py` | 统一 key 验证函数 |
| **修改** | `backend/services/deepseek_refs.py:326-331` | 删除 env 回退 |
| **修改** | `backend/services/pdf_metadata_llm.py:78-81` | 删除 env 回退 |
| **修改** | `smart_literature_filter.py:52-56` | 删除 env 兜底 |
| **修改** | `smart_segment_router.py:61-65` | 删除 env 兜底 |
| **修改** | `new_architecture/config.py:31-34` | from_key 加校验 |
| **修改** | `backend/routers/library.py:399` | 加 key 校验 |

---

### Task 1: 创建统一 API Key 验证模块

**Files:**
- Create: `backend/utils/__init__.py`
- Create: `backend/utils/api_key.py`

- [ ] **Step 1: 创建 `backend/utils/__init__.py`**

空文件即可，使 `backend/utils/` 成为 Python 包。

- [ ] **Step 2: 创建 `backend/utils/api_key.py`**

```python
"""统一的 DeepSeek API Key 验证工具。"""

from typing import Optional


def validate_deepseek_key(api_key: Optional[str], *, source: str = "前端设置") -> str:
    """
    验证并返回有效的 DeepSeek API key。

    Args:
        api_key: 用户提供的 API key（可能为 None 或空字符串）
        source: 错误提示中的来源描述，如 "前端设置" 或 "环境变量"

    Returns:
        清洗后的有效 API key 字符串

    Raises:
        ValueError: key 为空、格式错误或为占位符时抛出
    """
    if not api_key or not api_key.strip():
        raise ValueError(
            f"未提供 DeepSeek API Key。请在{source}中输入你的 Key。"
        )

    key = api_key.strip()

    if key in ("sk-xxx", "sk-xxxx", "sk-your-key", "your-api-key"):
        raise ValueError(
            f"API Key 为占位符，不可使用。"
            f"请前往 https://platform.deepseek.com/api_keys 生成新的 Key，"
            f"然后在{source}中更新。"
        )

    if not key.startswith("sk-"):
        raise ValueError(
            f"API Key 格式错误（应以 sk- 开头）。"
            f"请前往 https://platform.deepseek.com/api_keys 生成正确的 Key，"
            f"然后在{source}中更新。"
        )

    if len(key) < 20:
        raise ValueError(
            f"API Key 长度不足，可能不完整。"
            f"请前往 https://platform.deepseek.com/api_keys 重新复制完整的 Key，"
            f"然后在{source}中更新。"
        )

    return key
```

- [ ] **Step 3: 验证模块可导入**

Run: `python -c "from backend.utils.api_key import validate_deepseek_key; print('OK')"`
Expected: `OK`

---

### Task 2: 消除 `backend/services/deepseek_refs.py` 的 env 回退

**Files:**
- Modify: `backend/services/deepseek_refs.py`

当前代码（行 326-331）：
```python
    api_key: Optional[str] = None,
) -> Optional[dict]:
    if not api_key or not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
```

- [ ] **Step 1: 替换为统一验证函数**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将行 328-331 替换为：
```python
    api_key = validate_deepseek_key(api_key)
```

最终该函数变为：
```python
def call_deepseek_json(
    messages: list[dict],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    api_key = validate_deepseek_key(api_key)
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py').read()); print('OK')"`
Expected: `OK`

---

### Task 3: 消除 `backend/services/pdf_metadata_llm.py` 的 env 回退

**Files:**
- Modify: `backend/services/pdf_metadata_llm.py`

当前代码（行 78-81）：
```python
    if not api_key or not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
```

- [ ] **Step 1: 添加导入并替换**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将行 78-81 替换为：
```python
    api_key = validate_deepseek_key(api_key)
```

最终该函数变为：
```python
def extract_metadata_with_llm(
    front_matter: dict,
    filename: str,
    api_key: Optional[str] = None,
) -> dict:
    api_key = validate_deepseek_key(api_key)
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('backend/services/pdf_metadata_llm.py').read()); print('OK')"`
Expected: `OK`

---

### Task 4: 消除 `smart_literature_filter.py` 的 env 兜底

**Files:**
- Modify: `smart_literature_filter.py`

当前代码（行 52-56）：
```python
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found. Please provide an API key.")
```

- [ ] **Step 1: 添加导入并替换**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将行 52-56 替换为：
```python
        self.api_key = validate_deepseek_key(api_key)
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('smart_literature_filter.py').read()); print('OK')"`
Expected: `OK`

---

### Task 5: 消除 `smart_segment_router.py` 的 env 兜底

**Files:**
- Modify: `smart_segment_router.py`

当前代码（行 61-65）：
```python
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
```

- [ ] **Step 1: 添加导入并替换**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将行 61-65 替换为：
```python
    def __init__(self, api_key: str = None):
        self.api_key = validate_deepseek_key(api_key)
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('smart_segment_router.py').read()); print('OK')"`
Expected: `OK`

---

### Task 6: 加强 `new_architecture/config.py` 的 from_key 校验

**Files:**
- Modify: `new_architecture/config.py`

当前代码（行 31-34）：
```python
    @classmethod
    def from_key(cls, api_key: str) -> "Config":
        """直接传入API key（测试用）"""
        return cls(api_key=api_key)
```

- [ ] **Step 1: 添加导入并加强校验**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将 `from_key` 方法改为：
```python
    @classmethod
    def from_key(cls, api_key: str) -> "Config":
        """直接传入API key（前端用户 key，必须有校验）"""
        return cls(api_key=validate_deepseek_key(api_key))
```

- [ ] **Step 2: 同步更新 from_env 的错误提示**

将 `from_env` 的错误提示改为：
```python
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量读取配置（CLI/离线脚本用）"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY 未设置。请设置环境变量或通过前端传入 API Key。"
            )
        return cls(api_key=validate_deepseek_key(api_key, source="环境变量"))
```

- [ ] **Step 3: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('new_architecture/config.py').read()); print('OK')"`
Expected: `OK`

---

### Task 7: 为 `backend/routers/library.py` 的 match_online 添加 key 校验

**Files:**
- Modify: `backend/routers/library.py`

当前代码（行 399）：
```python
    api_key = request.get("api_key")
```
之后直接传给 `extract_metadata_with_llm`，没有校验。如果 key 为空，会走到 `pdf_metadata_llm.py` 的 `validate_deepseek_key` 抛错，但错误信息不够友好（不会提示"前端设置"）。

- [ ] **Step 1: 添加导入和校验**

在文件顶部添加导入：
```python
from backend.utils.api_key import validate_deepseek_key
```

将行 399 改为：
```python
    api_key = request.get("api_key")
    try:
        api_key = validate_deepseek_key(api_key)
    except ValueError:
        api_key = None
```

这样如果 key 无效就跳过 LLM 提取（library match 是增强功能，key 无效不应阻断主流程），只用已有元数据。

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('backend/routers/library.py').read()); print('OK')"`
Expected: `OK`

---

### Task 8: 确认所有后端路由的 key 校验一致性

**Files:**
- Read-only review: `backend/routers/reading.py`, `backend/routers/compare.py`, `backend/routers/filter.py`, `backend/routers/references.py`

这些路由已经正确实现了"只使用前端传入 key，不回退 env"的模式：

- `reading.py:656-657` — `if not api_key or not api_key.strip(): raise ValueError(...)` ✓
- `compare.py:67-70` — `get_api_key()` 直接 raise HTTPException ✓
- `filter.py:347-348` — `if not api_key or not api_key.strip(): raise ValueError(...)` ✓
- `references.py:724` — 通过 `extract_references_deepseek(file_path, api_key=api_key)` 传参 ✓

- [ ] **Step 1: 确认 reading.py 的三个 run 函数中 api_key 校验格式一致**

检查 `run_long_context_task` (行 656-657)、`run_quant_task` (行 852-853)、`run_qual_task` (行 983-984) 三个函数的 key 校验逻辑。

如果校验逻辑是手动 `if not api_key ... raise ValueError`，考虑统一替换为 `validate_deepseek_key(api_key)` 以获得更好的错误提示。

将以下模式：
```python
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
```

替换为：
```python
        api_key = validate_deepseek_key(api_key)
```

需要修改的函数：
- `run_long_context_task` (约行 656-659) — 删除手动校验，改用 `validate_deepseek_key`
- `run_quant_task` (约行 852-855) — 同上
- `run_qual_task` (约行 983-986) — 同上

每个函数修改后删除 `final_api_key = api_key.strip()` 行（因为 `validate_deepseek_key` 已返回清洗后的 key），后续引用 `final_api_key` 的地方改为直接使用 `api_key`。

- [ ] **Step 2: 确认 compare.py 的 get_api_key 函数**

`compare.py:67-70` 的 `get_api_key()` 可以保留（它已经正确地不回退 env），但考虑替换为 `validate_deepseek_key` 以获得更好的格式校验：

将：
```python
def get_api_key(provided_key: Optional[str] = None) -> str:
    if provided_key and provided_key.strip():
        return provided_key.strip()
    raise HTTPException(status_code=400, detail="缺少 API Key，请在前端设置中输入 DeepSeek API Key")
```

替换为：
```python
def get_api_key(provided_key: Optional[str] = None) -> str:
    try:
        return validate_deepseek_key(provided_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 3: 验证所有修改文件的语法**

Run:
```
python -c "import ast; ast.parse(open('backend/routers/reading.py').read()); print('reading OK')"
python -c "import ast; ast.parse(open('backend/routers/compare.py').read()); print('compare OK')"
python -c "import ast; ast.parse(open('backend/routers/filter.py').read()); print('filter OK')"
python -c "import ast; ast.parse(open('backend/routers/references.py').read()); print('references OK')"
```

Expected: 全部 OK

---

### Task 9: 统一 CLI/离线脚本的错误提示格式

**Files:**
- Modify: `deep_reading_steps/common.py:24-28`

CLI/离线脚本保持从 env 读取 key，但统一错误提示，引导用户配置 .env 或通过 Web 前端使用。

- [ ] **Step 1: 修改 `deep_reading_steps/common.py`**

在文件顶部添加导入（在现有 import 之后）：
```python
import sys
```

以及：
```python
from backend.utils.api_key import validate_deepseek_key
```

将 `get_deepseek_client()` 函数（行 24-28）替换为：
```python
def get_deepseek_client():
    try:
        key = validate_deepseek_key(DEEPSEEK_API_KEY, source="环境变量或 .env 文件")
    except ValueError as e:
        logger.error(str(e))
        return None
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "import ast; ast.parse(open('deep_reading_steps/common.py').read()); print('OK')"`
Expected: `OK`

---

### Task 10: 全局验证

- [ ] **Step 1: 在项目根目录运行语法检查**

Run:
```powershell
Get-ChildItem -Recurse -Include *.py -Path backend,smart_literature_filter.py,smart_segment_router.py,new_architecture,deep_reading_steps\common.py | ForEach-Object { python -c "import ast; ast.parse(open('$($_.FullName)').read())" 2>&1 | ForEach-Object { Write-Output "$($_.FullName): $_" } }
```

Expected: 无输出（所有文件语法正确）

- [ ] **Step 2: 确认没有残留的 env 回退模式**

Run: `python -c "from backend.utils.api_key import validate_deepseek_key; print('validate OK')"`

然后搜索确认以下模式已被消除：
- `backend/services/deepseek_refs.py` 中不再有 `os.getenv("DEEPSEEK_API_KEY")`
- `backend/services/pdf_metadata_llm.py` 中不再有 `os.getenv("DEEPSEEK_API_KEY")`
- `smart_literature_filter.py` 中不再有 `api_key or os.getenv`
- `smart_segment_router.py` 中不再有 `api_key or os.getenv`

- [ ] **Step 3: 提交**

```bash
git add backend/utils/ backend/services/ smart_literature_filter.py smart_segment_router.py new_architecture/config.py backend/routers/ deep_reading_steps/common.py
git commit -m "feat: 移除 env API Key 回退，强制使用前端用户 Key

- 创建 backend/utils/api_key.py 统一验证函数
- 消除 deepseek_refs.py 和 pdf_metadata_llm.py 的 os.getenv 回退
- 消除 smart_literature_filter.py 和 smart_segment_router.py 的 env 兜底
- 加强 new_architecture/config.py from_key 校验
- 统一 reading/compare/filter 路由的 key 校验
- CLI/离线脚本保持 env 读取但统一错误提示"
```
