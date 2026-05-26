# 精读维度并发方案

> 目标：将单篇精读内部的维度/步骤调用从串行改为并发，同时控制全局 DeepSeek API 并发数不超限。
> 约束：DeepSeek 并发上限 500；批量精读最多 10 篇同时跑。

---

## 1. 现状

### 1.1 文件级并发（已有）

`start_batch_reading`（`reading.py:1930`）为每个文件创建独立 `threading.Thread` 并立即 `thread.start()`。
10 篇文献 = 10 个线程同时跑。✅

### 1.2 维度级串行（待改）

每个线程内部的维度循环是串行的：

| 模式 | 入口函数 | 循环位置 | 维度数 | 单维耗时 |
|------|----------|----------|--------|----------|
| 长文本 | `run_long_context_task` | `reading.py:1149` | ≤12 | ~30-60s (reasoner) |
| 七步 | `run_quant_task` | `reading.py:1370` | 7 | ~30-60s (reasoner) |
| 四步 | `run_qual_task` | `reading.py:1542` | 4 | ~30-60s (reasoner) |

**当前耗时** = `维度数 × 单维耗时`（串行叠加）。

### 1.3 并发安全性

- `tasks` 字典：全局可变字典，所有线程共享读写
- `ConversationEngine`：每个线程独享一个实例（无共享状态）
- DeepSeek OpenAI client：每次 `create()` 是独立 HTTP 请求，client 本身线程安全
- SQLite：通过 `AsyncSessionLocal` 每次新建会话，写操作会排队（WAL 模式下可并发读）

---

## 2. 改动范围

### 2.1 新增：全局 DeepSeek 并发信号量

**文件**：`backend/services/queue_manager.py`（或新建 `backend/services/deepseek_limiter.py`）

```python
import threading

# DeepSeek 全局并发信号量
# 上限 500，保守取 100，确保 10 篇 × 12 维 = 120 也不会触及 500
DEEPSEEK_MAX_CONCURRENT = 100
deepseek_semaphore = threading.Semaphore(DEEPSEEK_MAX_CONCURRENT)
```

所有 DeepSeek API 调用（精读、综述、参考文献、翻译等）统一经过此信号量。
这保证了即使用户同时触发批量精读 + AI 综述 + 翻译，总并发也不超 100。

### 2.2 修改：`run_long_context_task`（长文本精读）

**文件**：`backend/routers/reading.py`
**位置**：`reading.py:1147-1191`（维度分析循环）

**改动**：将串行 for 循环改为 `ThreadPoolExecutor` 并发。

伪代码：
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _analyze_one_dim(dim_key, engine, custom_dim_map, custom_question):
    """单维度分析，带全局并发控制。"""
    with deepseek_semaphore:
        # ... 原有的 mapped_key / custom_dim_map 逻辑
        return dim_key, answer

results = {}
workers = min(len(analysis_dims), 10)  # 单篇最多 10 维同时调
with ThreadPoolExecutor(max_workers=workers) as pool:
    futures = {}
    for dim_key in analysis_dims:
        # 跳过增量模式已有结果的维度
        if conflict_resolution == "incremental" and item_key in prev_items:
            results[dim_key] = prev_items[item_key]
            continue
        f = pool.submit(_analyze_one_dim, dim_key, engine, custom_dim_map, custom_question)
        futures[f] = dim_key

    for future in as_completed(futures):
        if tasks[task_id]["status"] == "cancelled":
            pool.shutdown(wait=False, cancel_futures=True)
            return
        dim_key, answer = future.result()
        results[dim_key] = answer
        tasks[task_id]["logs"].append(f"✓ {dim_key} 完成")
```

**自定义问题**（`reading.py:1193-1202`）：在所有维度并发完成后串行执行（保持现状）。

**空维度重试**（`_check_and_retry_empty_dimensions`）：改为并发重试。

### 2.3 修改：`run_quant_task`（七步精读）

**文件**：`backend/routers/reading.py`
**位置**：`reading.py:1367-1389`（七步循环）

同理，7 步全部并发。`max_workers=7`。

### 2.4 修改：`run_qual_task`（四步精读）

**文件**：`backend/routers/reading.py`
**位置**：`reading.py:1539-1561`（四步循环）

同理，4 步全部并发。`max_workers=4`。

### 2.5 修改：AI 综述维度并发

**文件**：`backend/routers/compare.py`
**位置**：
- `synthesize_dimensions` → `compare.py:1495`（七步/四步综述）
- `synthesis_stream` → `compare.py:1652`（统一综述端点）

**改动**：将维度循环改为并发，收齐结果后按序 yield SSE 事件。

```python
# 并发调所有维度
dim_results = [None] * len(dimensions)
with ThreadPoolExecutor(max_workers=min(len(dimensions), 10)) as pool:
    futures = {}
    for idx, dim_info in enumerate(dimensions):
        f = pool.submit(_synthesize_one_dim, idx, dim_info, ...)
        futures[f] = idx
    for future in as_completed(futures):
        idx = futures[future]
        dim_results[idx] = future.result()  # (label, content)

# 按序 yield SSE 事件
for idx, result in enumerate(dim_results):
    yield f"event: dimension\ndata: ..."
```

### 2.6 修改：精读后处理并发

**文件**：`backend/routers/reading.py`

元数据提取和参考文献提取可并发：

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    meta_future = pool.submit(extract_metadata_with_llm, ...)
    ref_future = pool.submit(_try_extract_references, ...)
    metadata = meta_future.result()
    ref_artifacts = ref_future.result()
```

---

## 3. 不改动的部分

| 模块 | 原因 |
|------|------|
| 批量摘要翻译 `abstract_translator.py` | 已有 `ThreadPoolExecutor(max_workers=5)` |
| MD 分片翻译 `translation_pipeline.py` | 已有 `ThreadPoolExecutor` |
| PDF 全文翻译 | 两步有依赖关系，串行合理 |
| 参考文献 extract → trace | trace 依赖 extract 结果，串行合理 |
| 文献筛选 | 单次 LLM 调用 |
| 文献助手聊天 | 单次流式调用 |

---

## 4. 并发数计算

最坏情况：一个用户触发批量精读 + AI 综述 + 批量翻译。

| 操作 | 并发调用量 |
|------|-----------|
| 批量精读 10 篇 × 12 维 | 120 |
| AI 综述 10 维 | 10 |
| 批量翻译 5 workers | 5 |
| **合计** | **135** |

`deepseek_semaphore=100` 可以覆盖绝大多数场景。
极端情况下部分请求会排队等信号量，不会触发 500 限流。

---

## 5. 线程安全注意事项

### 5.1 `tasks` 字典

`tasks[task_id]["logs"].append(...)` 和 `tasks[task_id]["progress"] = ...` 需要保护。

方案：在 `tasks` 字典的每个 value 中加一个 `threading.Lock`：

```python
def init_task_payload(...):
    payload = {
        "status": "pending",
        "progress": 0,
        # ...
        "_lock": threading.Lock(),
    }
    return payload
```

或者更简单：`tasks[task_id]` 本身的赋值是原子的（Python GIL），`list.append` 也是原子的。
日志顺序可能乱，但功能不受影响。可以暂不加锁，后续如果有问题再补。

### 5.2 `ConversationEngine`

每个线程有独立的 `engine` 实例，无共享状态，安全。

### 5.3 `deepseek_semaphore`

`threading.Semaphore` 本身线程安全。

---

## 6. 提速预估

| 场景 | 当前耗时 | 改后耗时 | 提速比 |
|------|----------|----------|--------|
| 长文本 12 维 | ~8-12 min | ~1-2 min | 5-8× |
| 七步精读 | ~6-8 min | ~1-1.5 min | 5-7× |
| 四步精读 | ~4-6 min | ~1-1.5 min | 3-4× |
| AI 综述 5 维 | ~50-100s | ~15-25s | 3-5× |
| 批量 10 篇长文本 | ~80-120 min | ~10-20 min | 6-8× |

---

## 7. 实施步骤

1. **新增 `deepseek_limiter.py`**：全局信号量 + 辅助上下文管理器
2. **改 `run_long_context_task`**：维度并发 + 空维度并发重试
3. **改 `run_quant_task`**：七步并发
4. **改 `run_qual_task`**：四步并发
5. **改 `synthesize_dimensions` / `synthesis_stream`**：综述维度并发
6. **改精读后处理**：元数据提取与参考文献提取并发
7. **测试**：单篇精读 + 批量精读 + AI 综述 + 混合场景

---

## 8. 风险与回退

| 风险 | 应对 |
|------|------|
| DeepSeek 限流 | 信号量限制总并发；429 错误已有重试机制 |
| 维度结果质量下降 | `max_history_turns=0` 意味着每维独立，不影响质量 |
| 空维度重试乱序 | `as_completed` 收集后再统一处理 |
| 日志乱序 | 可接受；如需严格有序可加锁后按序输出 |
| prompt caching 命中率下降 | 并发请求共享相同前缀，DeepSeek 服务端应能缓存命中 |
| 批量精读内存激增 | 10 篇 × 并发维度，每维一份论文文本在 engine 中；可通过信号量控制 |

回退方案：将 `deepseek_semaphore` 值改为 1 即退化为串行行为。
