# PostgreSQL 导向的 `.dra` 导入导出重构方案

> 类型：方案  
> 状态：待实施  
> 日期：2026-05-29  
> 关联：`backend/services/data_portability.py`、`backend/routers/data.py`、`backend/db/models.py`、`docs/DATABASE_SCHEMA.md`、`docs/TECHNICAL_OVERVIEW.md`

---

## 1. 背景

当前 `.dra` 导入导出方案最初围绕单机 SQLite 场景设计，核心假设是“导入前先清空当前用户数据，再按固定顺序完整重建”。这套方案在 PostgreSQL 线上环境中已经暴露出几个结构性问题：

1. **导入策略过于粗暴**
   - 当前导入会先执行 `_clear_user_data()`，本质是“覆盖整个当前用户工作区”。
   - 这与线上多轮使用、多批次积累、Research Agent 持久会话的实际需求不匹配。

2. **覆盖逻辑与 PostgreSQL 外键约束冲突更明显**
   - SQLite 历史上依赖“先删子表再删父表”的代码顺序兜底。
   - PostgreSQL 会严格执行 FK，一旦清理顺序或清理范围不精确，就会直接报错。

3. **缺少可控的导入模式**
   - 用户只能“全清空后导入”，不能“追加到现有库”。
   - 无法把多个 `.dra` 包逐步汇总到同一账号。

4. **版本兼容只做了最低限度**
   - 现有逻辑只校验 `format_version`，几乎不利用 `schema_version`。
   - 旧 SQLite 时代导出的 `.dra` 包虽然很多时候“碰巧能导”，但缺少明确兼容层。

5. **导入冲突处理散落在硬编码里**
   - 当前 `_pre_delete_conflicts()`、`_deserialize_table()` 以“全量替换”为主。
   - 缺少围绕 PostgreSQL 多约束环境的声明式冲突策略。

本次重构目标不是在旧实现上继续打补丁，而是将 `.dra` 导入导出提升为**面向 PostgreSQL 的、可扩展的用户工作区迁移机制**，同时保留对旧 SQLite 导出包的兼容。

---

## 2. 本次重构目标

### 2.1 业务目标

1. 支持两种导入模式：
   - **覆盖导入**：用导入包内容覆盖当前用户工作区中的同类数据，但**不先全清空数据库**。
   - **追加导入**：保留现有数据，只导入新数据；冲突记录按规则跳过或合并。

2. 保持导出格式继续为 `.dra`（zip + JSON + 物理文件）。

3. 明确支持旧版 SQLite 导出的 `.dra` 包。

4. 导入过程必须只影响当前用户数据，不误删其他用户或系统级数据。

5. 导入结果应可解释：
   - 哪些记录新建
   - 哪些记录覆盖
   - 哪些记录跳过
   - 哪些记录因兼容问题失败

### 2.2 技术目标

1. 将“清空后重建”改为“**声明式冲突检测 + 分表导入策略**”。
2. 将“是否导入某条记录”的决策，从硬编码 if/else，升级为表级策略配置。
3. 显式支持 PostgreSQL 约束环境：
   - FK
   - UNIQUE
   - CHECK
   - 非空字段
4. 保持现有 `.dra` 导出结构尽量稳定，避免重新定义包格式导致旧包失效。
5. 为未来 Research Agent 新表预留 portability 扩展入口。

---

## 3. 范围与非范围

### 3.1 本次范围

- 重构 `backend/services/data_portability.py`
- 调整 `backend/routers/data.py` 的导入接口与返回结果
- 前端导入交互增加“覆盖 / 追加”选项
- 增加旧 SQLite 导出包兼容层
- 增加针对 PostgreSQL 的导入测试
- 使用 `C:\Users\langx\Desktop\testdra` 中样本包做兼容验证

### 3.2 非范围

- 不改变 `.dra` 的文件扩展名
- 不把 `.dra` 改成数据库快照格式
- 不导出 `users`、`invite_codes`、`user_feedback`、`feedback_events`、`admin_audit_logs`
- 不在本次引入跨用户共享或管理员代导入能力
- 不在本次引入云端自动备份

---

## 4. 现状问题拆解

### 4.1 当前导入主流程

当前导入链路大致为：

1. 解压 `.dra`
2. 读取 `manifest.json`
3. 调用 `_clear_user_data()` 删除当前用户旧数据
4. 按 `EXPORT_TABLE_ORDER` 逐表导入
5. `owner_user_id` 替换为当前用户
6. auto PK 通过 `id_map` 重映射
7. 提交事务
8. 恢复物理文件

### 4.2 当前方案的根本问题

#### A. “覆盖”被等同于“整库清空”

这导致：

- 导入失败时用户风险大
- 无法做增量汇总
- 与线上长期积累工作区冲突

#### B. `_clear_user_data()` 对新表不安全

当前实现存在“忘了加 owner 过滤或特判，就可能误删全表”的设计风险。对 PostgreSQL 线上库，这是不可接受的。

#### C. 冲突处理不是业务语义驱动

现在处理冲突时，更多是在“如何让插入成功”，而不是“这一类业务对象遇到同名/同 UUID/同 MD5 时应该怎样处理”。

#### D. 旧包兼容没有显式分层

旧 SQLite 导出包与当前 PostgreSQL 线上 schema 之间，需要有一个“标准化/升级”步骤，而不是直接把旧 JSON 记录喂给 ORM。

---

## 5. 新设计总览

### 5.1 总体原则

1. **不再先清空整个当前用户工作区**
2. **按表定义导入策略**
3. **先标准化旧包，再执行导入**
4. **覆盖与追加共用同一套导入管线，只是冲突决策不同**
5. **所有删除都必须是“定向删除”，且必须有 owner 约束或明确的 parent-scope 约束**

### 5.2 新导入阶段

新的 `import_user_data()` 分为 6 个阶段：

1. **解包与基础校验**
   - 校验 zip
   - 校验 `manifest.json`
   - 校验 `format_version`

2. **包标准化**
   - 识别旧 SQLite 导出包
   - 将缺失字段补默认值
   - 将旧字段名/旧枚举值映射到当前 schema
   - 形成统一的内存表示 `normalized_bundle`

3. **导入预检**
   - 统计各表记录数
   - 识别冲突类型
   - 对覆盖/追加模式生成预期动作摘要

4. **事务内数据库导入**
   - 不做全量清空
   - 按表策略执行 `insert / update / skip / remap / selective delete`

5. **事务后物理文件恢复**
   - 恢复 `files/`
   - 恢复 `artifacts/`
   - 恢复 `card_notes/`

6. **结果汇总**
   - 返回 per-table 统计
   - 返回冲突、跳过、兼容修正摘要

---

## 6. 导入模式设计

### 6.1 模式定义

新增导入参数：

```json
{
  "mode": "merge_append" | "merge_replace"
}
```

含义如下：

| 模式 | 中文 | 语义 |
|------|------|------|
| `merge_append` | 追加导入 | 保留现有数据；冲突记录按规则跳过、复用或局部合并 |
| `merge_replace` | 覆盖导入 | 不清空整个工作区；仅对“与导入记录冲突的现有记录”执行定向替换 |

### 6.2 为什么不用“全清空覆盖”

因为用户说的“覆盖”更接近：

- 这批导入进来的对象，如果和我现有对象冲突，就让导入包版本生效
- 但没有冲突的现有数据，不应该被顺手删掉

因此这里将“覆盖”定义为**冲突替换**，不是“全量替换整个用户空间”。

### 6.3 前端文案

- `追加导入`：保留现有数据，只导入新内容；冲突数据会按规则跳过或复用。
- `覆盖导入`：仅替换与导入包冲突的现有数据，不会先清空全部工作区。

---

## 7. 表级冲突策略

### 7.1 设计思想

不同表的“冲突键”与“覆盖语义”完全不同，必须拆开设计。  
本次将引入一个声明式注册表，例如：

```python
TABLE_PORTABILITY_RULES = {
    "files": {...},
    "bib_entries": {...},
    "jobs": {...},
    ...
}
```

每张表至少定义：

- `import_order`
- `scope_query`
- `match_keys`
- `append_action`
- `replace_action`
- `id_remap_rules`
- `file_restore_rule`

### 7.2 推荐冲突键与策略

#### 1. `upload_batches`

- 冲突键：`id`
- 追加模式：若目标 batch id 已存在，则生成新 batch id，并重映射 `files.batch_id`
- 覆盖模式：若目标 batch id 已存在，则先定向处理该 batch 关联的当前用户文件，再替换 batch 记录

说明：`upload_batches` 更像一次上传会话容器，导入时允许 remap，不能强依赖旧 id 原样落库。

#### 2. `files`

- 冲突键优先级：
  1. `(owner_user_id, md5)`
  2. `id`
- 追加模式：
  - 若同一用户已有相同 `md5` 文件，则复用现有 `File.id`，不重复建记录
  - 导入包中引用该文件的下游对象统一 remap 到现有文件
- 覆盖模式：
  - 若按 `md5` 命中，则复用现有文件记录
  - 若按 `id` 命中但内容不同，则为导入文件生成新 `id`，避免硬删现有文件导致级联风险

说明：`files` 的真实业务主键更接近“用户内文件内容”，不是导出时的 UUID。

#### 3. `prompt_templates`

- 冲突键：`(owner_user_id, slot_key, name)` 或等价业务键
- 追加模式：跳过同业务键的记录
- 覆盖模式：更新已有模板内容、描述、提示词正文

说明：提示词模板天然适合按业务键 upsert。

#### 4. `dimension_sets`

- 冲突键：`(owner_user_id, name)`
- 追加模式：若同名集合存在，则复用集合；集合内条目按名称补齐缺失项
- 覆盖模式：若同名集合存在，则替换该集合下的用户自定义 `dimension_items`

#### 5. `dimension_items`

- 依赖父表 remap
- 冲突键：`(set_id, label)` 或 `(set_id, position)`
- 追加模式：跳过重复项，补入缺失项
- 覆盖模式：在目标集合范围内定向删旧条目，再导入新条目

#### 6. `bib_entries`

- 冲突键候选优先级：
  1. `(owner_user_id, doi)` 当 DOI 非空
  2. `(owner_user_id, normalized_title, year)`
  3. `id`
- 追加模式：优先复用已有文献，必要时只补缺失字段
- 覆盖模式：以现有文献为目标更新元数据，但不直接删除整篇文献的所有下游对象

说明：文献条目是业务枢纽，不能继续把“同一篇文献但 UUID 不同”视作完全不同对象。

#### 7. `jobs`

- 冲突键：`id`
- 追加模式：默认生成新 `job.id` 导入，并 remap 下游
- 覆盖模式：若 `id` 冲突，则在当前用户范围内删除该 job 及其纯从属子表，再导入

说明：`jobs` 更像历史执行记录，不适合用业务键合并。

#### 8. `job_bib_entries` / `bib_filter_links`

- 完全依赖父表 remap
- 追加模式：若相同关联已存在则跳过
- 覆盖模式：按目标 job / bib 定向替换

#### 9. `reading_items`

- 冲突键：`id`
- 追加模式：生成新 `id` 导入；若存在同 `bib_entry_id + mode + section_key` 的业务重复，可按策略跳过
- 覆盖模式：若命中同业务键，替换该阅读结果及其 edits

#### 10. `reading_item_edits`

- 完全依赖 `reading_item_id` remap
- 追加模式：附加导入
- 覆盖模式：在目标 `reading_item_id` 范围内定向删除后重建

#### 11. `annotations`

- 冲突键：`id`
- 追加模式：新建或 remap
- 覆盖模式：按业务来源定向替换

#### 12. `agent_sessions` / `agent_messages` / `agent_action_proposals`

- `agent_sessions`
  - 冲突键：`id`
  - 追加模式：生成新会话 id 导入
  - 覆盖模式：若 session id 冲突，则替换该 session 及从属 message/proposal

- `agent_messages`
  - 依赖 `session_id` remap
  - 追加模式：消息级 append
  - 覆盖模式：在 session 范围内定向替换

说明：Research Agent 会话属于用户工作记忆，不应因覆盖导入而误删其他不相关 session。

#### 13. `artifacts`

- 冲突键：`id`
- 追加模式：生成新 artifact id 导入，并 remap 依赖它的对象
- 覆盖模式：若同 `id` 冲突，则定向删除目标 artifact 及其纯从属对象后再导入

#### 14. `card_notes`

- 冲突键：`id`
- 追加模式：生成新 id 或按 `(owner_user_id, bib_entry_id, title)` 做弱去重
- 覆盖模式：命中同 id 或同业务键时替换

#### 15. `bib_references` / `bib_reference_citations`

- 依赖 `bib_entry_id`、`artifact_id`、`matched_bib_entry_id` remap
- 追加模式：按引用文本或 source hash 去重
- 覆盖模式：在目标 bib_entry 或 artifact 范围内替换

---

## 8. 旧 SQLite 导出包兼容方案

### 8.1 兼容目标

必须支持以下旧包特征：

1. `schema_version` 落后
2. 缺少新表 JSON
3. 某些表记录缺少当前新字段
4. 部分旧数据枚举值仍来自 SQLite 时代
5. 自增主键链路需要 remap

### 8.2 兼容方式

导入时增加 `normalize_bundle()` 阶段：

1. 读取 `manifest.schema_version`
2. 判断是否属于旧兼容区间
3. 对每张表执行标准化：
   - 缺文件：视为空数组
   - 缺字段：补默认值
   - 枚举值：映射到当前允许值
   - 旧字段：重命名或丢弃
   - 时间字段：统一转 ISO / naive UTC

### 8.3 兼容规则

| 场景 | 处理 |
|------|------|
| `format_version` 不支持 | 拒绝导入 |
| `schema_version` 较旧但可映射 | 正常导入，并记录兼容修正 |
| 某张新表在旧包中缺失 | 按空表处理 |
| 某字段缺失但可补默认值 | 自动补齐 |
| 某字段值违反当前 CHECK 且无法映射 | 该记录跳过并计入错误 |

### 8.4 兼容优先级

本次至少保证：

- 当前 `testdra` 中两个历史样本可导入
- 旧 SQLite 导出包缺失的新表不导致整体失败
- 旧包中的 `dimension_*`、`agent_*`、`card_notes` 等链路能正确降级或导入

---

## 9. 新的导出策略

### 9.1 导出总体方向

导出仍保持“DB 引擎无关”的 JSON + 物理文件结构，但新增以下改进：

1. `manifest.json` 中加入：
   - `export_strategy_version`
   - `schema_version`
   - `table_stats`
   - `compat_flags`

2. 导出时显式写出：
   - 当前导出是否包含 `agent_*`
   - 哪些文件缺失
   - 哪些表为空但受支持

3. `CURRENT_SCHEMA_VERSION` 与最新 Alembic revision 保持一致

### 9.2 向后兼容原则

- 继续支持旧 `.dra` 包导入
- 新导出包仍使用 `format_version = 1`
- 通过 `manifest` 增量字段扩展，而不是直接改为新包格式

说明：本次重点是重写导入语义，不是强推新文件格式版本。

---

## 10. 后端代码重构方案

### 10.1 `data_portability.py` 拆分

建议将当前文件按职责重构为以下结构：

1. `manifest` 读写
2. `bundle` 解包与标准化
3. `table rules` 注册表
4. `import executor`
5. `file restore`

即便暂时不拆物理文件，也要在一个文件内形成清晰分段。

### 10.2 核心函数调整

#### A. 新增

```python
async def import_user_data(
    db: AsyncSession,
    user: User,
    dra_path: Path,
    *,
    mode: str,
    progress_cb: Callable[[str, int], None] | None = None,
) -> dict:
    ...
```

```python
def normalize_bundle(tmp_dir: Path, manifest: dict) -> NormalizedBundle:
    ...
```

```python
async def apply_table_import_rule(
    db: AsyncSession,
    bundle: NormalizedBundle,
    table_rule: TablePortabilityRule,
    mode: str,
    id_map: IdMap,
    user: User,
) -> TableImportStats:
    ...
```

#### B. 删除或弱化

- `_clear_user_data()` 不再作为主导入入口的第一步
- `_pre_delete_conflicts()` 不再做通用“先删再说”的粗放冲突清理

### 10.3 `id_map` 扩展

保留现有 `id_map` 思路，但从“少量特判”升级为统一结构：

```python
id_map = {
    "upload_batches": {old_id: new_id},
    "files": {old_id: new_id},
    "dimension_sets": {old_id: new_id},
    ...
}
```

所有依赖父表的子表都通过规则配置声明如何 remap。

### 10.4 selective delete 原则

覆盖模式允许删除，但必须满足：

1. 只删当前用户数据
2. 只删与当前导入记录直接冲突的那部分数据
3. 删除动作必须按该表规则显式定义

例如：

- 覆盖某个 `dimension_set` 时，只删该 set 下的 `dimension_items`
- 覆盖某个 `agent_session` 时，只删该 session 下的 messages/proposals
- 覆盖某个 `job` 时，只删该 job 的纯从属链路

绝不允许再出现“导入前把当前用户所有表全删掉”。

---

## 11. API 与前端改造

### 11.1 后端接口

在现有导入接口基础上新增 `mode` 参数。

单文件导入和分片导入完成接口都支持：

- `mode=merge_append`
- `mode=merge_replace`

### 11.2 前端交互

导入弹窗新增：

1. 文件选择
2. 模式选择
   - `追加导入`
   - `覆盖导入`
3. 风险提示
   - 追加：可能跳过重复项
   - 覆盖：只替换冲突项，不会清空全部工作区

### 11.3 返回结果

后端返回增强后的导入结果：

```json
{
  "success": true,
  "mode": "merge_append",
  "message": "导入成功。",
  "tables": {
    "files": {
      "created": 10,
      "reused": 3,
      "replaced": 0,
      "skipped": 1,
      "errors": 0
    }
  },
  "compat": {
    "schema_version": "006",
    "normalized_from_legacy": true,
    "warnings": []
  },
  "files_restored": 12,
  "files_missing": 1
}
```

---

## 12. 测试方案

### 12.1 自动化测试

新增或重写 `backend/tests` 中的 `.dra` 相关测试，至少覆盖：

1. **PostgreSQL 覆盖导入**
   - 现有数据存在
   - 导入包中部分对象冲突
   - 仅冲突对象被替换

2. **PostgreSQL 追加导入**
   - 现有数据保留
   - 重复文件按 md5 复用
   - 重复文献按业务键合并或跳过

3. **旧 SQLite 导出包兼容**
   - 缺失新表 JSON 不报错
   - 缺字段自动补默认值
   - 导入统计中包含 compat 信息

4. **外键敏感链路**
   - `upload_batches -> files`
   - `dimension_sets -> dimension_items`
   - `reading_items -> reading_item_edits`
   - `agent_sessions -> agent_messages -> agent_action_proposals`
   - `artifacts -> card_notes`

5. **物理文件恢复**
   - 文件存在时恢复成功
   - 文件缺失时数据库导入不失败

### 12.2 样本包回归测试

使用：

- `C:\Users\langx\Desktop\testdra\export_20260523_admin.dra`
- `C:\Users\langx\Desktop\testdra\export_20260529_test001 (1).dra`

验证以下场景：

1. 在 PostgreSQL 环境中执行 `追加导入`
2. 在 PostgreSQL 环境中执行 `覆盖导入`
3. 检查导入结果统计与关键表落库情况
4. 检查物理文件恢复情况

### 12.3 手工验收

至少验证：

1. 文献库可见
2. 精读结果可见
3. Prompt 模板存在
4. 维度集合存在
5. Agent 历史会话存在
6. 相关源文件可打开

---

## 13. 文档同步要求

实施完成后，必须同步更新：

1. `docs/DATABASE_SCHEMA.md`
   - 若有 schema / portability 规则变化

2. `docs/TECHNICAL_OVERVIEW.md`
   - 更新 `.dra` 导入导出链路说明

3. `docs/FUNCTION_INDEX.md`
   - 更新 `data_portability.py` / `data.py` 关键函数索引

4. `docs/STATE_AND_API_MAP.md`
   - 更新前端导入交互与 API 参数

5. `docs/README.md`
   - 追加本方案入口

---

## 14. 分阶段实施计划

### Phase 1. 方案落地

- 新增本方案文档
- 明确导入模式和冲突规则

### Phase 2. 后端核心重构

- 重写 bundle 标准化
- 重写表级规则注册
- 重写 `import_user_data()` 主流程

### Phase 3. API / 前端联动

- 导入接口增加 `mode`
- 前端导入弹窗增加模式选择
- 导入结果展示增强

### Phase 4. 测试与兼容验证

- 补充自动化测试
- 跑 `testdra` 样本包回归

### Phase 5. 文档同步

- 更新 schema / 概览 / 索引 / API 映射

---

## 15. 决策结论

本次 `.dra` 重构采用以下核心决策：

1. `.dra` 继续使用 JSON + 文件打包，不改扩展名。
2. 导入模式升级为“追加 / 覆盖（冲突替换）”，取消“先全清空再导入”的主流程。
3. 导入执行以 PostgreSQL 约束为基准设计。
4. 旧 SQLite 导出包通过 `normalize_bundle()` 做兼容层。
5. 冲突处理改为声明式表规则，不再依赖大段散乱硬编码。

这套方案可以同时解决：

- 线上 PostgreSQL 外键报错
- 用户希望“不要先清空数据库”的诉求
- 多 `.dra` 包汇总导入场景
- 旧 SQLite 导出包继续可用的兼容需求

