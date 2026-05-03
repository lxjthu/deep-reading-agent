# API Key 传递链路修复记录

> 适用项目：`deep-reading-agent`  
> 记录日期：2026-05-03  
> 问题类型：参考文献梳理功能使用了环境变量 API Key，而非用户提供的 Key

---

## 问题现象

服务器上报错：

```
❌ Error code: 401 - {'error': {'message': 'Authentication Fails, Your api key: ****5b25 is invalid', ...}}
```

用户已在前端配置了自己的 DeepSeek API Key，但参考文献梳理功能仍使用服务器环境变量中的 Key。

---

## 设计原则

根据 `REFERENCE_CITATION_TAB_PLAN.md` 的规划：

- 用户自己把 API Key 存在前端
- 所有处理调用的应该是用户自己存在前端的 Key
- 而不是服务器环境变量中的 Key

---

## 问题根因

API Key 传递链路在 `_try_extract_references` 处断裂：

```
前端用户 Key
    ↓
run_quant_task(api_key) / run_qual_task(api_key)
    ↓
_try_extract_references() ← 没有接收 api_key 参数 ❌
    ↓
extract_references_deepseek()
    ↓
call_deepseek_json() → os.getenv("DEEPSEEK_API_KEY") ← 使用环境变量 ❌
```

---

## 修复方案

### 1. 修改 `backend/services/deepseek_refs.py`

#### `call_deepseek_json` 函数

```python
# 修改前
def call_deepseek_json(messages, *, max_tokens, temperature):
    api_key = os.getenv("DEEPSEEK_API_KEY")

# 修改后
def call_deepseek_json(messages, *, max_tokens, temperature, api_key=None):
    if not api_key or not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY")  # 回退到环境变量
```

#### `extract_references_deepseek` 函数

```python
# 修改前
def extract_references_deepseek(pdf_path: str) -> list[dict]:

# 修改后
def extract_references_deepseek(pdf_path: str, api_key: Optional[str] = None) -> list[dict]:
```

#### `trace_citations_deepseek` 函数

```python
# 修改前
def trace_citations_deepseek(pdf_path: str, references: list[dict]) -> list[dict]:

# 修改后
def trace_citations_deepseek(pdf_path: str, references: list[dict], api_key: Optional[str] = None) -> list[dict]:
```

### 2. 修改 `backend/routers/reading.py`

#### `_try_extract_references` 函数

```python
# 修改前
def _try_extract_references(file_path, user_id, task_id, source_title, bib_entry_id):

# 修改后
def _try_extract_references(file_path, user_id, task_id, source_title, bib_entry_id, api_key=None):
```

#### 调用处修改（3 处）

```python
# 修改前
ref_artifacts = _try_extract_references(
    file_path, user_id, task_id, original_name, bib_entry_id,
)

# 修改后
ref_artifacts = _try_extract_references(
    file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
)
```

### 3. 修改 `backend/routers/references.py`

#### `run_reference_trace_task` 函数

```python
# 修改前
def run_reference_trace_task(task_id, user_id, source_bib_entry_id, file_path, source_title):

# 修改后
def run_reference_trace_task(task_id, user_id, source_bib_entry_id, file_path, source_title, api_key=None):
```

#### 调用处修改

```python
# 修改前
args=(task_id, user.id, entry.id, str(source_path), entry.title),

# 修改后
args=(task_id, user.id, entry.id, str(source_path), entry.title, _request.api_key),
```

---

## 修复后的链路

```
前端用户 Key
    ↓
run_quant_task(api_key) / run_qual_task(api_key)
    ↓
_try_extract_references(api_key=api_key) ✅
    ↓
extract_references_deepseek(api_key=api_key) ✅
    ↓
call_deepseek_json(api_key=api_key) ✅
    ↓
OpenAI(api_key=api_key) ← 使用用户 Key ✅
```

---

## 涉及文件

| 文件 | 修改内容 |
|------|----------|
| `backend/services/deepseek_refs.py` | 3 个函数增加 `api_key` 参数 |
| `backend/routers/reading.py` | `_try_extract_references` 增加 `api_key` 参数，3 处调用传递参数 |
| `backend/routers/references.py` | `run_reference_trace_task` 增加 `api_key` 参数，1 处调用传递参数 |

---

## 测试验证

修复后，参考文献梳理功能应使用用户在前端配置的 API Key，而非服务器环境变量。如果用户未提供 Key，才会回退到环境变量。
