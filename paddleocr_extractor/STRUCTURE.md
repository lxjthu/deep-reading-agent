# 目录结构说明

```
paddleocr_extractor/                # 模块根目录
│
├── __init__.py                     # 模块入口，导出主要类
├── extractor.py                    # 核心提取器实现
├── cli.py                          # 命令行工具
├── setup.py                        # pip 安装配置
│
├── README.md                       # 主要文档（功能介绍）
├── QUICKSTART.md                   # 快速开始指南
├── API.md                          # API 详细文档
├── DEEPSEEK_INTEGRATION.md         # 与 DeepSeek 集成指南
├── STRUCTURE.md                    # 本文档
│
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
│
└── example_*.py                    # 使用示例
    ├── example_basic.py            # 基础用法
    ├── example_batch.py            # 批量处理
    └── example_integration.py      # 与其他代码集成
```

## 核心文件说明

### extractor.py
- **PaddleOCRPDFExtractor** 类的主实现
- 包含 `_call_api()`、`_download_images()` 等内部方法
- 处理 PDF 提取、图片下载、Markdown 生成的完整流程

### __init__.py
- 模块入口点
- 导出 `PaddleOCRPDFExtractor` 类和便捷函数
- 自动加载 `.env` 文件

### cli.py
- 命令行接口
- 支持 `python cli.py 论文.pdf` 直接运行
- 支持批量处理和进度显示

## 文档文件说明

| 文档 | 阅读场景 | 内容 |
|------|----------|------|
| README.md | 第一次使用 | 功能概述、安装、快速开始 |
| QUICKSTART.md | 想快速上手 | 5分钟教程、常见问题 |
| API.md | 开发集成 | 详细的 API 参考 |
| DEEPSEEK_INTEGRATION.md | 对接 DeepSeek | 集成方案、完整示例 |
| STRUCTURE.md | 了解项目 | 目录结构、文件说明 |

## 使用流程

### 作为独立模块使用

```
1. 复制 paddleocr_extractor/ 到你的项目
2. pip install requests python-dotenv
3. 创建 .env 文件配置 API 凭证
4. from paddleocr_extractor import PaddleOCRPDFExtractor
```

### 作为 pip 包安装

```
1. cd paddleocr_extractor
2. pip install -e .
3. paddleocr-extract 论文.pdf
```

### 与其他项目集成

```
1. 复制 paddleocr_extractor/ 到目标项目
2. 参考 example_integration.py 编写对接代码
3. 根据需要修改提取逻辑
```

## 扩展开发

### 添加新的提取模式

```python
# 在 extractor.py 中添加
class PaddleOCRPDFExtractor:
    def __init__(self, ...):
        # 添加新参数
        self.new_mode = new_mode
    
    def extract_with_new_mode(self, pdf_path):
        # 实现新的提取逻辑
        pass
```

### 自定义后处理

```python
# 继承并扩展
class MyExtractor(PaddleOCRPDFExtractor):
    def post_process(self, content):
        # 自定义后处理
        content = self.remove_watermark(content)
        content = self.fix_tables(content)
        return content
```

## 最小化使用

如果只需要核心功能，最少需要这些文件：

```
paddleocr_extractor/
├── __init__.py      # 必须
├── extractor.py     # 必须
└── requirements.txt # pip install 用
```

使用示例：

```python
from paddleocr_extractor.extractor import PaddleOCRPDFExtractor

extractor = PaddleOCRPDFExtractor(
    remote_url="https://...",
    remote_token="..."
)
result = extractor.extract_pdf("论文.pdf")
```
