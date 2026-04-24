#!/usr/bin/env python3
"""
Deep Reading Agent v3 - KIMI Edition
暗琥珀主题 + 长文本精读 + 七步/四步精读
"""

import os
import sys
import io
import logging
import queue
import shutil
import subprocess
import threading
import time
import json
import re as _re
from datetime import datetime
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "_gui_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Gradio Theme - KIMI Dark Amber
# ---------------------------------------------------------------------------
KIMI_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.emerald,
    secondary_hue=gr.themes.colors.teal,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
).set(
    button_primary_background_fill="linear-gradient(135deg, #059669, #10b981)",
    button_primary_background_fill_hover="linear-gradient(135deg, #10b981, #34d399)",
    button_primary_text_color="white",
    button_primary_border_color="transparent",
    slider_color="#10b981",
    loader_color="#10b981",
)

# ---------------------------------------------------------------------------
# Extra CSS - 补充样式
# ---------------------------------------------------------------------------
EXTRA_CSS = """
/* 隐藏 footer */
footer { display: none !important; }

/* Emoji 图标 - 使用 Unicode 符号替代 */
.icon-upload::before { content: "↗"; }
.icon-target::before { content: "★"; }
.icon-chat::before { content: "✉"; }
.icon-chart::before { content: "■"; }
.icon-edit::before { content: "✎"; }
.icon-download::before { content: "↓"; }
.icon-folder::before { content: "□"; }
.icon-pencil::before { content: "✏"; }
.icon-crystal::before { content: "◉"; }
.icon-ruler::before { content: "△"; }
.icon-gear::before { content: "⚙"; }
.icon-rocket::before { content: "➤"; }
.icon-filter::before { content: "□"; }

/* 隐藏 no-label 组件的默认标签 */
.no-label fieldset.block > span:first-child,
.no-label .block > span:first-child {
  display: none !important;
}

/* 按钮 */
.btn-kimi {
  background: linear-gradient(135deg, #059669, #10b981) !important;
  color: white !important;
  border: none !important;
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.25) !important;
  font-weight: 600 !important;
  padding: 12px 24px !important;
  border-radius: 8px !important;
  transition: all 0.2s ease !important;
}

.btn-kimi:hover {
  background: linear-gradient(135deg, #10b981, #34d399) !important;
  box-shadow: 0 6px 20px rgba(16, 185, 129, 0.35) !important;
  transform: translateY(-1px);
}

.btn-kimi-danger {
  background: #fef2f2 !important;
  color: #dc2626 !important;
  border: 1px solid #fecaca !important;
  border-radius: 8px !important;
  padding: 12px 24px !important;
  font-weight: 600 !important;
  transition: all 0.2s ease !important;
}

.btn-kimi-danger:hover {
  background: #fee2e2 !important;
  transform: translateY(-1px);
}

/* Header */
.kimi-header {
  position: relative;
  overflow: hidden;
  padding-top: 3px;
}

.kimi-header::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #059669, #10b981, #059669);
}

/* 卡片 */
.kimi-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  margin-bottom: 16px;
}

/* 标题 */
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 上传区域 */
.upload-hint {
  font-size: 12px;
  color: #6b7280;
  text-align: center;
  margin-top: 8px;
}

/* 日志框 */
.log-box {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 12px !important;
  line-height: 1.6 !important;
  white-space: pre-wrap !important;
  background: #f9fafb !important;
  border: 1px solid #e5e7eb !important;
  border-radius: 8px !important;
  padding: 12px 16px !important;
}

/* Markdown 预览 */
.md-preview {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  max-height: 600px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.8;
}

.md-preview h1 { color: #059669 !important; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
.md-preview h2 { color: #1f2937 !important; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }
.md-preview h3 { color: #10b981 !important; }
.md-preview code { color: #059669 !important; background: #f0fdf4 !important; padding: 2px 6px !important; border-radius: 4px !important; }
.md-preview pre { background: #f9fafb !important; border: 1px solid #e5e7eb !important; padding: 14px !important; border-radius: 8px !important; }
.md-preview blockquote { border-left: 3px solid #059669 !important; background: #f0fdf4 !important; padding: 10px 16px !important; }
.md-preview th { color: #059669 !important; background: #f0fdf4 !important; }
.md-preview td { border-bottom: 1px solid #e5e7eb !important; }

/* Prompt 编辑器 */
.prompt-box {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 13px !important;
  line-height: 1.7 !important;
}

/* 维度标签 */
.dim-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  background: #ecfdf5;
  color: #059669;
  border: 1px solid #a7f3d0;
}

/* 滚动条 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #9ca3af; }
"""

# ---------------------------------------------------------------------------
# Env status
# ---------------------------------------------------------------------------

def _env_status():
    parts = []
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")
    parts.append(f"DeepSeek API: {'✓' if ds_key else '✗'}")
    return " | ".join(parts)

# ---------------------------------------------------------------------------
# Log capture (保留)
# ---------------------------------------------------------------------------

class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            pass

class TeeWriter:
    def __init__(self, log_queue: queue.Queue, original):
        self.log_queue = log_queue
        self.original = original
    def write(self, s):
        if s and s.strip():
            self.log_queue.put(s.strip())
        if self.original:
            self.original.write(s)
    def flush(self):
        if self.original:
            self.original.flush()

class OutputCapture:
    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._handler = None
        self._tee = None
        self._orig_stdout = None
    def __enter__(self):
        self._handler = QueueHandler(self.log_queue)
        self._handler.setLevel(logging.DEBUG)
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self._handler)
        self._orig_stdout = sys.stdout
        self._tee = TeeWriter(self.log_queue, self._orig_stdout)
        sys.stdout = self._tee
        return self
    def __exit__(self, *exc):
        sys.stdout = self._orig_stdout
        logging.getLogger().removeHandler(self._handler)

def _drain_queue(log_queue: queue.Queue, log_lines: list, max_lines: int = 300):
    while True:
        try:
            msg = log_queue.get_nowait()
            if msg == "__DONE__":
                return True
            log_lines.append(msg)
            if len(log_lines) > max_lines:
                log_lines[:] = log_lines[-max_lines:]
        except queue.Empty:
            return False

def _stable_copy(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    src = uploaded_file if isinstance(uploaded_file, str) else uploaded_file.name
    basename = os.path.basename(src)
    dst = os.path.join(UPLOAD_DIR, basename)
    if os.path.abspath(src) == os.path.abspath(dst):
        return dst
    shutil.copy2(src, dst)
    return dst

_cancel_event = threading.Event()

def _request_cancel():
    _cancel_event.set()
    return "已请求取消..."

def _check_cancel():
    if _cancel_event.is_set():
        raise InterruptedError("用户取消")

# ---------------------------------------------------------------------------
# Prompt management
# ---------------------------------------------------------------------------

QUANT_PROMPT_DIR = os.path.join(BASE_DIR, "prompts", "quant_analysis")
QUAL_PROMPT_DIR = os.path.join(BASE_DIR, "prompts", "qual_analysis")

QUANT_STEPS = [
    ("step_1_overview", "全景扫描", "📊"),
    ("step_2_theory", "理论与假说", "📚"),
    ("step_3_data", "数据考古", "🔍"),
    ("step_4_vars", "变量与测量", "📏"),
    ("step_5_identification", "识别策略", "🎯"),
    ("step_6_results", "结果解读", "📈"),
    ("step_7_critique", "专家批判", "⚡"),
]

QUAL_STEPS = [
    ("L1_Context", "背景层", "🌐"),
    ("L2_Theory", "理论层", "🏛️"),
    ("L3_Logic", "逻辑层", "🔗"),
    ("L4_Value", "价值层", "💎"),
]

ANALYSIS_DIMS = [
    ("overview", "核心贡献识别", "识别论文核心贡献、创新性和局限性"),
    ("theory", "理论框架评估", "评估理论来源、适用性和缺口"),
    ("methodology", "方法论批判", "批判研究方法、因果推断和偏差"),
    ("results", "实证结果解读", "解读数据、显著性和效应大小"),
    ("limitations", "局限性分析", "分析作者自述和额外局限"),
    ("implications", "实践意义", "提炼对领域、政策和实践的启示"),
    ("comparison", "跨文献对比", "与相关工作对比增量贡献"),
    ("future", "未来方向", "提出可执行的新选题方向"),
]

def _load_prompt_file(step_name: str, prompt_type: str) -> str:
    prompt_dir = QUANT_PROMPT_DIR if prompt_type == "quant" else QUAL_PROMPT_DIR
    file_path = os.path.join(prompt_dir, f"{step_name}.md")
    if not os.path.exists(file_path):
        return ""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def _save_prompt_file(step_name: str, prompt_type: str, content: str) -> str:
    prompt_dir = QUANT_PROMPT_DIR if prompt_type == "quant" else QUAL_PROMPT_DIR
    os.makedirs(prompt_dir, exist_ok=True)
    file_path = os.path.join(prompt_dir, f"{step_name}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✓ 已保存 {step_name}.md"

# ---------------------------------------------------------------------------
# Backend: Long Context Pipeline (新架构)
# ---------------------------------------------------------------------------

def run_long_context(pdf_file, selected_dims, custom_question, progress=gr.Progress()):
    """长文本精读 - 使用 ConversationEngine"""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    result = {}

    pdf_path = _stable_copy(pdf_file)
    if not pdf_path:
        yield {"logs": "请先上传 PDF", "stage": "等待上传", "progress": 0, "preview": "", "turns": [], "download": None}
        return

    def worker():
        try:
            with OutputCapture(log_q):
                log_q.put("[阶段 1/3] 提取 PDF...")
                progress(0.1, desc="提取 PDF")
                _check_cancel()

                from paddleocr_pipeline import extract_with_fallback
                paddleocr_md_dir = os.path.join(BASE_DIR, "paddleocr_md")
                os.makedirs(paddleocr_md_dir, exist_ok=True)
                md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir)
                
                with open(md_path, "r", encoding="utf-8") as f:
                    full_text = f.read()
                
                log_q.put(f"✓ 提取完成: {len(full_text)} 字符")

                # 导入新架构
                log_q.put("[阶段 2/3] 初始化长文本引擎...")
                progress(0.2, desc="初始化引擎")
                sys.path.insert(0, os.path.join(BASE_DIR, "new_architecture"))
                from new_architecture.config import Config
                from new_architecture.paper_cache import PaperCache, PaperMetadata
                from new_architecture.conversation_engine import ConversationEngine
                
                config = Config.from_env()
                paper_meta = PaperMetadata(
                    title=os.path.splitext(os.path.basename(pdf_path))[0],
                    authors=[],
                    source="PDF",
                )
                cache = PaperCache(full_text, paper_meta)
                engine = ConversationEngine(config, cache, max_history_turns=2)
                
                log_q.put("✓ 引擎就绪")

                # 执行选中的维度
                log_q.put("[阶段 3/3] 执行分析...")
                from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS
                
                turns_data = []
                # 名称 → key 映射
                _name_to_key = {d[1]: d[0] for d in ANALYSIS_DIMS}
                dim_list = [_name_to_key.get(d, d) for d in selected_dims] if selected_dims else list(ANALYSIS_DIMENSIONS.keys())
                
                for i, dim_key in enumerate(dim_list):
                    _check_cancel()
                    progress(0.2 + 0.7 * (i + 1) / len(dim_list), desc=f"分析: {dim_key}")
                    
                    dim_info = ANALYSIS_DIMENSIONS.get(dim_key, {})
                    questions = dim_info.get("default_questions", [f"请分析论文的{dim_info.get('name', dim_key)}"])
                    
                    for q in questions[:2]:  # 每个维度最多2个问题
                        log_q.put(f"  ▶ {dim_info.get('name', dim_key)}: {q[:60]}...")
                        answer = engine.ask(q, dimension=dim_key)
                        
                        # 获取token信息
                        last_turn = engine.results[-1] if engine.results else None
                        tokens_info = ""
                        if last_turn:
                            tokens_info = f"{last_turn.prompt_tokens}t / {last_turn.completion_tokens}t"
                        
                        turns_data.append({
                            "dimension": dim_info.get("name", dim_key),
                            "question": q,
                            "answer": answer,
                            "tokens": tokens_info,
                        })
                        log_q.put(f"    ✓ 完成 ({tokens_info})")

                # 合成报告
                log_q.put("正在合成最终报告...")
                report_path = os.path.join(BASE_DIR, "deep_reading_results", 
                                           f"long_context_{paper_meta.title}.md")
                os.makedirs(os.path.dirname(report_path), exist_ok=True)
                
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(f"# 长文本精读报告: {paper_meta.title}\n\n")
                    f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                    f.write(f"> 分析维度: {len(dim_list)} 个\n")
                    f.write(f"> 论文长度: {len(full_text)} 字符\n\n")
                    f.write("---\n\n")
                    
                    for turn in turns_data:
                        f.write(f"## {turn['dimension']}\n\n")
                        f.write(f"**Q**: {turn['question']}\n\n")
                        f.write(f"{turn['answer']}\n\n")
                        f.write(f"*Tokens: {turn['tokens']}*\n\n")
                        f.write("---\n\n")
                
                result["report"] = report_path
                result["turns"] = turns_data
                log_q.put("✅ 全部完成！")
                progress(1.0, desc="完成")

        except InterruptedError:
            log_q.put("⚠ 用户取消了流水线")
            result["cancelled"] = True
        except Exception as e:
            log_q.put(f"❌ 错误: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        
        stage = "处理中..."
        for line in reversed(log_lines):
            if line.startswith("[") or line.startswith("▶") or line.startswith("✓"):
                stage = line
                break

        progress_val = 0
        if "提取" in log_text:
            progress_val = 10
        if "初始化" in log_text:
            progress_val = 20
        if "分析:" in log_text:
            progress_val = 20 + min(70, log_text.count("▶") * 10)
        if "✅" in log_text:
            progress_val = 100

        # 构建turns markdown
        turns_md = ""
        for i, turn in enumerate(result.get("turns", [])):
            turns_md += f"\n### {turn['dimension']}\n\n"
            turns_md += f"**Q**: {turn['question']}\n\n"
            turns_md += turn['answer'][:2000] + ("\n\n..." if len(turn['answer']) > 2000 else "")
            turns_md += f"\n\n*{turn['tokens']}*\n\n---\n"

        yield {
            "logs": log_text,
            "stage": stage,
            "progress": progress_val,
            "preview": turns_md,
            "turns": result.get("turns", []),
            "download": result.get("report") if result.get("report") and os.path.exists(result["report"]) else None,
        }

        if done:
            break
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Backend: Classic Pipeline (七步精读 - 新架构改造)
# ---------------------------------------------------------------------------

STEP_PROMPTS = [
    ("step_1_overview", "研究概览", "1/7"),
    ("step_2_theory", "理论框架", "2/7"),
    ("step_3_data", "数据与样本", "3/7"),
    ("step_4_vars", "变量定义", "4/7"),
    ("step_5_identification", "识别策略", "5/7"),
    ("step_6_results", "实证结果", "6/7"),
    ("step_7_critique", "批判性评价", "7/7"),
]

def run_deep_reading(pdf_file, extraction_method, progress=gr.Progress()):
    """七步精读 - 使用 ConversationEngine 新架构"""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    result = {}

    pdf_path = _stable_copy(pdf_file)
    if not pdf_path:
        yield {"logs": "未提供 PDF", "stage": "错误", "progress": 0, "preview": "", "download": None}
        return

    basename = os.path.splitext(os.path.basename(pdf_path))[0]

    def worker():
        try:
            with OutputCapture(log_q):
                log_q.put("[阶段 1/3] 提取 PDF...")
                progress(0.1, desc="提取 PDF")
                _check_cancel()

                from paddleocr_pipeline import extract_with_fallback, extract_pdf_legacy
                paddleocr_md_dir = os.path.join(BASE_DIR, "paddleocr_md")
                os.makedirs(paddleocr_md_dir, exist_ok=True)

                if extraction_method == "PaddleOCR (本地GPU)":
                    md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir, force_local=True)
                elif extraction_method == "Legacy (pdfplumber)":
                    md_path, metadata = extract_pdf_legacy(pdf_path, out_dir=paddleocr_md_dir)
                else:
                    md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir)

                result["source_md"] = md_path
                log_q.put(f"✓ 提取完成: {os.path.basename(md_path)}")

                with open(md_path, "r", encoding="utf-8") as f:
                    full_text = f.read()

                log_q.put("[阶段 2/3] 初始化长文本引擎...")
                progress(0.2, desc="初始化引擎")
                _check_cancel()

                sys.path.insert(0, os.path.join(BASE_DIR, "new_architecture"))
                from new_architecture.config import Config
                from new_architecture.paper_cache import PaperCache, PaperMetadata
                from new_architecture.conversation_engine import ConversationEngine

                config = Config.from_env()
                paper_meta = PaperMetadata(
                    title=basename,
                    authors=[],
                    source="PDF",
                )
                cache = PaperCache(full_text, paper_meta)
                engine = ConversationEngine(config, cache, max_history_turns=2)
                log_q.put("✓ 引擎就绪 (论文全文已缓存)")

                log_q.put("[阶段 3/3] 七步深度阅读...")
                paper_output_dir = os.path.join(BASE_DIR, "deep_reading_results", basename)
                os.makedirs(paper_output_dir, exist_ok=True)
                result["output_dir"] = paper_output_dir

                # 加载并执行7步提示词
                step_results = []
                for i, (prompt_file, step_name, step_label) in enumerate(STEP_PROMPTS):
                    _check_cancel()
                    progress(0.2 + 0.6 * (i + 1) / len(STEP_PROMPTS), desc=f"步骤 {step_label}: {step_name}")
                    log_q.put(f"  步骤 {step_label}: {step_name}...")

                    prompt_path = os.path.join(QUANT_PROMPT_DIR, f"{prompt_file}.md")
                    if not os.path.exists(prompt_path):
                        log_q.put(f"  ⚠ 未找到提示词: {prompt_path}")
                        continue

                    with open(prompt_path, "r", encoding="utf-8") as f:
                        prompt_text = f.read()

                    # 在提示词前添加步骤标记，帮助模型定位
                    full_prompt = f"【步骤 {step_label}: {step_name}】\n\n{prompt_text}"
                    answer = engine.ask(full_prompt, dimension=step_name)

                    # 获取 token 信息
                    last_turn = engine.results[-1] if engine.results else None
                    tokens_info = ""
                    if last_turn:
                        tokens_info = f"{last_turn.prompt_tokens}t / {last_turn.completion_tokens}t"

                    # 保存单步结果
                    step_md_path = os.path.join(paper_output_dir, f"{i+1}_{step_name.replace(' ', '_')}.md")
                    with open(step_md_path, "w", encoding="utf-8") as f:
                        f.write(f"# 步骤 {step_label}: {step_name}\n\n")
                        f.write(f"> Token: {tokens_info}\n\n")
                        f.write(answer)

                    step_results.append({
                        "step": step_label,
                        "name": step_name,
                        "file": step_md_path,
                        "tokens": tokens_info,
                        "answer": answer,
                    })
                    log_q.put(f"    ✓ 完成 ({tokens_info})")

                # 合成最终报告
                log_q.put("正在合成最终报告...")
                final_report_path = os.path.join(paper_output_dir, "Final_Deep_Reading_Report.md")
                with open(final_report_path, "w", encoding="utf-8") as f:
                    f.write(f"# 深度阅读报告: {basename}\n\n")
                    f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                    f.write(f"> 论文长度: {len(full_text)} 字符\n")
                    f.write(f"> 分析步骤: 7 步\n")
                    f.write(f"> 缓存命中: ConversationEngine (自动)\n\n")
                    f.write("---\n\n")

                    for sr in step_results:
                        f.write(f"## {sr['step']}: {sr['name']}\n\n")
                        f.write(f"*Token: {sr['tokens']}*\n\n")
                        f.write(sr["answer"])
                        f.write("\n\n---\n\n")

                result["final_report"] = final_report_path
                log_q.put("✓ 深度阅读完成")

                # 保存元数据
                meta_path = os.path.join(paper_output_dir, "meta.json")
                import json
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "title": basename,
                        "source_pdf": pdf_path,
                        "source_md": md_path,
                        "generation_time": datetime.now().isoformat(),
                        "steps": [{"step": s["step"], "name": s["name"], "tokens": s["tokens"]} for s in step_results],
                    }, f, ensure_ascii=False, indent=2)
                log_q.put(f"✓ 元数据已保存: {meta_path}")

                progress(1.0, desc="完成")
                log_q.put("✅ 全部处理完成！")

        except InterruptedError:
            log_q.put("⚠ 用户取消了流水线")
            result["cancelled"] = True
        except Exception as e:
            log_q.put(f"❌ 错误: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        stage = ""
        for line in reversed(log_lines):
            if line.startswith("[") or line.startswith("✓") or line.startswith("⚠"):
                stage = line
                break

        progress_val = 0
        if "提取" in log_text: progress_val = 10
        if "引擎" in log_text: progress_val = 20
        if "步骤" in log_text:
            progress_val = 20 + min(60, log_text.count("步骤") * 9)
        if "合成" in log_text: progress_val = 90
        if "✅" in log_text: progress_val = 100

        preview = ""
        final_report = result.get("final_report", "")
        if final_report and os.path.exists(final_report):
            with open(final_report, "r", encoding="utf-8") as f:
                preview = f.read(8000)
            if len(preview) >= 8000:
                preview += "\n\n...（内容较长，请下载查看完整报告）..."

        yield {
            "logs": log_text,
            "stage": stage or "处理中...",
            "progress": progress_val,
            "preview": preview,
            "download": final_report if final_report and os.path.exists(final_report) else None,
        }

        if done:
            break
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Backend: Qual Analysis Pipeline (四步精读 - 新架构)
# ---------------------------------------------------------------------------

QUAL_PROMPTS = [
    ("L1_Context_Prompt", "背景层", "1/4"),
    ("L2_Theory_Prompt", "理论层", "2/4"),
    ("L3_Logic_Prompt", "逻辑层", "3/4"),
    ("L4_Value_Prompt", "价值层", "4/4"),
]

def run_qual_analysis(pdf_file, extraction_method, progress=gr.Progress()):
    """四步精读 - 使用 ConversationEngine 新架构"""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    result = {}

    pdf_path = _stable_copy(pdf_file)
    if not pdf_path:
        yield {"logs": "未提供 PDF", "stage": "错误", "progress": 0, "preview": "", "download": None}
        return

    basename = os.path.splitext(os.path.basename(pdf_path))[0]

    def worker():
        try:
            with OutputCapture(log_q):
                log_q.put("[阶段 1/3] 提取 PDF...")
                progress(0.1, desc="提取 PDF")
                _check_cancel()

                from paddleocr_pipeline import extract_with_fallback, extract_pdf_legacy
                paddleocr_md_dir = os.path.join(BASE_DIR, "paddleocr_md")
                os.makedirs(paddleocr_md_dir, exist_ok=True)

                if extraction_method == "PaddleOCR (本地GPU)":
                    md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir, force_local=True)
                elif extraction_method == "Legacy (pdfplumber)":
                    md_path, metadata = extract_pdf_legacy(pdf_path, out_dir=paddleocr_md_dir)
                else:
                    md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir)

                result["source_md"] = md_path
                log_q.put(f"✓ 提取完成: {os.path.basename(md_path)}")

                with open(md_path, "r", encoding="utf-8") as f:
                    full_text = f.read()

                log_q.put("[阶段 2/3] 初始化长文本引擎...")
                progress(0.2, desc="初始化引擎")
                _check_cancel()

                sys.path.insert(0, os.path.join(BASE_DIR, "new_architecture"))
                from new_architecture.config import Config
                from new_architecture.paper_cache import PaperCache, PaperMetadata
                from new_architecture.conversation_engine import ConversationEngine

                config = Config.from_env()
                paper_meta = PaperMetadata(
                    title=basename,
                    authors=[],
                    source="PDF",
                )
                cache = PaperCache(full_text, paper_meta)
                engine = ConversationEngine(config, cache, max_history_turns=2)
                log_q.put("✓ 引擎就绪 (论文全文已缓存)")

                log_q.put("[阶段 3/3] 四步深度阅读...")
                paper_output_dir = os.path.join(BASE_DIR, "deep_reading_results", basename)
                os.makedirs(paper_output_dir, exist_ok=True)
                result["output_dir"] = paper_output_dir

                # 加载并执行4步提示词
                step_results = []
                for i, (prompt_file, step_name, step_label) in enumerate(QUAL_PROMPTS):
                    _check_cancel()
                    progress(0.2 + 0.6 * (i + 1) / len(QUAL_PROMPTS), desc=f"步骤 {step_label}: {step_name}")
                    log_q.put(f"  步骤 {step_label}: {step_name}...")

                    prompt_path = os.path.join(QUAL_PROMPT_DIR, f"{prompt_file}.md")
                    if not os.path.exists(prompt_path):
                        log_q.put(f"  ⚠ 未找到提示词: {prompt_path}")
                        continue

                    with open(prompt_path, "r", encoding="utf-8") as f:
                        prompt_text = f.read()

                    full_prompt = f"【步骤 {step_label}: {step_name}】\n\n{prompt_text}"
                    answer = engine.ask(full_prompt, dimension=step_name)

                    last_turn = engine.results[-1] if engine.results else None
                    tokens_info = ""
                    if last_turn:
                        tokens_info = f"{last_turn.prompt_tokens}t / {last_turn.completion_tokens}t"

                    step_md_path = os.path.join(paper_output_dir, f"{i+1}_{step_name.replace(' ', '_')}.md")
                    with open(step_md_path, "w", encoding="utf-8") as f:
                        f.write(f"# 步骤 {step_label}: {step_name}\n\n")
                        f.write(f"> Token: {tokens_info}\n\n")
                        f.write(answer)

                    step_results.append({
                        "step": step_label,
                        "name": step_name,
                        "file": step_md_path,
                        "tokens": tokens_info,
                        "answer": answer,
                    })
                    log_q.put(f"    ✓ 完成 ({tokens_info})")

                # 合成最终报告
                log_q.put("正在合成最终报告...")
                final_report_path = os.path.join(paper_output_dir, "Final_Qual_Analysis_Report.md")
                with open(final_report_path, "w", encoding="utf-8") as f:
                    f.write(f"# 四步精读报告 (定性): {basename}\n\n")
                    f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                    f.write(f"> 论文长度: {len(full_text)} 字符\n")
                    f.write(f"> 分析步骤: 4 步 (背景层→理论层→逻辑层→价值层)\n")
                    f.write(f"> 缓存命中: ConversationEngine (自动)\n\n")
                    f.write("---\n\n")

                    for sr in step_results:
                        f.write(f"## {sr['step']}: {sr['name']}\n\n")
                        f.write(f"*Token: {sr['tokens']}*\n\n")
                        f.write(sr["answer"])
                        f.write("\n\n---\n\n")

                result["final_report"] = final_report_path
                log_q.put("✓ 四步精读完成")

                # 保存元数据
                meta_path = os.path.join(paper_output_dir, "qual_meta.json")
                import json
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "title": basename,
                        "source_pdf": pdf_path,
                        "source_md": md_path,
                        "generation_time": datetime.now().isoformat(),
                        "steps": [{"step": s["step"], "name": s["name"], "tokens": s["tokens"]} for s in step_results],
                    }, f, ensure_ascii=False, indent=2)
                log_q.put(f"✓ 元数据已保存: {meta_path}")

                progress(1.0, desc="完成")
                log_q.put("✅ 全部处理完成！")

        except InterruptedError:
            log_q.put("⚠ 用户取消了流水线")
            result["cancelled"] = True
        except Exception as e:
            log_q.put(f"❌ 错误: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        stage = ""
        for line in reversed(log_lines):
            if line.startswith("[") or line.startswith("✓") or line.startswith("⚠"):
                stage = line
                break

        progress_val = 0
        if "提取" in log_text: progress_val = 10
        if "引擎" in log_text: progress_val = 20
        if "步骤" in log_text:
            progress_val = 20 + min(60, log_text.count("步骤") * 15)
        if "合成" in log_text: progress_val = 90
        if "✅" in log_text: progress_val = 100

        preview = ""
        final_report = result.get("final_report", "")
        if final_report and os.path.exists(final_report):
            with open(final_report, "r", encoding="utf-8") as f:
                preview = f.read(8000)
            if len(preview) >= 8000:
                preview += "\n\n...（内容较长，请下载查看完整报告）..."

        yield {
            "logs": log_text,
            "stage": stage or "处理中...",
            "progress": progress_val,
            "preview": preview,
            "download": final_report if final_report and os.path.exists(final_report) else None,
        }

        if done:
            break
        time.sleep(0.5)
# ---------------------------------------------------------------------------
# Backend: Literature Filter (文献筛选)
# ---------------------------------------------------------------------------

FILTER_MODES = {
    "explorer": "探索者模式",
    "reviewer": "评审者模式",
    "empiricist": "实证主义者模式",
}

def _run_literature_filter(txt_file, mode, topic, min_year, keywords, progress=gr.Progress()):
    """文献筛选 - 基于 smart_literature_filter.py"""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    result = {"df": None, "output_path": None}

    if txt_file is None:
        yield {"logs": "请先上传文献题录文件", "stage": "错误", "progress": 0,
               "filter_table": [], "download": None}
        return

    if not topic or not topic.strip():
        yield {"logs": "请输入研究主题（筛选目标）", "stage": "错误", "progress": 0,
               "filter_table": [], "download": None}
        return

    def worker():
        try:
            with OutputCapture(log_q):
                log_q.put(f"[模式] {FILTER_MODES.get(mode, mode)} | 主题: {topic}")

                # 1. 解析文件
                log_q.put("[1/4] 解析文献题录...")
                progress(0.1, desc="解析文献题录")
                _check_cancel()

                from parsers import get_parser
                parser_instance = get_parser(txt_file)
                if not parser_instance:
                    raise ValueError("不支持的文件格式，请上传 Web of Science (savedrecs.txt) 或 CNKI 导出文件")

                parser_instance.parse()
                df = parser_instance.to_dataframe()
                log_q.put(f"✓ 解析完成: {len(df)} 篇文献")

                if df.empty:
                    raise ValueError("未找到任何文献记录")

                # 2. 基础过滤
                log_q.put("[2/4] 基础过滤...")
                progress(0.25, desc="基础过滤")
                _check_cancel()

                from smart_literature_filter import filter_literature
                kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
                df = filter_literature(df, min_year=min_year, keywords=kw_list)
                log_q.put(f"✓ 过滤后: {len(df)} 篇文献")

                if df.empty:
                    raise ValueError("过滤后无匹配文献")

                # 3. AI 评估
                log_q.put("[3/4] AI 评估...")
                progress(0.4, desc="AI 评估")
                _check_cancel()

                from smart_literature_filter import AIEvaluator, PromptManager
                evaluator = AIEvaluator()
                prompt_template = PromptManager.load_prompt(mode)

                ai_results = evaluator.evaluate_batch(df, prompt_template, topic)
                log_q.put(f"✓ AI 评估完成: {len(ai_results)} 篇")

                # 合并结果
                import pandas as pd
                ai_df = pd.DataFrame(ai_results)
                if not ai_df.empty and "original_index" in ai_df.columns:
                    ai_df.set_index("original_index", inplace=True)
                    df = df.join(ai_df, how="left")
                    if "score" in df.columns:
                        df["score"] = pd.to_numeric(df["score"], errors="coerce")
                        df = df.sort_values(by="score", ascending=False)

                # 4. 导出 Excel
                log_q.put("[4/4] 导出结果...")
                progress(0.9, desc="导出结果")
                _check_cancel()

                out_dir = os.path.join(BASE_DIR, "deep_reading_results", "literature_filter")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"filtered_{mode}_{int(time.time())}.xlsx")

                if "Year_Num" in df.columns:
                    df = df.drop(columns=["Year_Num"], errors="ignore")

                # 选择要显示的列
                display_cols = ["Title", "Authors", "Journal", "Year", "score", "reason"]
                if "title_cn" in df.columns:
                    display_cols.insert(1, "title_cn")
                if "abstract_cn" in df.columns:
                    display_cols.append("abstract_cn")
                if "journal_tier" in df.columns:
                    display_cols.insert(4, "journal_tier")

                # 只保留存在的列
                final_cols = [c for c in display_cols if c in df.columns]
                df_display = df[final_cols].copy()

                df_display.to_excel(out_path, index=False)
                log_q.put(f"✓ 已导出: {os.path.basename(out_path)}")

                result["df"] = df_display
                result["output_path"] = out_path
                result["row_count"] = len(df_display)
                progress(1.0, desc="完成")
                log_q.put("✅ 全部完成！")

        except InterruptedError:
            log_q.put("⚠ 用户取消了筛选")
            result["cancelled"] = True
        except Exception as e:
            log_q.put(f"❌ 错误: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)

        stage = "处理中..."
        for line in reversed(log_lines):
            if line.startswith("[") or line.startswith("✓") or line.startswith("⚠"):
                stage = line
                break

        progress_val = 0
        if "解析" in log_text: progress_val = 10
        if "过滤" in log_text: progress_val = 25
        if "评估" in log_text: progress_val = 40 + min(50, int(log_text.count("✓") * 10))
        if "导出" in log_text: progress_val = 90
        if "✅" in log_text: progress_val = 100

        # 构建表格预览
        table_data = []
        df = result.get("df")
        if df is not None and not df.empty:
            for _, row in df.head(20).iterrows():
                table_data.append([
                    str(row.get("Title", ""))[:60],
                    str(row.get("Authors", ""))[:40],
                    str(row.get("Journal", ""))[:30],
                    str(row.get("Year", "")),
                    str(row.get("score", "")),
                    str(row.get("reason", ""))[:80],
                ])

        yield {
            "logs": log_text,
            "stage": stage,
            "progress": progress_val,
            "filter_table": table_data,
            "download": result.get("output_path") if result.get("output_path") and os.path.exists(result["output_path"]) else None,
        }

        if done:
            break
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# UI Builder
# ---------------------------------------------------------------------------

def build_ui():
    with gr.Blocks(title="Deep Reading Agent | KIMI") as app:
        
        # ===== HEADER =====
        with gr.Row(elem_classes="kimi-header"):
            with gr.Column():
                gr.Markdown("""
                <div class="brand">
                  <div class="brand-icon">❤️‍🔥</div>
                  <div class="brand-text">
                    <h1>Deep Reading Agent</h1>
                    <div class="tagline">学术论文深度精读系统</div>
                  </div>
                </div>
                """)
            with gr.Column():
                gr.Markdown(f"""
                <div class="env-pills" style="justify-content: flex-end;">
                  <span class="pill ok">DeepSeek ✓</span>
                  <span class="pill">KIMI v3</span>
                </div>
                """)

        # ===== TABS =====
        with gr.Tabs(elem_classes="kimi-tabs") as tabs:
            
            # --- TAB 0: 文献筛选 ---
            with gr.Tab("□ 文献筛选", id="filter"):
                with gr.Row():
                    # Left sidebar
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-filter'></span> 上传文献题录</div>")
                            f_file = gr.File(
                                label="",
                                show_label=False,
                                file_types=[".txt"],
                                elem_classes="no-label",
                            )
                            gr.Markdown("<div class='upload-hint'>Web of Science (savedrecs.txt) 或 CNKI 导出文件</div>")
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-target'></span> 筛选设置</div>")
                            f_mode = gr.Radio(
                                label="",
                                show_label=False,
                                choices=[
                                    ("探索者模式", "explorer"),
                                    ("评审者模式", "reviewer"),
                                    ("实证主义者模式", "empiricist"),
                                ],
                                value="explorer",
                                elem_classes="no-label",
                            )
                            f_topic = gr.Textbox(
                                label="",
                                show_label=False,
                                placeholder="研究主题（如：数字普惠金融）",
                                elem_classes="no-label",
                            )
                            f_min_year = gr.Number(
                                label="",
                                show_label=False,
                                value=2015,
                                precision=0,
                                elem_classes="no-label",
                            )
                            gr.Markdown("<div style='font-size:11px;color:var(--text-muted);'>最小年份（0=不限制）</div>")
                            f_keywords = gr.Textbox(
                                label="",
                                show_label=False,
                                placeholder="关键词过滤，逗号分隔（可选）",
                                elem_classes="no-label",
                            )
                        
                        with gr.Row():
                            f_start = gr.Button("开始筛选", elem_classes="btn-kimi")
                            f_cancel = gr.Button("停止", elem_classes="btn-kimi-danger")
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-chart'></span> 处理进度</div>")
                            f_stage = gr.Textbox(label="", show_label=False, value="等待上传...", interactive=False, elem_classes="no-label")
                            f_progress = gr.Slider(label="", show_label=False, minimum=0, maximum=100, value=0, interactive=False, elem_classes="no-label")
                            f_log = gr.Textbox(label="", show_label=False, lines=8, interactive=False, elem_classes=["log-box", "no-label"])
                    
                    # Right main
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-target'></span> 筛选结果</div>")
                            f_table = gr.Dataframe(
                                headers=["标题", "作者", "期刊", "年份", "评分", "判定理由"],
                                label="",
                                show_label=False,
                                interactive=False,
                                elem_classes="no-label",
                            )
                            gr.Markdown("<div style='font-size:12px;color:var(--text-muted);margin-top:8px;'>评分 1-10，按分数降序排列</div>")
                        
                        with gr.Group(elem_classes="kimi-card", visible=False) as f_download_card:
                            gr.Markdown("<div class='card-title'><span class='icon icon-download'></span> 下载结果</div>")
                            f_download = gr.File(label="", show_label=False, interactive=False)
            
            # --- TAB 1: 长文本精读 ---
            with gr.Tab("➤ 长文本精读", id="long"):
                with gr.Row():
                    # Left sidebar
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-upload'></span> 上传论文</div>")
                            lc_pdf = gr.File(label="", show_label=False, file_types=[".pdf"], elem_classes="no-label")
                            gr.Markdown("<div class='upload-hint'>PDF 格式，完整论文一次性上传</div>")
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-target'></span> 分析维度</div>")
                            lc_dims = gr.CheckboxGroup(
                                label="",
                                show_label=False,
                                choices=[f"{d[1]}" for d in ANALYSIS_DIMS],
                                value=[d[1] for d in ANALYSIS_DIMS[:4]],
                                elem_classes="no-label",
                            )
                            gr.Markdown("<div style='font-size:11px;color:var(--text-muted);margin-top:8px;'>选中维度将依次执行，论文全文作为缓存前缀</div>")
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-chat'></span> 自定义问题</div>")
                            lc_custom = gr.Textbox(
                                label="",
                                show_label=False,
                                placeholder="（可选）追加一个自定义问题...",
                                lines=2,
                                elem_classes="no-label",
                            )
                        
                        with gr.Row():
                            lc_start = gr.Button("开始精读", elem_classes="btn-kimi")
                            lc_cancel = gr.Button("停止", elem_classes="btn-kimi-danger")
                    
                    # Right main
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-chart'></span> 处理进度</div>")
                            lc_stage = gr.Textbox(label="", show_label=False, value="等待上传...", interactive=False, elem_classes="no-label")
                            lc_progress = gr.Slider(label="", show_label=False, minimum=0, maximum=100, value=0, interactive=False, elem_classes="no-label")
                            lc_log = gr.Textbox(label="", show_label=False, lines=8, interactive=False, elem_classes=["log-box", "no-label"])
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-edit'></span> 分析结果</div>")
                            lc_preview = gr.Markdown("*上传 PDF 并选择维度后，点击「开始精读」*", elem_classes="md-preview")
                        
                        with gr.Group(elem_classes="kimi-card", visible=False) as lc_download_card:
                            gr.Markdown("<div class='card-title'><span class='icon icon-download'></span> 下载报告</div>")
                            lc_download = gr.File(label="", show_label=False, interactive=False)
            
            # --- TAB 2: 七步精读 ---
            with gr.Tab("△ 七步精读 (QUANT)", id="quant"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-upload'></span> 上传论文</div>")
                            q_pdf = gr.File(label="", file_types=[".pdf"])
                            q_method = gr.Radio(
                                label="提取方式",
                                choices=["PaddleOCR (远程API)", "PaddleOCR (本地GPU)", "Legacy (pdfplumber)"],
                                value="Legacy (pdfplumber)",
                            )
                            with gr.Row():
                                q_start = gr.Button("开始精读", elem_classes="btn-kimi")
                                q_cancel = gr.Button("停止", elem_classes="btn-kimi-danger")
                    
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-chart'></span> 处理进度</div>")
                            q_stage = gr.Textbox(label="当前阶段", value="等待上传...", interactive=False)
                            q_progress = gr.Slider(label="进度", minimum=0, maximum=100, value=0, interactive=False)
                            q_log = gr.Textbox(label="运行日志", lines=8, interactive=False, elem_classes="log-box")
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-edit'></span> 报告预览</div>")
                            q_preview = gr.Markdown("*上传 PDF 后点击「开始精读」*", elem_classes="md-preview")
                        
                        with gr.Group(elem_classes="kimi-card", visible=False) as q_download_card:
                            gr.Markdown("<div class='card-title'><span class='icon icon-download'></span> 下载报告</div>")
                            q_download = gr.File(label="完整报告", interactive=False)
            
            # --- TAB 3: 四步精读 ---
            with gr.Tab("◉ 四步精读 (QUAL)", id="qual"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-upload'></span> 上传论文</div>")
                            ql_pdf = gr.File(label="", show_label=False, file_types=[".pdf"], elem_classes="no-label")
                            ql_method = gr.Radio(
                                label="",
                                show_label=False,
                                choices=["PaddleOCR (远程API)", "PaddleOCR (本地GPU)", "Legacy (pdfplumber)"],
                                value="Legacy (pdfplumber)",
                                elem_classes="no-label",
                            )
                            with gr.Row():
                                ql_start = gr.Button("开始精读", elem_classes="btn-kimi")
                                ql_cancel = gr.Button("停止", elem_classes="btn-kimi-danger")
                    
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-chart'></span> 处理进度</div>")
                            ql_stage = gr.Textbox(label="", show_label=False, value="等待上传...", interactive=False, elem_classes="no-label")
                            ql_progress = gr.Slider(label="", show_label=False, minimum=0, maximum=100, value=0, interactive=False, elem_classes="no-label")
                            ql_log = gr.Textbox(label="", show_label=False, lines=8, interactive=False, elem_classes=["log-box", "no-label"])
                        
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-edit'></span> 报告预览</div>")
                            ql_preview = gr.Markdown("*上传 PDF 后点击「开始精读」*", elem_classes="md-preview")
                        
                        with gr.Group(elem_classes="kimi-card", visible=False) as ql_download_card:
                            gr.Markdown("<div class='card-title'><span class='icon icon-download'></span> 下载报告</div>")
                            ql_download = gr.File(label="", show_label=False, interactive=False)
            
            # --- TAB 4: 提示词管理 ---
            with gr.Tab("⚙ 提示词管理", id="prompts"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=300):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-folder'></span> 选择提示词</div>")
                            p_type = gr.Radio(label="模式", choices=["七步精读", "四步精读"], value="七步精读")
                            p_step = gr.Dropdown(
                                label="步骤",
                                choices=[f"{s[2]} {s[1]}" for s in QUANT_STEPS],
                                value=f"{QUANT_STEPS[0][2]} {QUANT_STEPS[0][1]}",
                            )
                            p_status = gr.Textbox(label="", show_label=False, interactive=False)
                            with gr.Row():
                                p_load = gr.Button("加载", elem_classes="btn-kimi-secondary")
                                p_save = gr.Button("保存", elem_classes="btn-kimi-secondary")
                    
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="kimi-card"):
                            gr.Markdown("<div class='card-title'><span class='icon icon-pencil'></span> 编辑器</div>")
                            p_editor = gr.Textbox(label="", lines=24, elem_classes="prompt-box")
        
        # ===== EVENTS =====
        
        # Filter events (文献筛选)
        def _f_start(file, mode, topic, min_year, keywords):
            if file is None:
                return {"f_log": "请先上传文献题录文件", "f_stage": "错误", "f_progress": 0,
                        "filter_table": [], "f_download": None, "f_download_card": gr.update(visible=False)}
            for output in _run_literature_filter(file, mode, topic, min_year, keywords):
                yield {
                    "f_log": output["logs"],
                    "f_stage": output["stage"],
                    "f_progress": output["progress"],
                    "filter_table": output["filter_table"],
                    "f_download": output["download"],
                    "f_download_card": gr.update(visible=bool(output["download"])),
                }
        
        f_start.click(
            fn=_f_start,
            inputs=[f_file, f_mode, f_topic, f_min_year, f_keywords],
            outputs=[f_log, f_stage, f_progress, f_table, f_download, f_download_card],
        )
        f_cancel.click(fn=_request_cancel, outputs=[f_stage])
        
        # Long context events
        def _lc_start(pdf, dims, custom_q):
            if pdf is None:
                return {"lc_log": "请先上传 PDF", "lc_stage": "错误", "lc_progress": 0, 
                        "lc_preview": "", "lc_download": None, "lc_download_card": gr.update(visible=False)}
            # Map display names back to keys
            dim_keys = []
            for d in dims:
                for ak, an, _ in ANALYSIS_DIMS:
                    if an == d:
                        dim_keys.append(ak)
            
            for output in run_long_context(pdf, dim_keys, custom_q):
                yield {
                    "lc_log": output["logs"],
                    "lc_stage": output["stage"],
                    "lc_progress": output["progress"],
                    "lc_preview": output["preview"] or "*正在分析...*",
                    "lc_download": output["download"],
                    "lc_download_card": gr.update(visible=bool(output["download"])),
                }
        
        lc_start.click(
            fn=_lc_start,
            inputs=[lc_pdf, lc_dims, lc_custom],
            outputs=[lc_log, lc_stage, lc_progress, lc_preview, lc_download, lc_download_card],
        )
        lc_cancel.click(fn=_request_cancel, outputs=[lc_stage])
        
        # Quant events
        def _q_start(pdf, method):
            if pdf is None:
                return {"q_log": "请先上传 PDF", "q_stage": "错误", "q_progress": 0,
                        "q_preview": "", "q_download": None, "q_download_card": gr.update(visible=False)}
            for output in run_deep_reading(pdf, method):
                yield {
                    "q_log": output["logs"],
                    "q_stage": output["stage"],
                    "q_progress": output["progress"],
                    "q_preview": output["preview"] or "*正在生成报告...*",
                    "q_download": output["download"],
                    "q_download_card": gr.update(visible=bool(output["download"])),
                }
        
        q_start.click(
            fn=_q_start,
            inputs=[q_pdf, q_method],
            outputs=[q_log, q_stage, q_progress, q_preview, q_download, q_download_card],
        )
        q_cancel.click(fn=_request_cancel, outputs=[q_stage])
        
        # Qual events (四步精读)
        def _ql_start(pdf, method):
            if pdf is None:
                return {"ql_log": "请先上传 PDF", "ql_stage": "错误", "ql_progress": 0,
                        "ql_preview": "", "ql_download": None, "ql_download_card": gr.update(visible=False)}
            for output in run_qual_analysis(pdf, method):
                yield {
                    "ql_log": output["logs"],
                    "ql_stage": output["stage"],
                    "ql_progress": output["progress"],
                    "ql_preview": output["preview"] or "*正在生成报告...*",
                    "ql_download": output["download"],
                    "ql_download_card": gr.update(visible=bool(output["download"])),
                }
        
        ql_start.click(
            fn=_ql_start,
            inputs=[ql_pdf, ql_method],
            outputs=[ql_log, ql_stage, ql_progress, ql_preview, ql_download, ql_download_card],
        )
        ql_cancel.click(fn=_request_cancel, outputs=[ql_stage])
        
        # Prompt events
        def _p_type_change(pt):
            is_quant = pt == "七步精读"
            choices = [f"{s[2]} {s[1]}" for s in (QUANT_STEPS if is_quant else QUAL_STEPS)]
            return gr.update(choices=choices, value=choices[0])
        
        p_type.change(fn=_p_type_change, inputs=[p_type], outputs=[p_step])
        
        def _p_load(pt, ps):
            is_quant = pt == "七步精读"
            step_name = ps.split(" ", 1)[1] if " " in ps else ps
            # Map display to file name
            name_map = {
                "全景扫描": "step_1_overview", "理论与假说": "step_2_theory",
                "数据考古": "step_3_data", "变量与测量": "step_4_vars",
                "识别策略": "step_5_identification", "结果解读": "step_6_results",
                "专家批判": "step_7_critique",
                "背景层": "L1_Context", "理论层": "L2_Theory",
                "逻辑层": "L3_Logic", "价值层": "L4_Value",
            }
            actual = name_map.get(step_name, step_name.replace(" ", "_").lower())
            ptype = "quant" if is_quant else "qual"
            content = _load_prompt_file(actual, ptype)
            status = f"✓ 已加载 {actual}.md" if content else f"未找到 {actual}.md"
            return content, status, actual, ptype
        
        p_load.click(
            fn=_p_load,
            inputs=[p_type, p_step],
            outputs=[p_editor, p_status, gr.State(), gr.State()],
        )
        
        # Initial load
        app.load(
            fn=lambda: _load_prompt_file("step_1_overview", "quant"),
            outputs=[p_editor],
        )
    
    return app


if __name__ == "__main__":
    app = build_ui()
    app.queue(max_size=20)
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=EXTRA_CSS,
        theme=KIMI_THEME,
    )
