# 模块清单

PaddleOCR PDF Extractor - 独立模块完整文件清单

## 文件列表

### 核心代码文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `__init__.py` | 0.6 KB | 模块入口，导出主类 |
| `extractor.py` | 11.4 KB | 核心提取器实现 |
| `cli.py` | 3.9 KB | 命令行工具 |
| `setup.py` | 1.6 KB | pip 安装配置 |

### 文档文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `README.md` | 6.5 KB | 主文档（功能介绍、安装、使用） |
| `QUICKSTART.md` | 2.5 KB | 5分钟快速开始 |
| `API.md` | 6.8 KB | API 详细参考 |
| `DEEPSEEK_INTEGRATION.md` | 9.2 KB | 与 DeepSeek 集成指南 |
| `STRUCTURE.md` | 3.5 KB | 目录结构说明 |
| `MANIFEST.md` | - | 本文件（清单） |

### 示例代码

| 文件 | 大小 | 说明 |
|------|------|------|
| `example_basic.py` | 1.6 KB | 基础用法示例 |
| `example_batch.py` | 2.4 KB | 批量处理示例 |
| `example_integration.py` | 6.1 KB | 与其他代码集成示例 |

### 配置文件

| 文件 | 大小 | 说明 |
|------|------|------|
| `requirements.txt` | 0.1 KB | Python 依赖 |
| `.env.example` | 0.3 KB | 环境变量模板 |

**总计：14 个文件，约 60 KB**

## 快速部署

### 方式一：最小化部署（仅需 4 个文件）

```bash
mkdir paddleocr_extractor
cd paddleocr_extractor

# 创建 __init__.py
# 创建 extractor.py
# 创建 requirements.txt
# 创建 .env (从 .env.example 复制)

pip install requests python-dotenv
```

### 方式二：完整部署（推荐）

```bash
# 复制整个 paddleocr_extractor/ 目录
pip install -r paddleocr_extractor/requirements.txt

# 配置环境变量
cp paddleocr_extractor/.env.example .env
# 编辑 .env 填入你的 API 凭证
```

### 方式三：pip 安装

```bash
cd paddleocr_extractor
pip install -e .

# 使用命令行工具
paddleocr-extract 论文.pdf
```

## 使用路径

### 路径 1：作为库使用（最常用）

```python
from paddleocr_extractor import PaddleOCRPDFExtractor

extractor = PaddleOCRPDFExtractor()
result = extractor.extract_pdf("论文.pdf")
```

阅读：
1. `QUICKSTART.md` - 快速上手
2. `API.md` - 查看所有接口
3. `example_basic.py` - 参考示例

### 路径 2：与 DeepSeek 集成

阅读：
1. `DEEPSEEK_INTEGRATION.md` - 完整集成指南
2. `example_integration.py` - 代码示例

### 路径 3：批量处理

```bash
python cli.py papers/*.pdf --batch
```

阅读：
1. `example_batch.py` - 批量处理代码
2. `cli.py` - 命令行用法

### 路径 4：二次开发

阅读：
1. `STRUCTURE.md` - 了解代码结构
2. `extractor.py` - 查看实现细节
3. `API.md` - 了解扩展接口

## 依赖关系图

```
用户代码
    │
    ├──▶ __init__.py ──▶ extractor.py
    │                         │
    │                         ├──▶ requests (HTTP)
    │                         └──▶ python-dotenv (环境变量)
    │
    └──▶ cli.py (命令行入口)
```

## 更新日志

### v1.0.0 (2026-02-02)
- 初始版本
- 支持远程 Layout Parsing API
- 自动过滤公式/表格截图
- 完整的文档和示例

## 许可

MIT License - 可自由使用、修改、分发
