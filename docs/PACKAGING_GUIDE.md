# PyInstaller 打包指南

> 适用项目：`deep-reading-agent`（packaging 分支）
> 最后更新：2026-05-16
> PyInstaller 版本：6.19.0
> Python 版本：3.13

---

## 目录

1. [打包成果概览](#1-打包成果概览)
2. [一键打包](#2-一键打包)
3. [打包架构](#3-打包架构)
4. [核心文件详解](#4-核心文件详解)
5. [打包产物结构](#5-打包产物结构)
6. [踩坑记录与解决方案](#6-踩坑记录与解决方案)
7. [手动打包步骤](#7-手动打包步骤)
8. [打包后验证清单](#8-打包后验证清单)
9. [已知限制与待改进](#9-已知限制与待改进)

---

## 1. 打包成果概览

打包后的 Deep Reading Agent 是一个**免安装、解压即用**的 Windows 桌面应用：

- **单端口架构**：后端（FastAPI）+ 前端（React SPA）共用 `localhost:8000`，无需分别启动
- **数据外置**：数据库、上传文件、分析结果全部存放在 `data/` 目录（与 exe 同级），卸载即删
- **自动初始化**：首次运行自动建库、创建管理员账户（admin / admin12345）、自动打开浏览器
- **完整功能**：包含在线版全部功能——多用户认证、文献筛选、精读（长文本/七步/四步）、对比综述、AI 综述、文献库、参考文献提取、批量精读、提示词管理、维度模板市场

### 打包版包含的功能模块

| 模块 | 说明 |
|------|------|
| 用户认证 | 注册/登录、JWT access+refresh token、admin/vip/normal 角色 |
| 文献上传 | 支持 PDF 和 Markdown 文件上传 |
| 文献筛选 | 批量题录导入、AI 智能筛选打分、筛选结果 Excel 导出 |
| 长文本精读 | 一次性整篇精读、自定义维度集合、批量文件夹上传 |
| 七步精读（定量） | 按七步框架逐步深度分析定量论文 |
| 四步精读（定性） | 按四步框架分析定性论文 |
| 对比综述 | 多篇论文跨维度对比、卡片三按钮（编辑/点评/AI总结）+ 维度级批量切换 |
| AI 综述 | 自动生成文献综述、SSE 流式输出、GB/T 7714 参考文献 |
| 文献库 | BibEntry 聚合展示、关联筛选评分/精读结果/时间线 |
| 参考文献 | DeepSeek + pdfplumber 自动提取引用文献 |
| 批量精读 | 文件夹批量提交、共享 batch_id、轮询进度 |
| 提示词管理 | 用户覆盖 > 系统默认 > 文件兜底，支持在线编辑 |
| 维度模板市场 | 预设/自定义维度集合、模板共享/AI生成/文档导入 |
| 元数据匹配 | CNKI/WoS 题录解析、本地+在线元数据匹配与合并 |
| 数据导出导入 | .dra 格式用户数据打包导出与导入 |
| 任务队列 | 排队、并发控制、预估等待时间 |
| 定时清理 | normal 用户 24h 数据自动清理 |

---

## 2. 一键打包

```powershell
# 前提：在 packaging 分支、Python 3.13 环境

# 1. 构建前端
cd frontend
npm install
npm run build
cd ..

# 2. 运行打包脚本
python build_web_dist.py
```

脚本自动完成：清理 → 重新构建前端 dist → 检查 PyInstaller → 打包 → 生成启动器 → 生成使用说明 → 打 ZIP 包。

产出文件：`dist/DeepReadingAgent-Web.zip`

### 2.1 隔离输出目录（旧 dist 被锁时）

Windows 有时会锁住旧打包目录中的 DLL（例如 `VCRUNTIME140.dll`），导致 `python build_web_dist.py` 在清理 `dist/` 时失败。`build_web_dist.py` 支持通过环境变量切换输出目录，便于先生成一份干净的 repack 包：

```powershell
python -c "import os, runpy; os.environ['DRA_DIST_DIR']=r'D:\code\deepagent\deep-reading-agent-online\deep-reading-agent\dist-repack'; os.environ['DRA_BUILD_DIR']=r'D:\code\deepagent\deep-reading-agent-online\deep-reading-agent\build-repack'; runpy.run_path('build_web_dist.py', run_name='__main__')"
```

产物为 `dist-repack/DeepReadingAgent-Web.zip`。确认可用后，可优先在 `dist-repack/` 内测试；旧 `dist/` 中被锁住的文件不影响 repack 包。

### 2.2 控制台窗口策略

当前打包脚本使用 PyInstaller `--windowed`，生成的 exe 使用 `runw.exe` bootloader，不再弹出黑色控制台窗口。stdout/stderr 会由 `run_web.py` 写入 `data/logs/startup.log`，调试时优先查看该日志。

如果需要临时观察控制台输出，可以把 `build_web_dist.py` 中的 `--windowed` 改回 `--console` 后重新打包；调试完成必须恢复 `--windowed`，避免发布版保留黑窗。

---

## 3. 打包架构

```
┌─────────────────────────────────────────────────────┐
│                    打包流程                           │
│                                                      │
│  run_web.py ────────── PyInstaller 入口              │
│       │                                              │
│       ├── sys._MEIPASS → _internal/  (只读资源)      │
│       │     ├── frontend/dist/  ← Vite 构建产物      │
│       │     ├── backend/       ← Python 源码         │
│       │     ├── prompts/       ← 提示词模板          │
│       │     └── new_architecture/                    │
│       │                                              │
│       └── sys.executable.parent → exe 同级目录       │
│             └── data/  (用户可写数据)                 │
│                  ├── .env                             │
│                  ├── db/app.sqlite                    │
│                  ├── _uploads/                        │
│                  ├── deep_reading_results/            │
│                  └── logs/                            │
│                                                      │
│  启动: run_web.py → 建库 → seed admin → uvicorn 8000│
│  前端: FastAPI FileResponse 托管 SPA                 │
│  API:  /api/* 路由由 FastAPI 处理                     │
│  SPA:  其余路由 fallback 到 index.html               │
└─────────────────────────────────────────────────────┘
```

### 与在线版的区别

| 对比项 | 在线版 (online 分支) | 打包版 (packaging 分支) |
|--------|---------------------|------------------------|
| 前端运行 | Vite dev server (5173) | FastAPI FileResponse (8000) |
| API 代理 | Vite proxy → 后端 8000 | 同端口，无代理 |
| 数据库位置 | 项目根目录 `db/` | exe 同级 `data/db/` |
| 环境变量 | 项目根 `.env` | `data/.env` |
| 文件上传 | 项目根 `_uploads/` | `data/_uploads/` |
| 分析结果 | 项目根 `deep_reading_results/` | `data/deep_reading_results/` |
| LLM Key | 前端输入（按用户隔离） | 同上 |
| 部署方式 | git push → Webhook 自动部署 | ZIP 解压 → 双击 bat |

---

## 4. 核心文件详解

### 4.1 `run_web.py` — 打包入口

PyInstaller 的入口脚本，负责启动前的全部初始化工作。

```python
# 关键路径判断
if getattr(sys, 'frozen', False):
    BUNDLE_ROOT = Path(sys._MEIPASS)   # _internal/ 目录（只读）
    EXE_DIR = Path(sys.executable).parent  # exe 所在目录
else:
    BUNDLE_ROOT = Path(__file__).parent.resolve()
    EXE_DIR = BUNDLE_ROOT
```

**启动流程**（`run_web.py:1-131`）：

1. **确定路径**：区分 PyInstaller 运行 vs 源码运行
2. **设置 sys.path**：确保 `_internal/` 和 `_internal/backend/` 可被导入
3. **创建数据目录**：`data/`、`data/db/`、`data/_uploads/` 等
4. **初始化 .env**：首次运行创建模板 .env
5. **设置环境变量**：`DATABASE_URL`、`UPLOAD_DIR`、`RESULTS_DIR` 等
6. **同步建表**：`Base.metadata.create_all()`（不使用 Alembic）
7. **seed 管理员**：创建 admin / admin12345 账户
8. **启动 uvicorn**：`uvicorn.run(app, host="127.0.0.1", port=8000)`
9. **自动打开浏览器**：3 秒后 `webbrowser.open('http://localhost:8000')`

### 4.2 `backend/main.py` — 静态文件服务

打包版中 FastAPI 同时承担 API 服务和前端静态文件托管。

```python
# main.py:140-148 — 路径解析（必须在路由注册前执行）
def get_project_root():
    """Get project root, compatible with PyInstaller."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent

project_root = get_project_root()
frontend_dist = project_root / "frontend" / "dist"
```

```python
# main.py:151-159 — 根路由：优先返回 index.html
@app.get("/")
async def root():
    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html", media_type="text/html")
    return {"message": "Deep Reading Agent API", "version": "3.0.0", "docs": "/docs"}
```

```python
# main.py:232-236 — 尾部 catch-all：SPA fallback
if frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html", media_type="text/html")
```

**三层静态文件服务机制**：

| 层级 | 匹配规则 | 处理者 |
|------|---------|--------|
| 1 | `/api/*` | FastAPI Router（优先级最高） |
| 2 | `/` | `@app.get("/")` → `FileResponse(index.html)` |
| 3 | `/assets/*`、`/favicon.svg`、SPA fallback | `serve_frontend` catch-all |

### 4.3 `DeepReadingAgent.spec` — PyInstaller 配置

```python
a = Analysis(
    ['run_web.py'],           # 入口文件
    datas=[
        ('frontend/dist', 'frontend/dist'),     # 前端构建产物
        ('.env.example', '.'),                   # .env 模板
        ('prompts', 'prompts'),                  # 提示词模板
        ('new_architecture', 'new_architecture'), # 精读引擎
        ('backend', 'backend'),                  # 整个后端源码
    ],
    hiddenimports=[...],  # 见下文 hidden imports 列表
)
```

**为什么用 `--onedir` 而非 `--onefile`**：

- `--onefile` 每次启动需解压到临时目录，启动慢 5-10 秒，且可能被杀毒软件拦截
- `--onedir` 解压即用，启动快，更新方便（可单独替换 `frontend/dist` 或 `backend/`）

### 4.4 `build_web_dist.py` — 自动化打包脚本

完整的 6 步打包流水线：

```
clean_build()          → 清理 build/ 和 dist/
check_frontend_dist()  → 强制重新构建前端
check_dependencies()   → 检查/安装 PyInstaller
build_executable()     → 执行 PyInstaller --onedir
create_launcher()      → 生成 启动DeepReadingAgent.bat
create_readme()        → 生成 使用说明.txt
create_distribution()  → 组装 ZIP 包
```

脚本还会传入：

- `--windowed`：隐藏打包版控制台窗口。
- `--distpath`、`--workpath`、`--specpath`：使用 `DIST_DIR` / `BUILD_DIR`，支持 `DRA_DIST_DIR` 与 `DRA_BUILD_DIR` 覆盖。
- 绝对路径形式的 `--add-data`：避免从不同工作目录运行脚本时资源路径失效。

---

## 5. 打包产物结构

```
dist/
├── DeepReadingAgent-Web.zip          ← 最终分发文件
└── DeepReadingAgent-Web/
    ├── 启动DeepReadingAgent.bat      ← 双击启动
    ├── 使用说明.txt                   ← 用户手册
    ├── .env.example                   ← 配置模板
    └── DeepReadingAgent/
        ├── DeepReadingAgent.exe       ← 主程序
        ├── data/                      ← 用户数据（运行时自动创建）
        │   ├── .env
        │   ├── db/app.sqlite
        │   ├── _uploads/
        │   ├── deep_reading_results/
        │   └── logs/
        └── _internal/                 ← 程序资源（只读）
            ├── frontend/dist/         ← React SPA
            │   ├── index.html
            │   ├── assets/
            │   │   ├── index-*.js     ← React + 业务代码（~480KB）
            │   │   └── index-*.css    ← Tailwind 样式（~60KB）
            │   ├── favicon.svg
            │   └── favicon.svg / icons.svg
            ├── backend/               ← FastAPI 源码
            │   ├── main.py
            │   ├── routers/           ← 16 个 API 模块
            │   ├── db/                ← ORM 模型 + session
            │   ├── services/          ← 任务队列、参考文献
            │   └── ...
            ├── prompts/               ← 提示词模板
            ├── new_architecture/      ← 精读引擎
            ├── python313.dll          ← Python 运行时
            └── ...                    ← 依赖 DLL 和库
```

---

## 6. 踩坑记录与解决方案

### 问题 1：根路由返回 API JSON 而非前端页面

**现象**：浏览器访问 `http://localhost:8000/` 返回 `{"message":"Deep Reading Agent API","version":"3.0.0"}`，白屏。

**原因**：`@app.get("/")` 路由优先级高于 `app.mount("/", StaticFiles(...))`，FastAPI 按注册顺序匹配，显式路由永远优先于 mount。

```
# 错误的路由优先级
@app.get("/")                    ← 匹配 / → 返回 JSON
app.mount("/", StaticFiles(...)) ← 永远不会被 / 触及
```

**解决方案**（commit `23f3f0ba`）：

```python
# main.py:151-159 — 根路由判断 frontend_dist 存在时返回 index.html
@app.get("/")
async def root():
    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html", media_type="text/html")
    return {"message": "Deep Reading Agent API", "version": "3.0.0", "docs": "/docs"}
```

同时将 `get_project_root()` 和 `frontend_dist` 的定义从文件末尾移到路由注册之前，避免 `NameError`。

**关键教训**：FastAPI 中显式路由（`@app.get`）优先于 mount，需要在根路由中主动判断并返回 `index.html`。

---

### 问题 2：PyInstaller 打包后路径错乱

**现象**：打包版启动时数据库创建在 `_internal/` 目录（只读），或 `.env` 文件找不到。

**原因**：PyInstaller 运行时 `__file__` 指向 `_internal/` 内的解压路径，而非 exe 所在目录。使用 `Path(__file__).parent` 计算的路径全部指向只读资源区。

**解决方案**（commit `bbf16722`）：

在 `run_web.py` 中明确区分两种路径：

```python
# 只读资源区（前端、后端源码、提示词）
BUNDLE_ROOT = Path(sys._MEIPASS)        # → _internal/

# 用户可写数据区（数据库、上传文件、结果）
EXE_DIR = Path(sys.executable).parent   # → exe 同级目录
DATA_DIR = EXE_DIR / "data"
```

并通过环境变量传递给后端：

```python
os.environ.setdefault('DATABASE_URL', f"sqlite+aiosqlite:///{db_path}")
os.environ.setdefault('UPLOAD_DIR', str(DATA_DIR / '_uploads'))
os.environ.setdefault('RESULTS_DIR', str(DATA_DIR / 'deep_reading_results'))
```

`backend/main.py` 中的 `get_project_root()` 只负责定位**只读资源**（`frontend/dist`），不应指向用户数据目录。

---

### 问题 3：hidden imports 缺失导致运行时 ModuleNotFoundError

**现象**：打包版启动后调用某些 API 报 `ModuleNotFoundError`，如 `uvicorn.logging`、`apscheduler.schedulers.asyncio` 等。

**原因**：PyInstaller 静态分析无法追踪动态导入（如 `importlib`、`uvicorn` 的协议自动选择）。以下模块必须手动声明：

**完整的 hidden imports 列表**：

```python
hidden_imports = [
    # Uvicorn（协议自动选择需要显式声明）
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    # FastAPI & ORM
    "fastapi", "sqlalchemy", "sqlalchemy.dialects.sqlite", "aiosqlite",
    # 认证
    "passlib", "passlib.handlers.bcrypt", "bcrypt",
    "jose", "jose.jwt",
    # 定时任务
    "apscheduler", "apscheduler.schedulers.background",
    "apscheduler.schedulers.asyncio", "apscheduler.triggers.interval",
    # 校验
    "email_validator",
    # PDF 提取
    "pdfplumber", "pypdf", "fitz",
    # LLM & 数据
    "openai", "pandas", "openpyxl", "tqdm",
    "yaml", "json_repair", "requests", "dotenv", "markdown",
]
```

**解决方案**（commit `67b0795e`）：

补全 hidden imports 列表，同时在 spec 文件的 `datas` 中将整个 `backend/` 目录作为数据文件打包（而非依赖 PyInstaller 自动分析），确保所有 Python 源码可用。

---

### 问题 4：整体 backend 作为 data 打包而非编译

**现象**：如果只依赖 PyInstaller 自动分析，部分 router 和 service 可能被遗漏。

**解决方案**（commit `67b0795e`）：

```python
# DeepReadingAgent.spec
datas=[
    ('frontend/dist', 'frontend/dist'),
    ('.env.example', '.'),
    ('prompts', 'prompts'),
    ('new_architecture', 'new_architecture'),
    ('backend', 'backend'),        # ← 整个 backend 目录作为 data
],
```

PyInstaller 会将 `backend/` 原样复制到 `_internal/backend/`，运行时通过 `sys.path.insert(0, BUNDLE_ROOT / "backend")` 直接 import。这种方式：

- 避免了 PyInstaller 静态分析遗漏
- 修改后端代码后只需替换 `_internal/backend/` 对应文件，无需重新打包
- 缺点是源码明文暴露（对学术工具可接受）

---

### 问题 5：`deploy.py` 运行时检查导致启动崩溃

**现象**：打包版启动时报 `git` 相关错误，无法启动。

**原因**：`backend/routers/deploy.py` 中有 Git 仓库检查逻辑（用于在线版的 Webhook 部署），在打包版中不存在 `.git` 目录。

**解决方案**（commit `67b0795e`）：

在 `deploy.py` 中添加延迟检查，仅在 `.git` 目录存在时执行 Git 操作：

```python
# deploy.py 中对 git 操作加保护
if not Path(".git").exists():
    # 打包模式，跳过 git 相关功能
    return ...
```

---

### 问题 6：数据库迁移在打包版中不可用

**现象**：打包版运行 Alembic 迁移失败（缺少 `migrations/` 目录和 `alembic.ini`）。

**原因**：打包版没有包含 Alembic 迁移框架，且数据库位于用户 `data/db/` 目录。

**解决方案**（commit `bbf16722`）：

打包版使用 `Base.metadata.create_all()` 同步建表，不依赖 Alembic。这要求：

- 所有新表必须在 `backend/db/models.py` 中定义
- 模型变更需通过 `run_web.py` 的 `_init_db()` 处理
- 不支持增量迁移（打包版适合全新安装）

如果未来需要支持数据库升级，需要在 spec 文件中添加 `('backend/migrations', 'backend/migrations')` 和 `('alembic.ini', '.')` 到 datas。

---

### 问题 7：migration 011 幂等处理

**现象**：打包版启动时 `create_all()` 报表已存在错误。

**原因**：`models.py` 中某些表通过 migration 011 新增（`reading_item_edits`、`reading_item_annotations`），`create_all()` 会尝试建所有已定义的表。

**解决方案**（commit `87c88ef6`）：

在 migration 011 中添加幂等检查：

```python
# 建表前检查表是否已存在
def upgrade():
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reading_item_edits'"
    ))
    if result.fetchone() is None:
        op.create_table('reading_item_edits', ...)
```

---

### 问题 8：PDF/Excel 依赖在打包后运行时缺失

**现象**：

- 精读 PDF 时出现 `No module named 'pdfminer.high_level'`。
- 导出或读取 Excel 时，PyInstaller warning 中出现 `xlsxwriter`，容易误判为 Excel 导出不可用。

**原因**：

- `extractor.py` 被复制进 `_internal/` 只是 data 文件，PyInstaller 不会因为 data 源码自动分析其中的 `pdfminer.high_level` 依赖。
- pandas 暴露多个 Excel 引擎的可选导入 warning；当前 `.xlsx` 写入和读取实际依赖的是 `openpyxl`。
- `backend/services/*` 中有多处延迟导入，打包分析阶段需要把 `backend/` 加到 PyInstaller module search path。

**解决方案**：

- `build_web_dist.py` 增加 `--paths=backend`。
- hidden imports 增加 `extractor`、`parsers`、`smart_literature_filter`、`python_multipart`、`multipart`、`httpx`、`pdfminer.high_level` 和相关 PDF 解析模块。
- hidden imports 增加 `services.ai_template_generator`、`services.deepseek_refs`、`services.document_parser`、`services.pdf_metadata_extract`、`services.pdf_metadata_llm` 等延迟导入服务模块。
- `--collect-submodules` 收集 `pdfminer`、`pdfplumber`、`pypdf`、`PyPDF2`、`fitz`、`openpyxl`。
- Excel 读写点显式指定 `engine="openpyxl"`，避免依赖 pandas 自动选择引擎。

**当前必须能在归档中看到的关键模块**：

```text
extractor
pdfminer.high_level
pdfplumber
openpyxl
openpyxl.writer.excel
pandas.io.excel._openpyxl
python_multipart
multipart
services.ai_template_generator
services.deepseek_refs
```

`xlsxwriter` 如果仍出现在 `warn-DeepReadingAgent.txt`，属于 pandas 的可选延迟导入；当前代码已固定使用 `openpyxl`，不需要把 `xlsxwriter` 作为强依赖。

**验证方式**：

```powershell
python build_web_dist.py
python -m PyInstaller.utils.cliutils.archive_viewer -l -r -b dist\DeepReadingAgent\DeepReadingAgent.exe |
  Select-String -Pattern "pdfminer.high_level|openpyxl|pandas.io.excel._openpyxl|services.deepseek_refs"
```

每次代码改动完成后，默认重新执行 `python build_web_dist.py` 并做至少一次 `GET /health` 冒烟测试，避免“本地源码可用、打包产物缺依赖”的问题再次出现。

### 问题 9：旧打包目录被 DLL 锁住

**现象**：重打包时清理 `dist/` 失败，常见报错为 `PermissionError: [WinError 5]` 或 `The process cannot access the file because it is being used by another process`，文件多为 `_internal/VCRUNTIME140.dll`。

**处理**：

1. 先确认没有 `DeepReadingAgent.exe` 进程：

```powershell
Get-Process DeepReadingAgent -ErrorAction SilentlyContinue
```

2. 如果仍被锁住，改用隔离输出目录：

```powershell
python -c "import os, runpy; os.environ['DRA_DIST_DIR']=r'D:\code\deepagent\deep-reading-agent-online\deep-reading-agent\dist-repack'; os.environ['DRA_BUILD_DIR']=r'D:\code\deepagent\deep-reading-agent-online\deep-reading-agent\build-repack'; runpy.run_path('build_web_dist.py', run_name='__main__')"
```

3. 在 `dist-repack/` 测试新包，确认后再择机清理旧 `dist/`。

---

## 7. 手动打包步骤

如果不使用 `build_web_dist.py`，可以手动执行：

```powershell
# Step 1: 构建前端
cd frontend
npm install
npm run build
cd ..

# Step 2: 安装 PyInstaller
pip install pyinstaller

# Step 3: 使用 spec 文件打包
python -m PyInstaller DeepReadingAgent.spec --noconfirm

# Step 4: 测试运行
cd dist\DeepReadingAgent
..\..\run_web.py   # 源码模式测试
DeepReadingAgent.exe  # 打包模式测试

# Step 5: 创建 ZIP（可选）
Compress-Archive -Path dist\DeepReadingAgent -DestinationPath dist\DeepReadingAgent-Web.zip
```

### 仅更新前端（无需重新打包后端）

```powershell
cd frontend && npm run build
# 直接替换打包目录中的前端文件
Copy-Item -Recurse -Force frontend\dist\* dist\DeepReadingAgent\_internal\frontend\dist\
```

### 仅更新后端（无需重新打包）

```powershell
# 直接替换打包目录中的后端文件
Copy-Item -Recurse -Force backend\*.py dist\DeepReadingAgent\_internal\backend\
Copy-Item -Recurse -Force backend\routers\*.py dist\DeepReadingAgent\_internal\backend\routers\
```

---

## 7.1 发布到 GitHub Release 与 OSS

打包 ZIP 发布复用 `docs/RELEASE_OSS_UPLOAD_RUNBOOK.md`。

典型流程：

```powershell
# 1. 上传到 GitHub Release
gh release upload v2.0.0 "dist-repack\DeepReadingAgent-Web.zip#DeepReadingAgent-Web-2026-05-24.zip" --repo lxjthu/deep-reading-agent --clobber

# 2. 上传到阿里云 OSS，并生成 24 小时签名 URL
python scripts\upload_release_to_oss.py dist-repack\DeepReadingAgent-Web.zip --object releases/DeepReadingAgent-Web-2026-05-24.zip
```

OSS 目标约定：

- bucket：`lxj-pdf-upload`
- endpoint：`https://oss-cn-wuhan-lr.aliyuncs.com`
- object：`releases/DeepReadingAgent-Web-YYYY-MM-DD.zip`

换包后，线上下载入口只需要更新服务器环境变量：

```text
ALIYUN_OSS_APP_OBJECT=releases/DeepReadingAgent-Web-YYYY-MM-DD.zip
```

不要把长期 AccessKey、短期签名 URL 或 GitHub token 写入仓库。若临时使用 `gh auth login --insecure-storage`，上传完成后必须执行：

```powershell
gh auth logout -h github.com -u lxjthu
```

---

## 8. 打包后验证清单

### 基础启动

- [ ] 双击 `启动DeepReadingAgent.bat` 后不应保留黑色控制台窗口
- [ ] 浏览器自动打开 `http://localhost:8000`
- [ ] 页面显示登录/注册界面（非 API JSON）
- [ ] `data/logs/startup.log` 中可看到启动日志与静态资源目录

### 用户认证

- [ ] 使用 admin / admin12345 登录成功
- [ ] 注册新用户成功
- [ ] 退出后重新登录成功
- [ ] Token 过期后自动 refresh

### 核心功能

- [ ] 上传 PDF 文件
- [ ] 上传 Markdown 文件
- [ ] 设置 API Key
- [ ] 长文本精读：提交并等待完成
- [ ] 七步精读：提交并等待完成
- [ ] 四步精读：提交并等待完成
- [ ] 对比综述：选择多篇论文查看对比
- [ ] AI 综述：生成文献综述
- [ ] 文献库：查看已读论文
- [ ] 参考文献提取
- [ ] 下载 Excel/Markdown 结果

### 数据持久化

- [ ] 重启程序后，历史数据仍在
- [ ] `data/db/app.sqlite` 文件存在且大小 > 0
- [ ] 上传的 PDF 存在于 `data/_uploads/`
- [ ] 分析结果存在于 `data/deep_reading_results/`

### 静态资源

- [ ] `GET /` 返回 `text/html`
- [ ] `GET /assets/index-*.js` 返回 200
- [ ] `GET /assets/index-*.css` 返回 200
- [ ] `GET /favicon.svg` 返回 200（或 404 不影响使用）
- [ ] 浏览器 F12 Network 无 404 错误（favicon.ico 除外）

---

## 9. 已知限制与待改进

### 当前限制

| 限制 | 说明 |
|------|------|
| 仅 Windows | 当前只支持 Windows，未测试 macOS/Linux |
| Python 源码明文 | backend 作为 data 打包，源码可被用户查看 |
| 无增量迁移 | 打包版使用 `create_all()`，不支持已有数据库的 schema 升级 |
| 不含 PaddleOCR | PDF 提取回退到 pdfplumber（需配置远程 PaddleOCR 服务） |
| 不含 Alembic | 数据库迁移框架未打包，首次安装自动建表 |
| 单机模式 | 无 HTTPS、无反向代理、不适合公网暴露 |

### 待改进

1. **Inno Setup / NSIS 安装程序**：替代 ZIP + bat，提供开始菜单快捷方式、卸载程序
2. **HTTPS 支持**：嵌入自签名证书或 mkcert
3. **系统托盘**：最小化到托盘并提供托盘菜单
4. **自动更新**：检查 GitHub Release 新版本并提示
5. **数据库升级**：打包 Alembic，支持增量迁移
6. **日志文件**：进一步结构化 `data/logs/` 中的启动、访问与错误日志
7. **端口冲突检测**：8000 端口被占用时提示或自动换端口

---

## 附录 A：打包相关文件清单

| 文件 | 作用 |
|------|------|
| `run_web.py` | PyInstaller 入口，启动初始化 |
| `build_web_dist.py` | 自动化打包脚本（6 步流水线） |
| `DeepReadingAgent.spec` | PyInstaller spec 配置（onedir 模式） |
| `backend/main.py` | FastAPI 入口 + 静态文件托管 + 根路由修复 |
| `frontend/vite.config.ts` | Vite 构建配置（base 默认 `/`） |
| `.env.example` | 配置模板 |
| `dist/启动DeepReadingAgent.bat` | 用户启动器 |
| `dist/使用说明.txt` | 用户手册 |

## 附录 B：环境变量映射

打包版通过 `run_web.py` 设置以下环境变量，覆盖 `backend/main.py` 中的默认值：

| 环境变量 | 打包版值 | 在线版默认值 |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///data/db/app.sqlite` | `sqlite+aiosqlite:///db/app.sqlite` |
| `UPLOAD_DIR` | `data/_uploads/` | `_uploads/` |
| `UPLOAD_ROOT_DIR` | `data/_uploads/` | `_uploads/` |
| `RESULTS_DIR` | `data/deep_reading_results/` | `deep_reading_results/` |
| `RESULTS_ROOT_DIR` | `data/deep_reading_results/` | `deep_reading_results/` |
| `DEEP_READING_DATA_DIR` | `data/` | （未设置） |

## 附录 C：Git 分支策略

```
online ────────────────────── 在线版主分支（自动部署到服务器）
  │
  └── packaging ───────────── 打包分支
        │
        ├── 定期 merge online → packaging（同步在线版功能）
        ├── 打包相关修改只在 packaging 分支
        └── main.py 的差异仅限静态文件服务部分
```

`packaging` 分支相对于 `online` 分支的独有修改：

1. `backend/main.py`：`get_project_root()` + `frontend_dist` 定义前移 + 根路由 `FileResponse` 逻辑
2. `run_web.py`：打包版启动入口
3. `build_web_dist.py`：打包脚本
4. `DeepReadingAgent.spec`：PyInstaller 配置
5. `backend/db/models.py`：migration 011 幂等处理
