# 离线 HTML 阅读快照

```powershell
python scripts/dra.py reader build --workspace D:/Research/workspace
python scripts/dra.py reader build --workspace D:/Research/workspace --entry-id ENTRY_ID --include-pdf
python scripts/dra.py reader serve --workspace D:/Research/workspace --build-id BUILD_ID
```

build 返回 `reader/BUILD_ID/index.html`，可双击打开。每次创建新目录，`reader/latest.json` 指向最近构建。HTML 是可重建快照；Markdown、JSON 和原件仍是正式来源。后续修改研究内容后需重新构建，旧快照不会自动更新，也不会覆盖用户编辑的页面。

首页提供关键词搜索、类型筛选和分页。论文页可切换原文、清洗候选、精读、翻译、问答、卡片、风格等现有产物版本；集合报告单独显示参与文献。支持目录、表格横向滚动、本地公式渲染、脚注、代码块、字体与行宽调整、MD 下载和打印。页内查找使用浏览器 Ctrl+F。证据记录显示引句、冻结来源、位置及匹配状态；未知页与未定位项不会当作已验证证据。

默认只导出选中文献的可读文本、必要图片与证据。`--entry-id` 可重复使用；集合的全部成员都被选中时才加入该集合报告。原 PDF 仅在显式 `--include-pdf` 时复制，并提供物理页链接；默认页面明确说明未包含 PDF。构建不会复制 `.env`、原始模型消息、native 请求文件或整个工作区。

全部样式、脚本、数学字体在本地。原稿 HTML 经过白名单清洗后展示：保留表格与合并单元格，去除脚本、事件属性和危险链接；原件内容保持不变。外部图片不会请求；本地缺图以提示显示。无法解析的公式保留源码并提示。阅读目录整体移动后仍可打开，不依赖原仓库或外网。

若宿主不允许 file URL，可用 serve 临时预览。只监听 `127.0.0.1`，默认临时端口，且只服务生成目录；前台按 Ctrl+C 停止，不启动生产服务。

依赖与许可证见 [THIRD_PARTY.md](../THIRD_PARTY.md)。新阅读页的显示成功不代表历史报告的事实核查通过；失败、待回答、待核查候选和人工稿均有各自状态。
