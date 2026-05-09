# 自定义维度数据导入导出修复

> **日期**: 2026-05-09  
> **关联**: [CUSTOM_DIMENSION_PHASE1_IMPL.md](./CUSTOM_DIMENSION_PHASE1_IMPL.md)  
> **状态**: 待实施

## 1. 问题

Phase 1 新增了 `dimension_sets` 和 `dimension_items` 两张表，但 `data_portability.py` 的导入导出未同步更新。具体症状：

| 缺陷 | 说明 |
|------|------|
| 导出遗漏 | `EXPORT_TABLE_ORDER` 不含两张维度表，`.dra` 包不含维度数据 |
| 导入遗漏 | `IMPORT_CLEAR_ORDER` 不含两张维度表，导入时不清除也不写入维度 |
| 版本号过时 | `CURRENT_SCHEMA_VERSION = "006"`，应为 `"007"` |

### 用户影响

| 场景 | 后果 |
|------|------|
| 用户导出再导入回自己 | 维度数据不受影响（未清未写），但导出文件不含维度 |
| 用户 A 导出给用户 B 导入 | B 的维度集不变，A 的自定义维度丢失，无报错 |
| 服务器迁移（全量导出+导入） | 所有自定义维度集丢失，只剩启动种子重建的默认集 |

## 2. 修复方案

### 2.1 改动范围

仅修改 1 个文件：`backend/services/data_portability.py`

### 2.2 改动 1：新增 import

在文件顶部 `from db.models import (...)` 中加入 `DimensionSet` 和 `DimensionItem`。

### 2.3 改动 2：EXPORT_TABLE_ORDER

在 `PromptTemplate` 之后插入 `DimensionSet` 和 `DimensionItem`。顺序必须先 Set 后 Item（FK 依赖）：

```python
EXPORT_TABLE_ORDER = [
    UploadBatch,
    File,
    PromptTemplate,
    DimensionSet,       # ← 新增（先集合）
    DimensionItem,      # ← 新增（后条目，依赖 set_id）
    BibEntry,
    Job,
    BibFilterLink,
    JobBibEntry,
    ReadingItem,
    Artifact,
    BibReference,
    BibReferenceCitation,
]
```

**为什么放在 BibEntry 之前**：`DimensionSet` 依赖 `owner_user_id` 指向 `users`（不在导出列表中），不依赖其他导出表。放在靠前位置使数据尽早写入，方便后续调试时查看导出 JSON。

### 2.4 改动 3：IMPORT_CLEAR_ORDER

在 `PromptTemplate` 之前（反向）插入。顺序必须先 Item 后 Set（FK 反向）：

```python
IMPORT_CLEAR_ORDER = [
    BibReferenceCitation,
    BibReference,
    ReadingItem,
    Artifact,
    JobBibEntry,
    BibFilterLink,
    Job,
    BibEntry,
    DimensionItem,      # ← 新增（先删条目）
    DimensionSet,       # ← 新增（后删集合）
    File,
    UploadBatch,
    PromptTemplate,
]
```

**为什么放在 BibEntry 和 File 之间**：反向删除时，先删叶子再删父。`DimensionItem` 依赖 `DimensionSet`，`DimensionSet` 不依赖其他被清除的表（只依赖 `users`），所以放在中间即可。

### 2.5 改动 4：CURRENT_SCHEMA_VERSION

```python
CURRENT_SCHEMA_VERSION = "007"
```

### 2.6 改动 5：_query_user_records 适配

当前 `_query_user_records` 的通用分支（else）直接用 `model.owner_user_id == user_id` 查询。`DimensionSet` 有 `owner_user_id`，走通用分支即可，**无需特殊处理**。

但 `DimensionItem` **没有** `owner_user_id`——它通过 `set_id` → `DimensionSet.owner_user_id` 间接关联。需要新增一个分支：

```python
elif model is DimensionItem:
    user_set_ids = select(DimensionSet.id).where(
        DimensionSet.owner_user_id == user_id
    )
    result = await db.execute(
        select(model).where(model.set_id.in_(user_set_ids))
    )
```

这与 `BibFilterLink` / `JobBibEntry` 的处理模式一致（通过子查询关联）。

### 2.7 _clear_user_data 适配

`_clear_user_data` 遍历 `IMPORT_CLEAR_ORDER`，对每个 model 执行删除。逻辑分支：

1. `hasattr(model, "owner_user_id")` → `DimensionSet` 走此分支，直接按 `owner_user_id` 删 ✅
2. `model is JobBibEntry` / `model is BibFilterLink` → 特殊子查询
3. else → `DimensionItem` 会走到此兜底分支，执行 `delete(model)` **删全表** ❌

需要为 `DimensionItem` 新增一个分支：

```python
elif model is DimensionItem:
    user_set_ids = select(DimensionSet.id).where(
        DimensionSet.owner_user_id == user_id
    )
    result = await db.execute(
        delete(model).where(model.set_id.in_(user_set_ids))
    )
```

### 2.8 _deserialize_table 适配

`_deserialize_table` 的现有逻辑已能处理：

- `DimensionSet` 有 `owner_user_id` → 自动替换为 `user_id` ✅
- `DimensionSet` 和 `DimensionItem` 都是 autoincrement PK → PK 会被跳过 ✅
- `DimensionItem.set_id` 的值来自导出时的旧 ID → 导入时 Set 已有新 ID

**问题**：`DimensionItem` 的 `set_id` 引用的是导出包中的旧 `DimensionSet.id`。由于 Set 是 auto-PK，导入时会被分配新 ID。Item 的 `set_id` 仍是旧值，会导致 FK 断裂。

**解决方案**：需要一个 ID 映射表，记录旧 ID → 新 ID 的对应关系。

现有 `_deserialize_table` 没有 ID 重映射机制。但查看代码逻辑：

1. `_pre_delete_conflicts` 会删除旧数据
2. `_deserialize_table` 中 auto-PK 的主键被跳过，让数据库自动分配新 ID
3. `DimensionSet` 被先导入（在 `EXPORT_TABLE_ORDER` 中靠前），获得新 ID
4. 随后导入 `DimensionItem` 时，其 `set_id` 仍是旧值

**需要在 `_deserialize_table` 或 `import_user_data` 中增加 ID 重映射**。

最简方案：在 `import_user_data` 中，导入 `DimensionSet` 后收集 `{旧ID: 新ID}` 映射，传给后续的 `DimensionItem` 导入。

### 2.9 ID 重映射方案

在 `import_user_data` 的导入循环中：

```python
# 现有代码
for model in EXPORT_TABLE_ORDER:
    ...
    count = await _deserialize_table(db, model, records, uid, urole)
    ...

# 改造为：在 DimensionSet 导入后收集映射
id_map: dict[tuple[str, int], int] = {}  # (table_name, old_pk) -> new_pk

for model in EXPORT_TABLE_ORDER:
    ...
    count, new_pks = await _deserialize_table(db, model, records, uid, urole, id_map)
    ...
```

`_deserialize_table` 修改：
- 接收 `id_map` 参数
- 插入后 `await db.flush()` 获取自动分配的 ID
- 将 `{旧ID: 新ID}` 写入 `id_map`
- 对于 `DimensionItem`，将 `set_id` 替换为 `id_map[("dimension_sets", old_set_id)]`

## 3. 测试计划

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 创建自定义维度集 + 维度 → 导出 → 检查 `.dra` | `dimension_sets.json` 和 `dimension_items.json` 存在且内容正确 |
| 2 | 导出 → 新用户导入 → 检查维度集 | 自定义维度集和维度条目完整恢复，`set_id` 指向正确的集合 |
| 3 | 导出 → 同用户导入 → 检查维度集 | 旧维度被清除，新维度写入，系统集保留 |
| 4 | 只含默认维度的用户导出导入 | 系统集 13 维度完整保留 |
| 5 | 导入旧版 `.dra`（无维度 JSON） | 不报错，维度数据不受影响（文件不存在则 skip） |

## 4. 文件变更清单

| 文件 | 变更 |
|------|------|
| `backend/services/data_portability.py` | +6 行 import，+2 表 EXPORT，+2 表 IMPORT，+版本号，+`_query_user_records` 分支，+`_clear_user_data` 分支，+ID 重映射 |
