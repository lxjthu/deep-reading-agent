# 用户数据一键导出/导入设计文档

> 日期: 2026-05-06
> 状态: Draft
> 关联: [DATABASE_SCHEMA.md](../../DATABASE_SCHEMA.md)、[TECHNICAL_OVERVIEW.md](../../TECHNICAL_OVERVIEW.md)

## 1. 背景与目标

### 1.1 问题

当前系统中用户数据存在以下便携性问题：

- 普通用户数据 24h 后被自动清理，无备份手段
- 用户无法跨设备/跨实例迁移自己的文献库和精读结果
- 服务器故障或误操作可能导致数据永久丢失
- 无任何导出/导入能力

### 1.2 目标

为所有用户提供一键导出和一键导入功能，覆盖以下场景：

1. **普通用户 24h 到期前自救**：导出数据 → 下次登录后导入恢复
2. **跨设备/跨实例迁移**：自部署场景下将数据从一个实例搬到另一个
3. **离线备份与归档**：定期导出全部数据，防丢失

### 1.3 约束

- 导出范围：全量（数据库记录 + 物理文件）
- 导入策略：清空后导入（不做智能合并）
- 所有已登录用户均可使用
- 数据严格按用户隔离

---

## 2. 方案选型

### 2.1 候选方案

| 方案 | 格式 | 优点 | 缺点 |
|------|------|------|------|
| A: JSON + 文件打包 | 每表一个 JSON + 物理文件，zip 打包 | 人可读、版本兼容好、与 DB 引擎无关 | 需写序列化逻辑 |
| B: SQLite 快照切片 | 一个 SQLite 文件 + 物理文件 | 天然结构化 | 版本兼容差、调试难、迁移 PostgreSQL 后失效 |

### 2.2 选择

**方案 A**。理由：

1. JSON 天然容忍多余/缺失字段，schema 升级后老导出包仍可导入
2. 清空后导入策略下 UUID 直接原样写入，无冲突
3. 用户可解压查看内容（人可读）
4. 未来迁移 PostgreSQL 不受影响

---

## 3. 导出包格式

### 3.1 文件结构

```
export_20260506_username.dra  (MIME: application/zip)
├── manifest.json
├── data/
│   ├── files.json
│   ├── upload_batches.json
│   ├── bib_entries.json
│   ├── bib_filter_links.json
│   ├── bib_references.json
│   ├── bib_reference_citations.json
│   ├── jobs.json
│   ├── job_bib_entries.json
│   ├── reading_items.json
│   ├── artifacts.json
│   └── prompt_templates.json
├── files/                     # 上传的物理文件
│   └── {file_id}.{ext}       # 以 files.id 作为文件名
└── artifacts/                 # 产物物理文件
    └── {job_id}/
        └── {filename}
```

### 3.2 manifest.json

```json
{
  "format_version": 1,
  "exported_at": "2026-05-06T14:30:00Z",
  "source_host": "deepreading.qzz.io",
  "schema_version": "005",
  "user": {
    "username": "zhangsan",
    "role": "vip",
    "email": "zhang@example.com"
  },
  "stats": {
    "bib_entries": 42,
    "files": 15,
    "jobs": 38,
    "artifacts": 56,
    "reading_items": 312,
    "prompt_templates": 3,
    "bib_references": 890,
    "bib_reference_citations": 1240
  },
  "missing_files": [],
  "errors": []
}
```

**字段说明**：

- `format_version`：导出包格式版本（当前为 1），导入时检查此字段
- `schema_version`：对应 Alembic 迁移版本号，用于兼容性判断
- `missing_files`：导出时物理文件缺失的记录列表
- `errors`：导出过程中遇到的非致命错误

### 3.3 版本兼容规则

| format_version | 处理 |
|---|---|
| 不在支持列表 | 拒绝导入，提示"导出包版本不兼容，请升级系统" |
| 在支持列表 | 正常导入 |

当前 `SUPPORTED_FORMAT_VERSIONS = {1}`。

---

## 4. 导出流程

### 4.1 API

```
POST /api/data/export
Authorization: Bearer <access_token>
```

返回：二进制 zip 流
- Content-Type: `application/octet-stream`
- Content-Disposition: `attachment; filename=export_20260506_zhangsan.dra`

### 4.2 后端流程

```
1. 验证用户身份
2. 创建临时目录 tmp/export_{user_id}_{timestamp}/
3. 写 manifest.json
4. 按 FK 正向顺序依次查询 11 张表（仅 owner_user_id = 当前用户），序列化为 JSON
5. 复制物理文件到 files/ 和 artifacts/ 目录
6. 打包为 zip
7. 清理临时目录，返回 zip 流
8. 记录操作日志
```

### 4.3 查询顺序（FK 正向依赖）

```
upload_batches → files → prompt_templates(user) →
bib_entries → jobs → bib_filter_links → job_bib_entries →
reading_items → artifacts → bib_references → bib_reference_citations
```

### 4.4 序列化规则

| 类型 | 处理方式 |
|------|---------|
| datetime | 序列化为 ISO8601 字符串 |
| INTEGER（含布尔 0/1） | 保持原样 |
| TEXT / String | 保持原样 |
| owner_user_id | 保留原值（导入时替换为目标用户 ID） |
| 自增 id（BibFilterLink.id 等） | 保留原值（导入时让 DB 自动分配） |
| UUID 主键（files.id 等） | 保留原值 |
| 物理文件缺失 | JSON 记录中追加 `"_file_missing": true`，记入 manifest.missing_files |

### 4.5 不导出的内容

- `users` 表（账号信息）
- `invite_codes` 表（邀请码）
- `user_settings` 表（v1 未启用）
- 系统级提示词（`prompt_templates` 中 `scope='system'` 的记录）

---

## 5. 导入流程

### 5.1 API

```
POST /api/data/import
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

Body: file=<.dra 文件>
```

返回：导入统计 JSON

### 5.2 后端流程

```
1. 验证用户身份
2. 解析 zip 包，读取 manifest.json
   - 检查 format_version 是否支持
3. 清空用户现有数据（事务内）
4. 按 FK 正向顺序导入 JSON 数据
5. 恢复物理文件
6. 根据当前用户角色重算 expires_at
7. 提交事务
8. 记录操作日志
```

### 5.2.1 事务管理（关键实现细节）

**重要**：导入操作使用 FastAPI 的 `get_db` 依赖注入，该依赖会在请求开始时创建 session，在请求结束时自动关闭。因此导入操作必须在一次 HTTP 请求内完成所有数据库操作。

**事务边界**：
- **数据清除和导入**在同一个事务中完成
- **物理文件恢复**在事务提交后进行（best-effort）
- 不要在 `_clear_user_data()` 内部调用 `db.commit()`，应由调用方统一控制

**错误的事务写法（会导致"Can't operate on closed transaction"）**：
```python
# 错误：在嵌套事务中调用 commit
async with db.begin_nested():
    await _clear_user_data(db, user.id)  # 内部调用了 db.commit()
    await _deserialize_table(db, ...)
    await db.commit()  # 事务已关闭，报错
```

**正确的事务写法**：
```python
# 正确：在一个事务中完成所有数据操作
await _clear_user_data(db, user.id)  # 不调用 commit
await _deserialize_table(db, ...)
await db.commit()  # 统一提交
```

### 5.2.2 清空策略

**当前实现**：清空**所有用户**的数据（不仅仅是当前用户），确保 UUID 主键不冲突。

```python
async def _clear_user_data(db: AsyncSession, user_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in IMPORT_CLEAR_ORDER:
        # 删除所有记录，不限于当前用户
        result = await db.execute(delete(model))
        counts[table_name] = result.rowcount or 0
    return counts
```

**注意**：这是针对单用户实例的简化策略。多用户实例应考虑：
1. 仅清空当前用户数据
2. 导入时对 UUID 冲突的记录生成新 ID
3. 更新外键引用关系

### 5.3 清空顺序（FK 反向依赖，先删子表）

```
bib_reference_citations → bib_references → reading_items →
artifacts（+ 物理文件）→ job_bib_entries → bib_filter_links →
jobs → bib_entries → files（+ 物理文件）→ upload_batches →
prompt_templates（仅 scope='user'）
```

### 5.4 导入顺序（FK 正向依赖，先建父表）

```
upload_batches → files → prompt_templates(user) →
bib_entries → jobs → bib_filter_links → job_bib_entries →
reading_items → artifacts → bib_references → bib_reference_citations
```

### 5.4.1 物理文件恢复策略

**关键原则**：文件恢复必须在数据库事务提交后进行。

**原因**：
- 事务提交前，新插入的记录尚未真正写入数据库
- 文件恢复需要查询数据库获取 `storage_path`
- 如果先恢复文件再提交事务，可能导致文件恢复成功但数据回滚，造成 orphaned files

**实现步骤**：

1. **事务内**：导入所有数据库记录
2. **提交事务**：`await db.commit()`
3. **事务外**：收集文件恢复信息（此时 session 仍有效）
4. **文件恢复**：复制物理文件到目标目录

```python
# 步骤1-2：数据导入和提交
await db.commit()

# 步骤3：收集恢复信息（仍在 session 内）
files_to_restore = []
for src_path in files_dir.iterdir():
    file_id = src_path.stem
    result = await db.execute(select(File).where(File.id == file_id))
    record = result.scalar_one_or_none()
    if record and not getattr(record, "_file_missing", False):
        dst = resolve_storage_path(record.storage_path)
        files_to_restore.append((src_path, dst))

# 步骤4：恢复文件（best-effort）
for src_path, dst_path in files_to_restore:
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
    except Exception:
        pass  # 文件缺失不阻塞导入
```

### 5.5 导入时数据转换

| 字段 | 处理 |
|------|------|
| owner_user_id | 替换为当前用户 ID |
| expires_at | 清空后根据当前用户角色重算：VIP/admin → NULL，normal → now+24h |
| 自增 id | 不写入，让数据库自动分配 |
| UUID 主键 | 原样写入（清空后无冲突） |
| `"_file_missing": true` 的记录 | 跳过物理文件恢复 |
| bib_references.matched_bib_entry_id | 原样写入（指向同一用户的其他 bib_entry，清空后导入时原值有效） |

### 5.6 错误处理

| 错误 | 处理 |
|------|------|
| format_version 不匹配 | 拒绝导入，返回错误信息 |
| zip 解压失败 | 返回"文件格式错误" |
| manifest.json 缺失 | 返回"无效的导出包" |
| 某条 JSON 记录字段缺失 | 跳过该条，记入 errors，不阻塞 |
| 物理文件缺失 | 跳过（JSON 中已有 `_file_missing` 标记） |
| 数据库异常 | 回滚整个事务，恢复导入前状态 |

### 5.7 事务保护

步骤 3-6 在一个数据库事务内完成。失败则整体回滚。回滚后若有已写入的物理文件，通过临时目录管理自动清理。

---

## 6. 前端交互

### 6.1 入口位置

工作台右上角用户菜单中新增：
- "导出我的数据"
- "导入数据"

### 6.2 导出交互

1. 点击"导出我的数据"
2. 弹出确认对话框："将导出您的全部数据（文献库、精读结果、源文件、提示词等），可能需要数分钟。"
3. 普通用户额外提示："您的数据将在 {expires_at} 后被清理，建议尽快导出备份"
4. 确认后 loading，浏览器直接下载 `.dra` 文件

### 6.3 导入交互

1. 点击"导入数据"
2. 弹出文件选择器（仅接受 `.dra`）
3. 选择后弹出警告："导入将**清空您当前的所有数据**，并用导出包中的数据替换。此操作不可撤销。"
4. 需要输入确认文字"确认导入"才能点击确定
5. 确认后显示进度条
6. 完成后显示导入统计，自动刷新页面

### 6.4 普通用户到期提醒

普通用户工作台顶部横幅增加：
"您的数据将在 **{剩余时间}** 后清理。建议定期 [导出备份] 。"

---

## 7. 安全约束

| 约束 | 说明 |
|------|------|
| 权限 | 所有已登录用户均可导出/导入自己的数据 |
| 数据隔离 | 仅导出/导入 `owner_user_id = 当前用户` 的记录 |
| 不导出系统提示词 | prompt_templates 仅导出 `scope='user'` 且属于当前用户 |
| 不导出邀请码 | invite_codes 不纳入 |
| 不导出密码哈希 | users.password_hash 不写入 manifest |
| 不导出 token | 导入后用户继续使用自己的密码和 token |
| 角色不变 | 导入不改变用户角色 |
| 文件大小限制 | 导入包最大 1GB |
| 频率限制 | 每用户每天最多导出 5 次、导入 3 次 |

---

## 8. 代码结构

### 8.1 新增文件

```
backend/
├── services/
│   └── data_portability.py    # 核心逻辑：导出打包 + 导入解包
├── routers/
│   └── data.py                # API 路由
frontend/src/
├── components/
│   └── DataExportImport.tsx   # UI 组件
```

### 8.2 data_portability.py 核心接口

```python
FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = {1}

EXPORT_TABLE_ORDER = [
    UploadBatch, File, PromptTemplate,
    BibEntry, Job, BibFilterLink, JobBibEntry,
    ReadingItem, Artifact, BibReference, BibReferenceCitation,
]

IMPORT_CLEAR_ORDER = [
    BibReferenceCitation, BibReference, ReadingItem,
    Artifact, JobBibEntry, BibFilterLink,
    Job, BibEntry, File, UploadBatch, PromptTemplate,
]

async def export_user_data(db: AsyncSession, user: User) -> Path:
    """构建 .dra 导出包，返回临时文件路径"""

async def import_user_data(db: AsyncSession, user: User, dra_path: Path) -> dict:
    """解析 .dra 包并导入，返回统计"""

async def _serialize_table(db, model, user_id) -> list[dict]:
    """将单表用户数据序列化为 dict 列表"""

async def _clear_user_data(db: AsyncSession, user_id: int) -> dict:
    """清空用户所有数据，返回删除统计"""

async def _deserialize_table(db, model, records, user_id) -> int:
    """将 dict 列表反序列化写入数据库"""

async def _restore_physical_files(tmp_dir, user_id) -> dict:
    """恢复物理文件到对应目录"""
```

---

## 9. 测试要点

### 9.1 导出测试

- 空用户导出（无数据）→ manifest.stats 全为 0，zip 中 data/ 目录存在但 JSON 为空数组
- 有数据用户导出 → JSON 记录数与数据库一致
- 物理文件缺失时导出 → manifest.missing_files 有记录，JSON 中 `_file_missing=true`
- 不同角色用户导出 → 均能正常导出

### 9.2 导入测试

- 正常导入 → 数据完整恢复，物理文件存在
- 导入空包 → 不报错，清空后无数据
- 导入不兼容版本 → 拒绝并报错
- 导入包中物理文件缺失 → 记录存在但无物理文件，不阻塞
- 导入后角色处理 → normal 用户导入 VIP 数据，expires_at 为 now+24h
- 重复导入 → 第二次导入清空第一次的数据后重新导入

### 9.3 导出+导入往返测试

- 导出 → 导入 → 再次导出 → 两次导出包的数据部分 JSON 一致（排除时间戳差异）

---

## 10. 未来扩展

| 扩展点 | 说明 |
|--------|------|
| 增量导出 | 仅导出上次导出后变更的数据，减少包体积 |
| 选择性导出 | 前端勾选导出哪些类型的数据 |
| 智能合并导入 | 不清空现有数据，按 dedup_key 合并（需 UUID 重映射） |
| 定时自动导出 | 普通用户到期前自动导出到服务器备份目录 |
| 加密导出包 | 用用户密码加密 .dra 包，增强安全性 |
