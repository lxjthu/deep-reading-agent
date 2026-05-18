# Deep Reading Agent

多用户学术论文在线精读工作台。用户上传 PDF、Markdown 或题录文件后，系统调用 DeepSeek 完成文献筛选、长文本/七步/四步精读、对比综述、AI 综述、参考文献提取，并将结果沉淀到个人文献库。

当前主架构是 **FastAPI + React SPA**。旧 Gradio GUI、旧 iframe 对比 demo 和 7860 端口启动链路已移除。

## 快速开始

```powershell
# 安装后端依赖
pip install -r requirements.txt

# 启动后端
uvicorn backend.main:app --reload --port 8000

# 启动前端
cd frontend
npm install
npm run dev
```

也可以使用一键开发脚本：

```powershell
.\start-dev.ps1
```

前端默认运行在 `http://localhost:5173`，Vite proxy 将 `/api` 转发到后端 `http://127.0.0.1:8000`。

## Web 打包版

packaging 分支使用 PyInstaller 生成 Windows onedir 包：

```powershell
cd frontend
npm install
npm run build
cd ..
python build_web_dist.py
```

产物为 `dist/DeepReadingAgent-Web.zip`。解压后双击 `启动DeepReadingAgent.bat`，浏览器访问 `http://localhost:8000`。打包版由 FastAPI 同时托管 API 和 React 静态文件，用户数据存放在 exe 同级 `data/` 目录。

## 核心功能

- 用户注册登录、JWT access/refresh token、admin/vip/normal 角色
- PDF/Markdown/题录上传，按用户隔离存储
- 文献筛选与 Excel 导出
- 长文本精读、七步精读、四步精读
- 批量文件夹精读
- React 对比综述视图和 AI 综述流式生成
- 文献库、历史记录、鉴权预览和下载
- 参考文献提取与引用追踪
- 提示词管理和维度模板市场
- `.dra` 用户数据导出/导入

## 目录结构

```text
frontend/
  src/RootApp.tsx
  src/App.tsx
  src/LibraryTab.tsx
  src/components/CompareView.tsx
  src/components/compare/
  src/store/auth.ts

backend/
  main.py
  routers/
  db/
  auth/
  services/
  prompt_registry.py
  prompt_service.py

new_architecture/
  conversation_engine.py

prompts/
docs/
run_web.py
build_web_dist.py
DeepReadingAgent.spec
```

## 文档

- [技术总览](docs/TECHNICAL_OVERVIEW.md)
- [状态/API/数据库映射](docs/STATE_AND_API_MAP.md)
- [函数索引](docs/FUNCTION_INDEX.md)
- [数据库 Schema](docs/DATABASE_SCHEMA.md)
- [打包指南](docs/PACKAGING_GUIDE.md)
- [部署架构](docs/DEPLOYMENT_ARCHITECTURE.md)
