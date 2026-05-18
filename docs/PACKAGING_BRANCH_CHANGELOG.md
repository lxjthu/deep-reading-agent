# Packaging 分支修改记录

分支：`packaging`
创建日期：2026-05-16
目的：记录对打包分支的所有修改计划与实施进展。

---

## 修改计划

### [已实施] 精读结果多版本并存
- **日期**：2026-05-16
- **描述**：同一篇文献用不同模式精读时结果并存（七步/四步/长文本互不影响）；同模式由用户选择覆盖或新增；长文本支持增量精读（跳过已有维度）
- **设计文档**：`docs/superpowers/specs/2026-05-16-reading-multi-version-design.md`
- **实施计划**：`docs/superpowers/plans/2026-05-16-reading-multi-version.md`
- **相关文件**：`reading.py`、`compare.py`、`App.tsx`、`ConflictDialog.tsx`、`LibraryTab.tsx`、`CompareView.tsx`、`useCompareData.ts`
- **备注**：11 个 Task 全部完成，前端构建通过，后端路由验证通过

## 修改历史

### [2026-05-16] 精读结果多版本并存 — ✅已实施
- `cleanup_old_reading_data` 增加 job_type 过滤，不同模式互不影响
- 废弃 `force_overwrite`，改用 `conflict_resolution`（overwrite/new/incremental）
- 新增 `POST /check-conflict` 端点，返回冲突详情
- 长文本增量精读：跳过已有维度，复用旧结果
- 前端 ConflictDialog 弹窗替代 window.confirm
- 对比综述按 bib_entry 取最新 job，文献库折叠展示多条精读记录
- **调试修复**：409 后 fall through 导致 `task/undefined` 无限轮询；`check_reading_duplicate` 不区分模式误报冲突；`scalar_one_or_none` 多结果报错改为 `scalars().first()`；QualTab handleConflictResolve 错误调用 long/start；`err.detail` 对象序列化 `[object Object]`
