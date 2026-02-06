# 深度阅读助手 - 新手入门教程

> 本教程假设你是完全零基础的用户，会一步一步带你完成安装和使用。
> 遇到问题请先查看文末的「常见问题」。

---

## 目录

1. [这个工具是做什么的？](#1-这个工具是做什么的)
2. [你需要准备什么](#2-你需要准备什么)
3. [第一步：安装 Python](#3-第一步安装-python)
4. [第二步：解压发布包](#4-第二步解压发布包)
5. [第三步：获取 API 密钥](#5-第三步获取-api-密钥)
6. [第四步：启动程序](#6-第四步启动程序)
7. [第五步：配置 API 密钥](#7-第五步配置-api-密钥)
8. [使用教程：五个功能标签页](#8-使用教程五个功能标签页)
9. [理解输出结果](#9-理解输出结果)
10. [常见问题与解决](#10-常见问题与解决)

---

## 1. 这个工具是做什么的？

「深度阅读助手」是一个**学术论文自动精读工具**。你给它一篇 PDF 论文，它会：

1. **提取文本** — 将 PDF 转换为结构化的 Markdown 文件
2. **智能分类** — 自动判断论文类型（计量经济学/社会科学/非学术文献）
3. **深度分析** — 像经济学教授一样，从 7 个维度逐步精读论文
4. **生成报告** — 输出结构化的深度阅读报告，可直接导入 Obsidian 笔记软件

整个过程通过一个网页界面操作，不需要写任何代码。

---

## 2. 你需要准备什么

| 准备项 | 说明 |
|--------|------|
| **Windows 电脑** | Windows 10 或 Windows 11（推荐），macOS 和 Linux 也支持但本教程以 Windows 为例 |
| **Python 3.10+** | 编程语言运行环境，下面会教你安装 |
| **DeepSeek API 密钥** | 核心分析引擎，**必须配置**，下面会教你申请 |
| **网络连接** | 需要联网调用 DeepSeek API |
| **磁盘空间** | 约 1 GB（Python + 依赖包），每篇论文报告约 200KB-2MB |

**可选但推荐：**

| 准备项 | 说明 |
|--------|------|
| PaddleOCR API | 远程版面分析服务，提取含表格、公式的 PDF 效果远好于默认方案 |
| Qwen（通义千问）API 密钥 | 用于从 PDF 图片中精确识别论文标题、作者、期刊、年份 |

---

## 3. 第一步：安装 Python

> 如果你已经安装了 Python 3.10 或更高版本，可以跳过这一步。
> 不确定的话，按 `Win + R`，输入 `cmd` 回车，然后输入 `python --version` 回车。
> 如果显示 `Python 3.10.x` 或更高，说明已安装。

### 3.1 下载 Python

1. 打开浏览器，访问 **https://www.python.org/downloads/**
2. 点击黄色大按钮 **"Download Python 3.x.x"**（版本号 3.10 以上即可）
3. 下载完成后会得到一个 `.exe` 安装文件

### 3.2 安装 Python（关键步骤，不能跳过！）

1. 双击下载的安装文件
2. **最重要的一步**：在安装界面底部，**勾选「Add Python to PATH」**（或「Add python.exe to PATH」）
   ```
   ┌─────────────────────────────────────────┐
   │  Install Python 3.x.x                   │
   │                                          │
   │  ☐ Install launcher for all users        │
   │  ☑ Add python.exe to PATH    ← 必须勾选！ │
   │                                          │
   │  [ Install Now ]  [ Customize... ]       │
   └─────────────────────────────────────────┘
   ```
   > **如果忘记勾选**：卸载 Python，重新安装，这次记得勾选。
3. 点击 **"Install Now"**
4. 等待安装完成，点击 **"Close"**

### 3.3 验证安装

1. 按 `Win + R`，输入 `cmd`，按回车，打开命令提示符
2. 输入以下命令，按回车：
   ```
   python --version
   ```
3. 如果显示类似 `Python 3.12.3`，说明安装成功
4. 如果显示 `'python' 不是内部或外部命令`，说明 PATH 没配好，请重新安装并勾选 "Add to PATH"

---

## 4. 第二步：解压发布包

1. 下载发布包 `deep-reading-agent-gui-xxxxxxxx.zip`
2. **右键点击** zip 文件 → 选择 **"全部解压缩"**（或使用 7-Zip、WinRAR）
3. 选择一个你容易找到的位置，比如 `D:\` 或桌面
4. 解压后你会看到一个文件夹 `deep-reading-agent`，里面的关键文件：

```
deep-reading-agent/
├── start.bat          ← 双击这个启动！
├── app.py             ← 主程序
├── setup_env.py       ← API 密钥配置对话框
├── requirements.txt   ← 依赖列表
├── .env.example       ← 环境变量模板
├── README_GUI.md      ← 详细使用手册
└── ...（其他代码文件）
```

> **注意**：不要把文件放在含有中文或空格的路径下（如 `C:\Users\张三\桌面\`），可能导致问题。
> 推荐放在 `D:\deep-reading-agent\` 这样的简单英文路径。

---

## 5. 第三步：获取 API 密钥

### 5.1 DeepSeek API 密钥（必须）

DeepSeek 是驱动论文分析的核心 AI 引擎。

1. 打开 **https://platform.deepseek.com/**
2. 点击 **"注册"** 或 **"登录"**（支持手机号注册）
3. 登录后，点击左侧菜单的 **"API Keys"**
4. 点击 **"创建 API Key"**
5. 复制生成的密钥（以 `sk-` 开头的一长串字符），**保存好，只显示一次！**

> **费用说明**：
> - 新注册通常赠送免费额度
> - 一篇 20 页论文的完整精读大约消耗 15-30 万 token
> - `deepseek-reasoner`（深度推理模型）价格高于 `deepseek-chat`
> - 建议先充值 10-20 元试用

### 5.2 Qwen（通义千问）API 密钥（推荐）

Qwen 用于从 PDF 页面截图中精确识别论文的标题、作者、期刊和发表年份。不配置也能用，但元数据识别效果会差一些。

1. 打开 **https://dashscope.console.aliyun.com/**
2. 使用阿里云账号登录（没有的话需要先注册阿里云）
3. 在控制台中找到 **"API-KEY 管理"**
4. 创建新的 API Key，复制保存

> **费用说明**：Qwen-VL-Plus 模型每篇论文只调用一次（3 张图片），费用极低（约几分钱）。

### 5.3 PaddleOCR API（推荐但非必需）

PaddleOCR 提供高质量的 PDF 文本提取，能识别表格、公式和多栏版面。如果不配置，系统会使用 pdfplumber（免费但效果较差）。

> PaddleOCR 远程 API 需要自行部署或使用第三方服务。如果你没有，可以先跳过，系统会自动回退到 pdfplumber。

---

## 6. 第四步：启动程序

### 6.1 双击 start.bat

在 `deep-reading-agent` 文件夹中，找到 `start.bat`，**双击运行**。

你会看到一个黑色的命令行窗口，依次显示：

```
============================================
  Deep Reading Agent - One-Click Launcher
============================================

[1/5] Searching for Python ...
      Found: Python 3.12.3 (py launcher)

[2/5] Setting up virtual environment ...
      Creating virtual environment ...        ← 首次运行会创建，需要几秒
      Virtual environment created.

[3/5] Installing dependencies ...
      Installing packages from requirements.txt ...  ← 首次运行需要几分钟
      All packages installed successfully.

[4/5] Checking environment configuration ...
      .env file not found. Opening configuration dialog ...  ← 弹出配置窗口
```

> **首次启动会比较慢**（3-10 分钟），因为需要下载安装所有依赖包。以后启动只需几秒。

### 6.2 如果看到报错

| 报错信息 | 原因 | 解决 |
|----------|------|------|
| `Python not found` | Python 没装或没加 PATH | 回到第 3 步重新安装 |
| `Failed to create virtual environment` | Python 版本太低或损坏 | 确保 Python 3.10+ |
| `Some packages may have failed` | 某些包安装失败 | 见下方「依赖安装问题」 |

---

## 7. 第五步：配置 API 密钥

### 7.1 首次启动自动弹窗

如果是第一次运行，会自动弹出一个配置窗口：

```
┌─────────────────────────────────────────────────┐
│  Deep Reading Agent                              │
│  Configure API keys. Only DeepSeek is required.  │
│                                                  │
│  DeepSeek API Key *:  [sk-...              ]     │
│  DeepSeek Base URL:   [https://api.deepseek.com] │
│  PaddleOCR API URL:   [                    ]     │
│  PaddleOCR API Token: [                    ]     │
│  Qwen Vision API Key: [                    ]     │
│                                                  │
│  ☐ Show keys                                     │
│                                                  │
│  [ Save & Start ]  [ Skip ]  [ Cancel ]          │
└─────────────────────────────────────────────────┘
```

**填写说明**：

| 字段 | 必填？ | 填什么 |
|------|--------|--------|
| DeepSeek API Key | **必填** | 粘贴你在 5.1 获取的 `sk-...` 密钥 |
| DeepSeek Base URL | 不用填 | 保持默认 `https://api.deepseek.com` |
| PaddleOCR API URL | 选填 | 如果你有 PaddleOCR 服务地址就填，没有就留空 |
| PaddleOCR API Token | 选填 | PaddleOCR 的访问令牌，和上面配套使用 |
| Qwen Vision API Key | 推荐填 | 粘贴你在 5.2 获取的通义千问 API 密钥 |

填好后点击 **"Save & Start"**。

### 7.2 手动修改配置

如果之后需要修改 API 密钥：

1. 用记事本打开 `deep-reading-agent` 文件夹下的 `.env` 文件
2. 直接编辑对应的值，保存
3. 重新启动程序即可生效

如果找不到 `.env` 文件：
- Windows 默认隐藏没有扩展名的文件
- 在文件资源管理器中，点击顶部 **"查看"** → 勾选 **"隐藏的项目"**
- 或者直接复制 `.env.example` 并重命名为 `.env`，然后编辑

`.env` 文件示例内容：
```ini
DEEPSEEK_API_KEY=sk-你的密钥
PADDLEOCR_REMOTE_URL=https://你的paddleocr地址
PADDLEOCR_REMOTE_TOKEN=你的token
QWEN_API_KEY=sk-你的qwen密钥
```

> **重要**：等号两边不要有空格，值不要加引号。

---

## 8. 使用教程：五个功能标签页

配置完成后，程序会自动打开浏览器，显示 **http://127.0.0.1:7860** 。

页面顶部会显示环境状态，例如：

```
环境状态: DeepSeek API: Configured | PaddleOCR: Remote API | Qwen Vision: Configured
```

如果看到 `DeepSeek API: Missing`，说明 `.env` 配置有问题，请回到第 7 步。

---

### Tab 1: 论文筛选

**用途**：从 Web of Science (WoS) 或中国知网 (CNKI) 导出的文献列表中，快速筛选与你研究主题相关的论文。

**使用步骤**：

1. 在 WoS 或 CNKI 中检索文献，导出为纯文本文件（WoS 的 `savedrecs.txt` 或 CNKI 导出的 `.txt`）
2. 在左侧点击 **"上传 WoS/CNKI 导出文件"**，选择你的文件
3. （可选）选择 **AI 评估模式**：
   - **无** — 只做基本解析和关键词过滤，不调用 AI
   - **explorer (广泛探索)** — 适合初步探索，筛选范围较宽
   - **reviewer (严格评审)** — 适合系统性综述，严格评审
   - **empiricist (实证导向)** — 适合寻找实证方法论文
4. 如果选了 AI 模式，在 **"研究主题"** 框中输入你的研究主题（例如：`数字经济对农村收入的影响`）
5. （可选）设置最早年份、关键词过滤等
6. 点击 **"开始筛选"**
7. 右侧会显示筛选结果表格和 Excel 下载链接

> **费用**：不启用 AI 模式免费；AI 模式每篇文献约消耗 1000-2000 token。

---

### Tab 2: 单文件精读（核心功能）

**用途**：对一篇 PDF 论文进行完整的深度阅读分析。

**使用步骤**：

1. 在左侧点击 **"上传 PDF 文件"**，选择一篇论文的 PDF
2. 选择 **提取方式**：
   - **PaddleOCR (远程API)** — 推荐，效果最好（需要配置 PaddleOCR API）
   - **PaddleOCR (本地GPU)** — 需要额外安装 GPU 版 PaddleOCR
   - **Legacy (pdfplumber)** — 免费方案，不需要额外配置，但不能识别表格和公式
3. 点击 **"开始精读"**
4. 右侧会依次显示 5 个阶段的进度：

```
[阶段 1/5] 提取 PDF             ← 将 PDF 转换为文本（约 1-3 分钟）
[阶段 2/5] 深度阅读（7步分析）   ← 核心分析，逐步生成 7 篇报告（约 10-20 分钟）
[阶段 3/5] 补充检查              ← 检查并补充缺失内容（约 2-5 分钟）
[阶段 4/5] 注入 Dataview 摘要    ← 生成结构化元数据（约 1-2 分钟）
[阶段 5/5] 注入 Obsidian 元数据  ← 提取标题、作者等信息（约 30 秒）
```

5. 完成后，右侧会显示最终报告预览和结果目录路径

> **耗时**：一篇 20 页论文约 15-30 分钟。
> **费用**：约消耗 15-30 万 token（以 DeepSeek 定价计算约 1-3 元）。

**7 步分析包含**：

| 步骤 | 分析内容 |
|------|----------|
| Step 1 Overview | 研究概览：核心问题、贡献、结论 |
| Step 2 Theory | 理论框架：文献综述、研究假说 |
| Step 3 Data | 数据考古：数据来源、样本选择 |
| Step 4 Variables | 变量定义：核心变量、控制变量 |
| Step 5 Identification | 识别策略：计量模型、内生性处理 |
| Step 6 Results | 结果解读：回归结果、稳健性检验 |
| Step 7 Critique | 批判评价：研究局限、未来方向 |

---

### Tab 3: 批量精读

**用途**：一次性分析一个文件夹中的所有 PDF 论文。

**使用步骤**：

1. 将所有要分析的 PDF 放在同一个文件夹中
2. 在 **"PDF 文件夹路径"** 中输入文件夹路径（例如：`D:\papers`）
3. 点击 **"验证路径"** 确认路径正确，会显示找到的 PDF 数量
4. 勾选 **"跳过已处理"**（推荐，这样中断后可以继续）
5. 选择提取方式
6. 点击 **"开始批量精读"**

系统会自动：
- 逐个提取 PDF 并分类（计量 QUANT / 社科 QUAL / 跳过 IGNORE）
- 计量论文走 7 步深度阅读流程
- 社科论文走 4 层金字塔分析流程
- 右侧表格实时显示每篇论文的处理进度

> **注意**：批量处理会消耗大量 token。10 篇论文约消耗 150-300 万 token。建议先用 Tab 2 试一篇看效果。

---

### Tab 4: PDF 提取

**用途**：只做 PDF → Markdown 转换，不做分析。适合只想提取文本的场景。

**使用步骤**：

1. 上传 PDF 文件
2. 调整提取参数（一般保持默认即可）：
   - **表格识别** ✅ — 将表格转为 Markdown 表格
   - **公式识别** ✅ — 将公式转为 LaTeX
   - **图表解析** ❌ — 较慢，一般不需要
   - **方向矫正** ❌ — 仅对扫描件有用
3. 点击 **"开始提取"**
4. 完成后可预览提取结果，并下载 `.md` 文件

---

### Tab 5: MD 文件精读

**用途**：跳过 PDF 提取步骤，直接对已有的 Markdown 文件进行深度分析。

**适用场景**：
- 已经用 Tab 4 提取过的 MD 文件
- 从其他工具获得的 Markdown 论文文本

**使用步骤**：

1. 选择模式：**单文件** 或 **文件夹**
2. 上传 MD 文件（或输入文件夹路径）
3. 点击 **"开始精读"**

---

## 9. 理解输出结果

所有分析结果保存在 `deep-reading-agent` 文件夹下：

```
deep-reading-agent/
├── paddleocr_md/                        ← PDF 提取输出
│   └── 论文名_paddleocr.md
│
├── deep_reading_results/                ← 计量论文 (QUANT) 分析结果
│   └── 论文名/
│       ├── semantic_index.json          ← 语义索引
│       ├── section_routing.md           ← 章节路由记录
│       ├── 1_Overview.md                ← 步骤 1: 研究概览
│       ├── 2_Theory.md                  ← 步骤 2: 理论框架
│       ├── 3_Data.md                    ← 步骤 3: 数据考古
│       ├── 4_Variables.md               ← 步骤 4: 变量定义
│       ├── 5_Identification.md          ← 步骤 5: 识别策略
│       ├── 6_Results.md                 ← 步骤 6: 结果解读
│       ├── 7_Critique.md               ← 步骤 7: 批判评价
│       └── Final_Deep_Reading_Report.md ← 最终合并报告
│
└── social_science_results_v2/           ← 社科论文 (QUAL) 分析结果
    └── 论文名/
        ├── L1_Context.md                ← 层 1: 背景与问题
        ├── L2_Theory.md                 ← 层 2: 理论分析
        ├── L3_Logic.md                  ← 层 3: 逻辑论证
        ├── L4_Value.md                  ← 层 4: 价值评判
        └── 论文名_Full_Report.md        ← 完整报告
```

### 在 Obsidian 中使用

如果你使用 [Obsidian](https://obsidian.md/) 笔记软件：

1. 打开 Obsidian
2. 点击 "打开文件夹作为仓库"
3. 选择 `deep_reading_results` 文件夹
4. 所有报告会自动显示，支持双向链接和 Dataview 查询

每个 `.md` 文件都包含 YAML 元数据头：

```yaml
---
title: 论文标题
authors:
  - 作者1
  - 作者2
journal: 期刊名称
year: '2024'
tags:
  - paper
  - deep-reading
---
```

---

## 10. 常见问题与解决

### 安装相关

---

**Q: 双击 `start.bat` 没有反应 / 一闪而过**

这通常是 Python 没有安装或没有加入 PATH。

解决：
1. 按 `Win + R`，输入 `cmd`，回车
2. 在命令提示符中输入 `python --version`
3. 如果显示版本号（3.10+）→ Python 正常，问题在其他地方
4. 如果报错 → 回到第 3 步重新安装 Python，**确保勾选 "Add to PATH"**

如果确认 Python 已安装但仍一闪而过，用以下方法查看报错信息：
1. 在 `deep-reading-agent` 文件夹空白处，按住 `Shift` 并右键 → 选择 **"在此处打开 PowerShell 窗口"**
2. 输入 `.\start.bat` 回车
3. 观察报错信息

---

**Q: 安装依赖时报错 `paddlex` 安装失败**

`paddlex[ocr]` 是本地 GPU 版 PaddleOCR，需要 NVIDIA GPU 和 CUDA 环境。**大多数用户不需要安装它。**

解决：
1. 这个报错不影响使用。程序会显示 `Some packages may have failed`，但核心功能正常
2. 你可以使用「PaddleOCR (远程API)」或「Legacy (pdfplumber)」提取方式，都不依赖这个包
3. 如果想去掉这个警告，可以编辑 `requirements.txt`，删掉 `paddlex[ocr]>=3.4.1` 那一行，然后重新运行 `start.bat`

---

**Q: 安装依赖时报错 `pymupdf` 找不到**

`pymupdf` 是 PDF 视觉提取（Qwen VL）所需的库，但可能未包含在 `requirements.txt` 中。

解决：
1. 在 `deep-reading-agent` 文件夹中，按住 `Shift` 并右键 → **"在此处打开 PowerShell 窗口"**
2. 输入以下命令安装：
   ```powershell
   .\venv\Scripts\pip.exe install pymupdf
   ```
3. 重新启动 `start.bat`

---

**Q: 安装依赖非常慢 / 下载超时**

国内网络访问 PyPI 可能较慢。

解决：使用国内镜像源。在 PowerShell 中运行：
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

---

### 启动相关

---

**Q: 启动后浏览器没有自动打开**

手动打开浏览器，输入 **http://127.0.0.1:7860** 回车即可。

---

**Q: 页面顶部显示 `DeepSeek API: Missing`**

`.env` 文件未正确配置。

检查：
1. 确认 `.env` 文件存在于 `deep-reading-agent` 文件夹中（和 `app.py` 同一级）
2. 用记事本打开 `.env`，检查内容格式

正确格式：
```
DEEPSEEK_API_KEY=sk-abc123def456
```

常见错误：
```
DEEPSEEK_API_KEY = sk-abc123def456     ← 等号周围不要有空格
DEEPSEEK_API_KEY="sk-abc123def456"     ← 值不要加引号
# DEEPSEEK_API_KEY=sk-abc123def456     ← 行首不要有 # 号（# 表示注释）
```

---

**Q: 端口 7860 被占用**

你可能已经运行了一个实例，或者其他程序占用了这个端口。

解决：
1. 关闭之前的 `start.bat` 窗口
2. 如果端口仍被占用，用记事本打开 `app.py`，找到最后几行：
   ```python
   app.launch(server_name="127.0.0.1", server_port=7860, ...)
   ```
   把 `7860` 改为其他数字（如 `7861`），保存后重新启动

---

### 使用相关

---

**Q: 提取阶段报 `ConnectionError` 或 `TimeoutError`**

PaddleOCR 远程 API 不可达。

解决：
- 检查 `.env` 中 `PADDLEOCR_REMOTE_URL` 是否正确
- 如果不需要 PaddleOCR，在 Tab 2/3 中选择 **"Legacy (pdfplumber)"** 提取方式

---

**Q: 分析过程中报错 "API 余额不足" 或 "Authentication failed"**

DeepSeek API 密钥过期或余额不足。

解决：
1. 登录 https://platform.deepseek.com/
2. 检查账户余额
3. 如果余额为 0，需要充值
4. 如果密钥失效，重新生成一个新密钥，更新 `.env` 文件

---

**Q: 点了「停止」按钮但进程没有马上停下来**

取消机制在**阶段之间**生效。当前阶段的 AI 调用需要等它返回后才能停止。

`deepseek-reasoner` 模型单次调用可能耗时 1-3 分钟。如果需要立即停止，在命令行窗口按 `Ctrl + C`。

---

**Q: PDF 提取结果为空白或乱码**

- 如果是**扫描件 PDF**（图片型而非文字型），必须使用 PaddleOCR，pdfplumber 无法处理
- 如果使用 PaddleOCR 仍有问题，试试在 Tab 4 中勾选 **"方向矫正"**
- 某些加密或权限受限的 PDF 无法提取

---

**Q: 批量处理中断后如何恢复？**

1. 确保 **"跳过已处理"** 已勾选（默认开启）
2. 直接重新点击 **"开始批量精读"** 即可
3. 系统通过 `processed_papers.json` 文件记录已完成的论文（基于 MD5 哈希），会自动跳过已处理的文件
4. 如需强制全部重新处理，删除 `deep-reading-agent` 文件夹下的 `processed_papers.json` 文件

---

**Q: 最终报告中标题、作者、期刊显示为 "Unknown"**

这说明元数据提取不完整。

改善方法：
1. 配置 `QWEN_API_KEY`（通义千问视觉 API），它能从 PDF 页面截图中精确识别这些信息
2. 不配置 Qwen 时，系统会尝试从文本中自动提取，但对某些排版格式支持有限
3. 你也可以手动编辑生成的 `.md` 文件，修改 YAML 头部中的 `title`、`authors`、`journal`、`year` 字段

---

### 其他

---

**Q: 想让局域网内其他设备访问**

用记事本打开 `app.py`，修改最后几行：

```python
app.launch(server_name="0.0.0.0", server_port=7860, ...)
```

保存后重启，然后用 `http://你电脑的IP:7860` 访问。

---

**Q: 程序占用了多少磁盘空间？**

- `venv/` 虚拟环境：约 500MB - 1GB
- 每篇论文的分析结果：约 200KB - 2MB
- 程序本身：约 1MB

---

**Q: 如何完全卸载？**

直接删除 `deep-reading-agent` 文件夹即可。程序不会在其他地方写入数据。如果之前安装了 Python 且不再需要，也可以卸载 Python。

---

> 如果遇到本教程未覆盖的问题，请查看 `README_GUI.md` 获取更多技术细节，
> 或在 GitHub 仓库提交 Issue：https://github.com/lxjthu/deep-reading-agent/issues
