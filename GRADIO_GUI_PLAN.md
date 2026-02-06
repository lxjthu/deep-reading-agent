# Gradio GUI 实现方案

## 产出物

单文件 `app.py`，放在项目根目录。启动方式：

```powershell
.\venv\Scripts\python.exe app.py
# 浏览器打开 http://127.0.0.1:7860
```

## 依赖

`requirements.txt` 末尾追加 `gradio`，然后 `pip install gradio`。

---

## 界面结构（3 个 Tab）

### Tab 1: PDF 提取

直接调用 `paddleocr_pipeline.extract_with_fallback()`，不走 subprocess。

| 左栏（参数） | 右栏（结果） |
|---|---|
| `gr.File` 上传 PDF | 提取日志 `gr.Textbox` |
| 输出目录 `gr.Textbox` (默认 paddleocr_md) | Markdown 预览 `gr.Markdown` |
| 表格识别 `Checkbox(True)` | 元数据 `gr.JSON` |
| 公式识别 `Checkbox(True)` | 下载文件 `gr.File` |
| 图表解析 `Checkbox(False)` | |
| 方向矫正 `Checkbox(False)` | |
| 下载图片 `Checkbox(False)` | |
| 每批页数 `Slider(5-50, 默认10)` | |
| 禁用回退 `Checkbox(False)` | |
| 强制 pdfplumber `Checkbox(False)` | |
| [开始提取] 按钮 | |

### Tab 2: 全流程精读

6 阶段流水线，前 3 阶段直接 import，后 3 阶段 subprocess。

| 左栏 | 右栏 |
|---|---|
| `gr.File` 上传 PDF | 当前步骤 `gr.Textbox` |
| 提取方式 `Radio(PaddleOCR/Legacy)` | 运行日志 `gr.Textbox(lines=15)` |
| [开始精读] 按钮 | 最终报告预览 `gr.Markdown` |
| [停止] 按钮 | 下载结果 `gr.File` |

6 阶段：
1. **提取** — `paddleocr_pipeline.extract_with_fallback()` 或 `extract_pdf_legacy()`
2. **分段** — `paddleocr_segment` 模块的分段函数
3. **深度阅读** — 直接 import `deep_read_pipeline` 中的 step_1~step_7 模块逐步调用
4. **补充检查** — subprocess 调用 `run_supplemental_reading.py`
5. **Dataview 摘要** — subprocess 调用 `inject_dataview_summaries.py`
6. **元数据注入** — subprocess 调用 `inject_obsidian_meta.py`

### Tab 3: 批量处理

直接 import `SmartScholar` 和 `StateManager`，在 Python 层循环处理。

| 左栏 | 右栏 |
|---|---|
| 文件夹路径 `gr.Textbox` | 进度表 `gr.Dataframe` (文件名/类型/状态/耗时) |
| [验证路径] 按钮 | 当前日志 `gr.Textbox` |
| 文件夹状态 `gr.Textbox` | 总体进度 `gr.Textbox` |
| 跳过已处理 `Checkbox(True)` | |
| [开始批量] 按钮 | |

---

## 核心技术方案

### 日志实时流

后台线程执行任务，日志通过 `queue.Queue` 传回 Gradio generator：

```python
class QueueHandler(logging.Handler):
    """日志 → 队列"""
    def emit(self, record):
        self.queue.put(self.format(record))

class TeeWriter:
    """捕获 print() 输出"""
    def write(self, s):
        if s.strip():
            self.queue.put(s.strip())
```

Gradio generator 每 0.5s 检查队列，`yield` 更新 UI。

### 长任务不阻塞 UI

核心模式：工作线程 + generator 轮询：

```python
def run_extraction(...):
    result = {}
    def worker():
        with capture_output(log_queue):
            result['data'] = extract_with_fallback(...)
        log_queue.put("__DONE__")

    threading.Thread(target=worker).start()
    while True:
        msg = log_queue.get(timeout=0.5)
        if msg == "__DONE__": break
        yield (log_text, "", None)
    yield (log_text, preview, file_path)
```

### 文件处理

Gradio 上传的文件在临时目录，需复制到 `_gui_uploads/` 稳定路径：

```python
work_dir = os.path.join(BASE_DIR, "_gui_uploads")
shutil.copy2(uploaded_file, os.path.join(work_dir, basename))
```

### 取消机制

`threading.Event` 作为取消标志，每个阶段间检查。

---

## 实现步骤

| 步骤 | 内容 |
|------|------|
| 0 | `pip install gradio`，更新 `requirements.txt` |
| 1 | 创建 `app.py` 骨架：imports、路径设置、三个 Tab 空壳、启动代码 |
| 2 | 实现日志捕获工具（QueueHandler + TeeWriter + capture_output） |
| 3 | 实现 Tab 1 后端 + UI 绑定，用真实 PDF 测试 |
| 4 | 实现 Tab 2 后端（6 阶段 generator），绑定 UI |
| 5 | 实现 Tab 3 后端（验证路径 + 批量 generator），绑定 UI |
| 6 | 顶部增加 `.env` 状态指示（DeepSeek/PaddleOCR 是否配置） |

## 涉及文件

| 文件 | 操作 |
|------|------|
| `app.py` | **新建** — Gradio GUI 主文件 |
| `requirements.txt` | **修改** — 追加 `gradio` |
| `.gitignore` | **修改** — 追加 `_gui_uploads/` |

## 验证方式

1. `python app.py` 启动，浏览器打开 `http://127.0.0.1:7860`
2. Tab 1：上传一个 PDF，点击提取，观察日志流和 Markdown 预览
3. Tab 2：上传 PDF，选择 PaddleOCR，点击精读，观察 6 阶段进度
4. Tab 3：输入 `E:\pdf\002`，验证路径，点击批量处理，观察进度表
