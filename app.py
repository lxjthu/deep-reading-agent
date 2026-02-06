#!/usr/bin/env python3
"""
Deep Reading Agent - Gradio GUI

Single-file GUI for the Deep Reading Agent pipeline.
Launch: python app.py
Browse: http://127.0.0.1:7860
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
from datetime import datetime
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "_gui_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment status
# ---------------------------------------------------------------------------

def _local_paddleocr_available() -> bool:
    """Check if local PaddleOCR (paddleocr + paddlex) is installed."""
    try:
        from paddleocr_local import is_available
        return is_available()
    except ImportError:
        return False


_LOCAL_POCR = _local_paddleocr_available()


def _env_status():
    """Return a short status string about configured API keys."""
    parts = []
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")
    parts.append(f"DeepSeek API: {'Configured' if ds_key else 'Missing'}")

    # PaddleOCR status: local GPU + remote API
    pocr_parts = []
    if _LOCAL_POCR:
        pocr_parts.append("Local GPU")
    pocr_url = os.getenv("PADDLEOCR_REMOTE_URL", "")
    if pocr_url:
        pocr_parts.append("Remote API")
    if pocr_parts:
        parts.append(f"PaddleOCR: {' + '.join(pocr_parts)}")
    else:
        parts.append("PaddleOCR: Not available (will use pdfplumber fallback)")

    qwen_key = os.getenv("QWEN_API_KEY", "")
    parts.append(f"Qwen Vision: {'Configured' if qwen_key else 'Not configured'}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Log capture utilities
# ---------------------------------------------------------------------------

class QueueHandler(logging.Handler):
    """Sends log records into a queue for Gradio streaming."""

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
    """Captures print() / stdout writes into a queue."""

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
    """Context manager that captures logging + stdout into a queue."""

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._handler = None
        self._tee = None
        self._orig_stdout = None

    def __enter__(self):
        # Attach queue handler to root logger
        self._handler = QueueHandler(self.log_queue)
        self._handler.setLevel(logging.DEBUG)
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self._handler)

        # Redirect stdout
        self._orig_stdout = sys.stdout
        self._tee = TeeWriter(self.log_queue, self._orig_stdout)
        sys.stdout = self._tee
        return self

    def __exit__(self, *exc):
        sys.stdout = self._orig_stdout
        logging.getLogger().removeHandler(self._handler)


def _drain_queue(log_queue: queue.Queue, log_lines: list, max_lines: int = 500):
    """Drain all pending messages from queue into log_lines list."""
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
    """Copy a Gradio uploaded file into _gui_uploads/ and return stable path."""
    if uploaded_file is None:
        return ""
    src = uploaded_file if isinstance(uploaded_file, str) else uploaded_file.name
    basename = os.path.basename(src)
    dst = os.path.join(UPLOAD_DIR, basename)
    shutil.copy2(src, dst)
    return dst


# ---------------------------------------------------------------------------
# Cancel mechanism
# ---------------------------------------------------------------------------

_cancel_event = threading.Event()


def _request_cancel():
    _cancel_event.set()
    return "Cancellation requested... will stop after current stage."


def _check_cancel():
    if _cancel_event.is_set():
        raise InterruptedError("Cancelled by user")


# ---------------------------------------------------------------------------
# Tab 1: PDF Extraction backend
# ---------------------------------------------------------------------------

def run_extraction(
    pdf_file,
    out_dir,
    use_local_gpu,
    use_table,
    use_formula,
    use_chart,
    use_orientation,
    download_images,
    max_pages,
    no_fallback,
    force_legacy,
):
    """Generator that yields (log, preview, metadata, download_file) tuples."""
    log_q = queue.Queue()
    log_lines = []
    result = {}

    pdf_path = _stable_copy(pdf_file)
    if not pdf_path:
        yield "未提供 PDF 文件", "", "{}", None
        return

    out_dir = out_dir.strip() or "paddleocr_md"
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(BASE_DIR, out_dir)
    os.makedirs(out_dir, exist_ok=True)

    def worker():
        try:
            with OutputCapture(log_q):
                from paddleocr_pipeline import (
                    extract_with_fallback, extract_pdf_legacy,
                    extract_pdf_local_paddleocr,
                )

                if force_legacy:
                    md_path, metadata = extract_pdf_legacy(pdf_path, out_dir)
                elif use_local_gpu:
                    md_path, metadata = extract_with_fallback(
                        pdf_path,
                        out_dir=out_dir,
                        use_table_recognition=use_table,
                        use_formula_recognition=use_formula,
                        use_chart_recognition=use_chart,
                        use_doc_orientation_classify=use_orientation,
                        no_fallback=no_fallback,
                        force_local=True,
                    )
                else:
                    md_path, metadata = extract_with_fallback(
                        pdf_path,
                        out_dir=out_dir,
                        download_images=download_images,
                        use_table_recognition=use_table,
                        use_formula_recognition=use_formula,
                        use_chart_recognition=use_chart,
                        use_doc_orientation_classify=use_orientation,
                        max_pages_per_chunk=int(max_pages),
                        no_fallback=no_fallback,
                    )
                result["md_path"] = md_path
                result["metadata"] = metadata
        except Exception as e:
            log_q.put(f"ERROR: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    # Stream logs
    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        yield log_text, "", "{}", None
        if done:
            break
        time.sleep(0.5)

    # Final yield with results
    log_text = "\n".join(log_lines)
    if "error" in result:
        yield log_text, f"提取失败: {result['error']}", "{}", None
        return

    md_path = result.get("md_path", "")
    metadata = result.get("metadata", {})

    # Read markdown preview
    preview = ""
    if md_path and os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            preview = f.read(10000)
        if len(preview) >= 10000:
            preview += "\n\n...（已截断）..."

    import json
    meta_str = json.dumps(metadata, indent=2, ensure_ascii=False, default=str)

    yield log_text, preview, meta_str, md_path if md_path and os.path.exists(md_path) else None


# ---------------------------------------------------------------------------
# Tab 2: Full Pipeline Deep Reading backend
# ---------------------------------------------------------------------------

def run_full_pipeline(pdf_file, extraction_method):
    """Generator that yields (stage, log, preview, download_file) tuples."""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    result = {}

    pdf_path = _stable_copy(pdf_file)
    if not pdf_path:
        yield "错误", "未提供 PDF 文件", "", None
        return

    basename = os.path.splitext(os.path.basename(pdf_path))[0]

    def worker():
        try:
            with OutputCapture(log_q):
                # ---- Stage 1: Extraction ----
                log_q.put(f"[阶段 1/5] 提取 PDF: {basename}")
                _check_cancel()

                from paddleocr_pipeline import extract_with_fallback, extract_pdf_legacy

                paddleocr_md_dir = os.path.join(BASE_DIR, "paddleocr_md")
                os.makedirs(paddleocr_md_dir, exist_ok=True)

                if extraction_method == "PaddleOCR (本地GPU)":
                    md_path, metadata = extract_with_fallback(
                        pdf_path, out_dir=paddleocr_md_dir, force_local=True)
                elif extraction_method == "Legacy (pdfplumber)":
                    md_path, metadata = extract_pdf_legacy(pdf_path, out_dir=paddleocr_md_dir)
                else:
                    # "PaddleOCR (远程API)" or default
                    md_path, metadata = extract_with_fallback(pdf_path, out_dir=paddleocr_md_dir)

                result["source_md"] = md_path
                log_q.put(f"提取完成: {md_path}")

                # ---- Stage 2: Deep Reading (7 steps) ----
                log_q.put(f"[阶段 2/5] 深度阅读（7步分析）...")
                _check_cancel()

                from deep_reading_steps import (
                    common,
                    step_1_overview, step_2_theory, step_3_data,
                    step_4_vars, step_5_identification, step_6_results,
                    step_7_critique,
                )
                from deep_reading_steps.semantic_router import generate_semantic_index

                sections = common.load_md_sections(md_path)
                paper_basename = basename
                if paper_basename.endswith("_segmented"):
                    paper_basename = paper_basename[:-10]

                paper_output_dir = os.path.join(BASE_DIR, "deep_reading_results", paper_basename)
                os.makedirs(paper_output_dir, exist_ok=True)
                result["output_dir"] = paper_output_dir

                # Set env var for common.py
                os.environ["DEEP_READING_OUTPUT_DIR"] = paper_output_dir

                # Semantic index
                index_path = os.path.join(paper_output_dir, "semantic_index.json")
                if not os.path.exists(index_path):
                    full_text = "\n\n".join(sections.values())
                    log_q.put("正在生成语义索引...")
                    generate_semantic_index(full_text, paper_output_dir)

                section_routing = common.route_sections_to_steps(sections)
                common.save_routing_result(section_routing, sections, paper_output_dir)

                step_modules = [
                    (step_1_overview, 1, "研究概览"),
                    (step_2_theory, 2, "理论框架"),
                    (step_3_data, 3, "数据与样本"),
                    (step_4_vars, 4, "变量定义"),
                    (step_5_identification, 5, "识别策略"),
                    (step_6_results, 6, "实证结果"),
                    (step_7_critique, 7, "批判性评价"),
                ]

                for mod, sid, name in step_modules:
                    _check_cancel()
                    log_q.put(f"  步骤 {sid}/7: {name}...")
                    assigned = section_routing.get(sid, [])
                    mod.run(sections, assigned, paper_output_dir, step_id=sid)

                # Synthesize final report
                log_q.put("正在合成最终报告...")
                import re as _re
                final_report_path = os.path.join(paper_output_dir, "Final_Deep_Reading_Report.md")
                with open(final_report_path, "w", encoding="utf-8") as f:
                    f.write(f"# 深度阅读报告: {paper_basename}\n\n")
                    step_names = [
                        "1_Overview", "2_Theory", "3_Data", "4_Variables",
                        "5_Identification", "6_Results", "7_Critique",
                    ]
                    for sn in step_names:
                        sf_path = os.path.join(paper_output_dir, f"{sn}.md")
                        if os.path.exists(sf_path):
                            with open(sf_path, "r", encoding="utf-8") as sf:
                                content = sf.read()
                            # strip YAML frontmatter
                            content = _re.sub(r"^---\n.*?\n---\n", "", content, flags=_re.DOTALL)
                            for marker in ["## \u5bfc\u822a", "## Navigation"]:
                                if marker in content:
                                    content = content.split(marker)[0]
                            f.write(f"## {sn.replace('_', ' ')}\n\n{content.strip()}\n\n")

                result["final_report"] = final_report_path
                log_q.put("深度阅读完成")

                # ---- Stage 3: Supplemental Check ----
                log_q.put(f"[阶段 3/5] 补充检查...")
                _check_cancel()
                try:
                    env = os.environ.copy()
                    env["DEEP_READING_OUTPUT_DIR"] = paper_output_dir
                    subprocess.run(
                        [sys.executable, os.path.join(BASE_DIR, "run_supplemental_reading.py"),
                         final_report_path, "--regenerate"],
                        check=True, env=env, cwd=BASE_DIR,
                        capture_output=True, text=True,
                    )
                    log_q.put("补充检查完成")
                except subprocess.CalledProcessError as e:
                    log_q.put(f"补充检查警告: {e.stderr or e}")
                except FileNotFoundError:
                    log_q.put("未找到补充阅读脚本，跳过")

                # ---- Stage 4: Dataview Summaries ----
                log_q.put(f"[阶段 4/5] 注入 Dataview 摘要...")
                _check_cancel()
                try:
                    subprocess.run(
                        [sys.executable, os.path.join(BASE_DIR, "inject_dataview_summaries.py"),
                         paper_output_dir],
                        check=True, cwd=BASE_DIR,
                        capture_output=True, text=True,
                    )
                    log_q.put("Dataview 摘要注入完成")
                except subprocess.CalledProcessError as e:
                    log_q.put(f"Dataview 摘要警告: {e.stderr or e}")
                except FileNotFoundError:
                    log_q.put("未找到 inject_dataview_summaries.py，跳过")

                # ---- Stage 5: Obsidian Metadata ----
                log_q.put(f"[阶段 5/5] 注入 Obsidian 元数据...")
                _check_cancel()
                try:
                    # Build command with PDF vision extraction if Qwen API is configured
                    meta_cmd = [
                        sys.executable, os.path.join(BASE_DIR, "inject_obsidian_meta.py"),
                        md_path, paper_output_dir,
                    ]
                    if os.getenv("QWEN_API_KEY"):
                        meta_cmd.extend(["--use_pdf_vision", "--pdf_path", pdf_path])
                        log_q.put("  已启用 PDF 视觉提取（检测到 Qwen API）")

                    subprocess.run(
                        meta_cmd,
                        check=True, cwd=BASE_DIR,
                        capture_output=True, text=True,
                    )
                    log_q.put("Obsidian 元数据注入完成")
                except subprocess.CalledProcessError as e:
                    log_q.put(f"元数据注入警告: {e.stderr or e}")
                except FileNotFoundError:
                    log_q.put("未找到 inject_obsidian_meta.py，跳过")

                log_q.put("全部 5 个阶段完成！")

        except InterruptedError:
            log_q.put("用户取消了流水线")
            result["cancelled"] = True
        except Exception as e:
            log_q.put(f"错误: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    # Stream updates
    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        # Determine current stage from last stage line
        stage = ""
        for line in reversed(log_lines):
            if line.startswith("[阶段"):
                stage = line
                break
        yield stage, log_text, "", None
        if done:
            break
        time.sleep(0.5)

    # Final yield
    log_text = "\n".join(log_lines)
    stage = "完成" if "error" not in result and "cancelled" not in result else "错误/已取消"
    preview = ""
    final_report = result.get("final_report", "")
    if final_report and os.path.exists(final_report):
        with open(final_report, "r", encoding="utf-8") as f:
            preview = f.read(15000)
        if len(preview) >= 15000:
            preview += "\n\n...（已截断）..."

    output_dir = result.get("output_dir", "")
    yield stage, log_text, preview, output_dir if output_dir and os.path.isdir(output_dir) else None


# ---------------------------------------------------------------------------
# Tab 3: Batch Processing backend
# ---------------------------------------------------------------------------

def validate_folder(folder_path):
    """Validate a folder path and return status info."""
    folder_path = folder_path.strip()
    if not folder_path:
        return "请输入文件夹路径"
    if not os.path.isdir(folder_path):
        return f"目录不存在: {folder_path}"
    pdf_count = 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_count += 1
    return f"找到 {pdf_count} 个 PDF 文件"


def run_batch(folder_path, skip_processed, extraction_method="PaddleOCR (远程API)"):
    """Generator yielding (progress_df, log, overall) tuples."""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    progress_data = []  # list of [filename, type, status, elapsed]
    result = {}

    folder_path = folder_path.strip()
    if not folder_path or not os.path.isdir(folder_path):
        import pandas as pd
        yield pd.DataFrame(columns=["文件名", "类型", "状态", "耗时"]), "无效的文件夹路径", ""
        return

    def worker():
        try:
            with OutputCapture(log_q):
                from smart_scholar_lib import SmartScholar
                from state_manager import StateManager

                scholar = SmartScholar()
                state_mgr = StateManager()

                # Configure extraction method for SmartScholar
                if extraction_method == "PaddleOCR (本地GPU)":
                    os.environ["PADDLEOCR_FORCE_LOCAL"] = "1"
                    log_q.put("使用本地 PaddleOCR (GPU) 进行提取")
                else:
                    os.environ.pop("PADDLEOCR_FORCE_LOCAL", None)

                # Find PDFs
                pdf_files = []
                for root, _, files in os.walk(folder_path):
                    for f in files:
                        if f.lower().endswith(".pdf"):
                            pdf_files.append(os.path.join(root, f))
                pdf_files.sort()

                if not pdf_files:
                    log_q.put("未找到 PDF 文件")
                    result["done"] = True
                    return

                log_q.put(f"找到 {len(pdf_files)} 个 PDF 文件")

                deep_reading_results_dir = os.path.join(BASE_DIR, "deep_reading_results")
                qual_results_dir = os.path.join(BASE_DIR, "social_science_results_v2")

                for i, pdf_path in enumerate(pdf_files):
                    _check_cancel()
                    bname = os.path.splitext(os.path.basename(pdf_path))[0]
                    t0 = time.time()

                    # --- check skip ---
                    if skip_processed:
                        def _output_exists(d):
                            return (
                                d and os.path.exists(d)
                                and (
                                    os.path.exists(os.path.join(d, "Final_Deep_Reading_Report.md"))
                                    or os.path.exists(os.path.join(d, f"{bname}_Full_Report.md"))
                                )
                            )

                        if state_mgr.is_processed(pdf_path, output_check_func=_output_exists):
                            elapsed = f"{time.time() - t0:.1f}s"
                            progress_data.append([bname, "-", "已跳过(哈希)", elapsed])
                            log_q.put(f"[跳过] {bname}")
                            continue

                        # fallback filename check
                        quant_report = os.path.join(deep_reading_results_dir, bname, "Final_Deep_Reading_Report.md")
                        qual_report = os.path.join(qual_results_dir, bname, f"{bname}_Full_Report.md")
                        if os.path.exists(quant_report):
                            state_mgr.mark_completed(pdf_path, os.path.dirname(quant_report), "QUANT")
                            progress_data.append([bname, "QUANT", "已跳过(已存在)", f"{time.time() - t0:.1f}s"])
                            log_q.put(f"[跳过] {bname} (已有 QUANT 结果)")
                            continue
                        if os.path.exists(qual_report):
                            state_mgr.mark_completed(pdf_path, os.path.dirname(qual_report), "QUAL")
                            progress_data.append([bname, "QUAL", "已跳过(已存在)", f"{time.time() - t0:.1f}s"])
                            log_q.put(f"[跳过] {bname} (已有 QUAL 结果)")
                            continue

                    log_q.put(f"\n[{i+1}/{len(pdf_files)}] 处理中: {bname}")
                    state_mgr.mark_started(pdf_path)

                    try:
                        # 1. Extract
                        extracted_md_path = scholar.ensure_extracted_md(pdf_path)
                        if not extracted_md_path:
                            state_mgr.mark_failed(pdf_path, "提取失败")
                            progress_data.append([bname, "-", "失败(提取)", f"{time.time() - t0:.1f}s"])
                            continue

                        # 2. Classify
                        with open(extracted_md_path, "r", encoding="utf-8") as f:
                            preview = f.read(5000)
                        paper_type = scholar.classify_paper(preview)
                        log_q.put(f"  分类结果: {paper_type}")

                        if paper_type == "IGNORE":
                            state_mgr.mark_completed(pdf_path, None, "IGNORE")
                            progress_data.append([bname, "IGNORE", "已跳过", f"{time.time() - t0:.1f}s"])
                            continue

                        # 3. Dispatch
                        if paper_type == "QUANT":
                            paper_output_dir = os.path.join(deep_reading_results_dir, bname)
                            env = os.environ.copy()
                            env["DEEP_READING_OUTPUT_DIR"] = paper_output_dir
                            scholar.run_command(
                                [sys.executable, os.path.join(BASE_DIR, "deep_read_pipeline.py"), extracted_md_path,
                                 "--out_dir", deep_reading_results_dir],
                                cwd=BASE_DIR,
                            )
                            # Inject metadata
                            if os.path.exists(extracted_md_path):
                                try:
                                    meta_cmd = [
                                        sys.executable, os.path.join(BASE_DIR, "inject_obsidian_meta.py"),
                                        extracted_md_path, paper_output_dir,
                                    ]
                                    if os.getenv("QWEN_API_KEY"):
                                        meta_cmd.extend(["--use_pdf_vision", "--pdf_path", pdf_path])
                                    scholar.run_command(meta_cmd, cwd=BASE_DIR)
                                except Exception as me:
                                    log_q.put(f"  元数据警告: {me}")

                            state_mgr.mark_completed(pdf_path, paper_output_dir, "QUANT")

                        elif paper_type == "QUAL":
                            extraction_dir = os.path.dirname(extracted_md_path)
                            scholar.run_command(
                                [sys.executable, os.path.join(BASE_DIR, "social_science_analyzer_v2.py"),
                                 extraction_dir, "--filter", bname],
                                cwd=BASE_DIR,
                            )
                            paper_output_dir = os.path.join(qual_results_dir, bname)
                            pdf_dir_for_meta = os.path.dirname(pdf_path)
                            try:
                                # 直接传递 PDF 路径，避免文件名匹配问题
                                qual_meta_cmd = [
                                    sys.executable, "-m", "qual_metadata_extractor.extractor",
                                    paper_output_dir, pdf_dir_for_meta,
                                    "--pdf_path", pdf_path,
                                ]
                                scholar.run_command(qual_meta_cmd, cwd=BASE_DIR)
                            except Exception as me:
                                log_q.put(f"  QUAL 元数据警告: {me}")
                            state_mgr.mark_completed(pdf_path, paper_output_dir, "QUAL")

                        elapsed = f"{time.time() - t0:.1f}s"
                        progress_data.append([bname, paper_type, "完成", elapsed])
                        log_q.put(f"  完成，耗时 {elapsed}")

                    except Exception as e:
                        state_mgr.mark_failed(pdf_path, str(e))
                        progress_data.append([bname, "-", f"失败: {e}", f"{time.time() - t0:.1f}s"])
                        log_q.put(f"  错误: {e}")

                log_q.put("\n批量处理完成")
                result["done"] = True

        except InterruptedError:
            log_q.put("用户取消了批量处理")
        except Exception as e:
            log_q.put(f"批量处理错误: {e}")
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    import pandas as pd
    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        df = pd.DataFrame(progress_data, columns=["文件名", "类型", "状态", "耗时"]) if progress_data else pd.DataFrame(columns=["文件名", "类型", "状态", "耗时"])
        total = f"已处理: {len(progress_data)} 个文件"
        yield df, log_text, total
        if done:
            break
        time.sleep(0.5)

    # Final
    log_text = "\n".join(log_lines)
    df = pd.DataFrame(progress_data, columns=["文件名", "类型", "状态", "耗时"]) if progress_data else pd.DataFrame(columns=["文件名", "类型", "状态", "耗时"])
    done_count = sum(1 for r in progress_data if r[2] == "完成")
    skip_count = sum(1 for r in progress_data if "跳过" in r[2])
    fail_count = sum(1 for r in progress_data if "失败" in r[2])
    total = f"总计: {len(progress_data)} | 完成: {done_count} | 跳过: {skip_count} | 失败: {fail_count}"
    yield df, log_text, total


# ---------------------------------------------------------------------------
# Tab 4: Literature Filter backend
# ---------------------------------------------------------------------------

def run_literature_filter(input_file, ai_mode, topic, min_year, keywords, limit_num):
    """Generator yielding (log, result_df, download_file) tuples."""
    log_q = queue.Queue()
    log_lines = []
    result = {}

    file_path = _stable_copy(input_file)
    if not file_path:
        import pandas as pd
        yield "未提供文件", pd.DataFrame(), None
        return

    def worker():
        try:
            with OutputCapture(log_q):
                from parsers import get_parser
                from smart_literature_filter import filter_literature, AIEvaluator, PromptManager

                # 1. Parse
                log_q.put(f"正在解析文件: {os.path.basename(file_path)}")
                parser_instance = get_parser(file_path)
                if not parser_instance:
                    log_q.put("错误：不支持的文件格式，请上传 WoS (savedrecs.txt) 或 CNKI 导出文件")
                    result["error"] = "Unsupported format"
                    return

                parser_instance.parse()
                df = parser_instance.to_dataframe()
                log_q.put(f"解析完成：{len(df)} 条记录（来源: {df['SourceType'].iloc[0] if len(df) > 0 else '未知'}）")

                if df.empty:
                    log_q.put("文件中未找到记录")
                    result["df"] = df
                    return

                # 2. Filter by year / keywords
                kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords.strip() else None
                yr = int(min_year) if min_year and str(min_year).strip() else None

                if yr or kw_list:
                    before = len(df)
                    df = filter_literature(df, min_year=yr, keywords=kw_list)
                    log_q.put(f"过滤结果: {before} -> {len(df)} 条记录")

                if df.empty:
                    log_q.put("没有符合过滤条件的论文")
                    result["df"] = df
                    return

                # 3. AI evaluation
                # 映射中文选项到英文模式名
                ai_mode_map = {
                    "无": None,
                    "explorer (广泛探索)": "explorer",
                    "reviewer (严格评审)": "reviewer",
                    "empiricist (实证导向)": "empiricist",
                    # 兼容旧版英文选项
                    "None": None,
                    "explorer": "explorer",
                    "reviewer": "reviewer",
                    "empiricist": "empiricist",
                }
                actual_ai_mode = ai_mode_map.get(ai_mode)

                if actual_ai_mode:
                    if not topic or not topic.strip():
                        log_q.put("错误：AI 评估模式需要填写研究主题")
                        result["df"] = df
                        return

                    log_q.put(f"开始 AI 评估（模式: {actual_ai_mode}, 主题: {topic}）")
                    evaluator = AIEvaluator()
                    prompt_template = PromptManager.load_prompt(actual_ai_mode)

                    lim = int(limit_num) if limit_num else 0
                    if lim > 0:
                        df_to_eval = df.head(lim).copy()
                        log_q.put(f"限制 AI 评估数量: {lim} 篇")
                    else:
                        df_to_eval = df.copy()

                    import concurrent.futures
                    import json as _json

                    evaluated = 0
                    total = len(df_to_eval)
                    ai_results = []

                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_idx = {
                            executor.submit(evaluator.evaluate_paper, row, prompt_template, topic): idx
                            for idx, row in df_to_eval.iterrows()
                        }
                        for future in concurrent.futures.as_completed(future_to_idx):
                            idx = future_to_idx[future]
                            try:
                                res = future.result()
                                res["original_index"] = idx
                                ai_results.append(res)
                            except Exception as e:
                                ai_results.append({"original_index": idx, "error": str(e)})
                            evaluated += 1
                            if evaluated % 5 == 0 or evaluated == total:
                                log_q.put(f"  AI 评估进度: {evaluated}/{total}")

                    import pandas as _pd
                    ai_df = _pd.DataFrame(ai_results)
                    if not ai_df.empty:
                        ai_df.set_index("original_index", inplace=True)
                        df = df.join(ai_df, how="left")
                        if "score" in df.columns:
                            df["score"] = _pd.to_numeric(df["score"], errors="coerce")
                            df = df.sort_values(by="score", ascending=False)

                    log_q.put(f"AI 评估完成，已评分 {len(ai_results)} 篇论文")

                # 4. Save Excel
                if "Year_Num" in df.columns:
                    df = df.drop(columns=["Year_Num"])

                out_path = os.path.join(UPLOAD_DIR, "literature_filter_result.xlsx")
                df.to_excel(out_path, index=False)
                log_q.put(f"结果已保存: {out_path}（共 {len(df)} 篇）")

                result["df"] = df
                result["excel"] = out_path

        except Exception as e:
            log_q.put(f"ERROR: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    import pandas as pd
    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        yield log_text, pd.DataFrame(), None
        if done:
            break
        time.sleep(0.5)

    log_text = "\n".join(log_lines)
    df_out = result.get("df", pd.DataFrame())

    # Trim display columns for readability
    display_cols = [c for c in ["Title", "Authors", "Journal", "Year", "score", "relevance", "recommendation", "SourceType"] if c in df_out.columns]
    df_display = df_out[display_cols] if display_cols else df_out

    excel_path = result.get("excel")
    yield log_text, df_display, excel_path if excel_path and os.path.exists(excel_path) else None


# ---------------------------------------------------------------------------
# Tab 5: MD Deep Reading backend
# ---------------------------------------------------------------------------

def validate_md_folder(folder_path):
    """Validate a folder path and return MD file statistics."""
    folder_path = folder_path.strip()
    if not folder_path:
        return "请输入文件夹路径。"
    if not os.path.isdir(folder_path):
        return f"目录不存在: {folder_path}"
    total = 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(".md"):
                total += 1
    return f"找到 {total} 个 MD 文件"


def _clean_paper_basename(filename):
    """Strip known suffixes to get a clean paper name."""
    name = os.path.splitext(filename)[0]
    for suffix in ("_segmented", "_paddleocr", "_raw"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def run_md_reading(mode, md_file, folder_path, skip_processed):
    """Generator yielding (progress_df, log, overall, preview, download) tuples."""
    _cancel_event.clear()
    log_q = queue.Queue()
    log_lines = []
    progress_data = []  # [filename, type, status, elapsed]
    result = {}

    import pandas as pd

    empty_df = pd.DataFrame(columns=["文件名", "类型", "状态", "耗时"])

    # Collect MD file list
    md_paths = []
    if mode == "单文件":
        stable = _stable_copy(md_file)
        if not stable:
            yield empty_df, "未提供 MD 文件。", "", "", None
            return
        md_paths.append(stable)
    else:
        fp = (folder_path or "").strip()
        if not fp or not os.path.isdir(fp):
            yield empty_df, "文件夹路径无效。", "", "", None
            return
        for root, _, files in os.walk(fp):
            for f in sorted(files):
                if f.lower().endswith(".md"):
                    md_paths.append(os.path.join(root, f))
        if not md_paths:
            yield empty_df, "文件夹中没有找到 .md 文件。", "", "", None
            return

    def worker():
        try:
            with OutputCapture(log_q):
                from smart_scholar_lib import SmartScholar

                scholar = SmartScholar()

                deep_reading_results_dir = os.path.join(BASE_DIR, "deep_reading_results")
                qual_results_dir = os.path.join(BASE_DIR, "social_science_results_v2")

                log_q.put(f"待处理 MD 文件: {len(md_paths)} 个")

                for i, md_path in enumerate(md_paths):
                    _check_cancel()
                    fname = os.path.basename(md_path)
                    bname = _clean_paper_basename(fname)
                    t0 = time.time()
                    log_q.put(f"\n[{i+1}/{len(md_paths)}] 处理: {fname}")

                    # --- skip check ---
                    if skip_processed:
                        quant_report = os.path.join(deep_reading_results_dir, bname, "Final_Deep_Reading_Report.md")
                        qual_report = os.path.join(qual_results_dir, bname, f"{bname}_Full_Report.md")
                        if os.path.exists(quant_report) or os.path.exists(qual_report):
                            elapsed = f"{time.time() - t0:.1f}s"
                            progress_data.append([fname, "-", "已跳过", elapsed])
                            log_q.put(f"  [SKIP] 已存在结果: {bname}")
                            continue

                    # --- classify ---
                    with open(md_path, "r", encoding="utf-8") as f:
                        preview_text = f.read(5000)
                    paper_type = scholar.classify_paper(preview_text)
                    log_q.put(f"  分类结果: {paper_type}")

                    if paper_type == "IGNORE":
                        elapsed = f"{time.time() - t0:.1f}s"
                        progress_data.append([fname, "IGNORE", "已跳过", elapsed])
                        continue

                    # --- dispatch ---
                    try:
                        if paper_type == "QUANT":
                            paper_output_dir = os.path.join(deep_reading_results_dir, bname)
                            scholar.run_command(
                                [sys.executable, os.path.join(BASE_DIR, "deep_read_pipeline.py"),
                                 md_path, "--out_dir", deep_reading_results_dir],
                                cwd=BASE_DIR,
                            )
                            # Inject metadata
                            try:
                                scholar.run_command(
                                    [sys.executable, os.path.join(BASE_DIR, "inject_obsidian_meta.py"),
                                     md_path, paper_output_dir],
                                    cwd=BASE_DIR,
                                )
                            except Exception as me:
                                log_q.put(f"  元数据注入警告: {me}")
                            result_path = os.path.join(paper_output_dir, "Final_Deep_Reading_Report.md")

                        elif paper_type == "QUAL":
                            md_dir = os.path.dirname(md_path)
                            scholar.run_command(
                                [sys.executable, os.path.join(BASE_DIR, "social_science_analyzer_v2.py"),
                                 md_dir, "--filter", bname],
                                cwd=BASE_DIR,
                            )
                            paper_output_dir = os.path.join(qual_results_dir, bname)
                            try:
                                scholar.run_command(
                                    [sys.executable, "-m", "qual_metadata_extractor.extractor",
                                     paper_output_dir, os.path.dirname(md_path)],
                                    cwd=BASE_DIR,
                                )
                            except Exception as me:
                                log_q.put(f"  QUAL 元数据警告: {me}")
                            result_path = os.path.join(paper_output_dir, f"{bname}_Full_Report.md")

                        elapsed = f"{time.time() - t0:.1f}s"
                        progress_data.append([fname, paper_type, "完成", elapsed])
                        log_q.put(f"  完成，耗时 {elapsed}")

                        # Store last result path for single-file preview
                        result["last_report"] = result_path
                        result["last_output_dir"] = paper_output_dir

                    except Exception as e:
                        elapsed = f"{time.time() - t0:.1f}s"
                        progress_data.append([fname, paper_type, f"失败: {e}", elapsed])
                        log_q.put(f"  ERROR: {e}")

                log_q.put("\n精读处理完成。")
                result["done"] = True

        except InterruptedError:
            log_q.put("已被用户取消。")
        except Exception as e:
            log_q.put(f"ERROR: {e}")
            result["error"] = str(e)
        finally:
            log_q.put("__DONE__")

    threading.Thread(target=worker, daemon=True).start()

    # Stream updates
    while True:
        done = _drain_queue(log_q, log_lines)
        log_text = "\n".join(log_lines)
        df = pd.DataFrame(progress_data, columns=["文件名", "类型", "状态", "耗时"]) if progress_data else empty_df
        total = f"已处理: {len(progress_data)} 个文件"
        yield df, log_text, total, "", None
        if done:
            break
        time.sleep(0.5)

    # Final yield
    log_text = "\n".join(log_lines)
    df = pd.DataFrame(progress_data, columns=["文件名", "类型", "状态", "耗时"]) if progress_data else empty_df
    done_count = sum(1 for r in progress_data if r[2] == "完成")
    skip_count = sum(1 for r in progress_data if "跳过" in r[2])
    fail_count = sum(1 for r in progress_data if "失败" in r[2] or "FAIL" in r[2])
    total = f"总计: {len(progress_data)} | 完成: {done_count} | 跳过: {skip_count} | 失败: {fail_count}"

    # Single-file mode: read final report for preview
    preview = ""
    download_path = None
    if mode == "单文件":
        report_path = result.get("last_report", "")
        if report_path and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                preview = f.read(15000)
            if len(preview) >= 15000:
                preview += "\n\n... (truncated) ..."
            download_path = report_path
    else:
        # Folder mode: offer the output directory path
        last_dir = result.get("last_output_dir", "")
        if last_dir and os.path.isdir(last_dir):
            download_path = last_dir

    yield df, log_text, total, preview, download_path


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

def build_ui():
    with gr.Blocks(title="深度阅读助手") as app:
        gr.Markdown("# 深度阅读助手 Deep Reading Agent")
        gr.Markdown(f"**环境状态:** {_env_status()}")

        # ===== Tab 1: 论文筛选 =====
        with gr.Tab("论文筛选"):
            with gr.Row():
                with gr.Column(scale=1):
                    lf_file = gr.File(label="上传 WoS/CNKI 导出文件", file_types=[".txt"])
                    lf_mode = gr.Radio(
                        label="AI 评估模式",
                        choices=["无", "explorer (广泛探索)", "reviewer (严格评审)", "empiricist (实证导向)"],
                        value="无",
                    )
                    lf_topic = gr.Textbox(
                        label="研究主题（AI 模式必填）",
                        placeholder="例如：ESG与企业价值",
                    )
                    lf_year = gr.Textbox(label="最早年份（可选）", placeholder="例如：2015")
                    lf_keywords = gr.Textbox(
                        label="关键词过滤（逗号分隔，可选）",
                        placeholder="例如：DID, 回归, 面板数据",
                    )
                    lf_limit = gr.Slider(
                        label="AI 评估数量限制（0 = 全部）",
                        minimum=0, maximum=500, step=10, value=0,
                    )
                    lf_btn = gr.Button("开始筛选", variant="primary")

                    # 提示词编辑折叠面板
                    with gr.Accordion("编辑 AI 评估提示词", open=False):
                        lf_prompt_mode = gr.Dropdown(
                            label="选择模式",
                            choices=["explorer", "reviewer", "empiricist"],
                            value="explorer",
                        )
                        lf_prompt_load = gr.Button("加载提示词", size="sm")
                        lf_prompt_text = gr.Textbox(
                            label="提示词内容",
                            lines=15,
                            placeholder="点击「加载提示词」查看当前模式的提示词...",
                        )
                        lf_prompt_save = gr.Button("保存提示词", variant="secondary")
                        lf_prompt_status = gr.Textbox(label="状态", interactive=False, lines=1)

                with gr.Column(scale=2):
                    lf_log = gr.Textbox(label="运行日志", lines=10, interactive=False)
                    lf_df = gr.Dataframe(label="筛选结果", interactive=False)
                    lf_dl = gr.File(label="下载 Excel")

            # 提示词加载和保存函数
            def load_prompt(mode_name):
                prompt_dir = os.path.join(BASE_DIR, "prompts", "literature_filter")
                file_path = os.path.join(prompt_dir, f"{mode_name}.md")
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read(), f"已加载 {mode_name} 模式的提示词"
                return "", f"未找到提示词文件: {file_path}"

            def save_prompt(mode_name, content):
                if not content.strip():
                    return "错误：提示词内容不能为空"
                prompt_dir = os.path.join(BASE_DIR, "prompts", "literature_filter")
                os.makedirs(prompt_dir, exist_ok=True)
                file_path = os.path.join(prompt_dir, f"{mode_name}.md")
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return f"已保存 {mode_name} 模式的提示词"
                except Exception as e:
                    return f"保存失败: {e}"

            lf_prompt_load.click(
                fn=load_prompt,
                inputs=[lf_prompt_mode],
                outputs=[lf_prompt_text, lf_prompt_status],
            )
            lf_prompt_save.click(
                fn=save_prompt,
                inputs=[lf_prompt_mode, lf_prompt_text],
                outputs=[lf_prompt_status],
            )

            lf_btn.click(
                fn=run_literature_filter,
                inputs=[lf_file, lf_mode, lf_topic, lf_year, lf_keywords, lf_limit],
                outputs=[lf_log, lf_df, lf_dl],
            )

        # ===== Tab 2: 单文件精读 =====
        with gr.Tab("单文件精读"):
            with gr.Row():
                with gr.Column(scale=1):
                    fp_pdf = gr.File(label="上传 PDF 文件", file_types=[".pdf"])
                    _fp_choices = ["PaddleOCR (本地GPU)", "PaddleOCR (远程API)", "Legacy (pdfplumber)"]
                    _fp_default = "PaddleOCR (本地GPU)" if _LOCAL_POCR else "PaddleOCR (远程API)"
                    fp_method = gr.Radio(
                        label="提取方式",
                        choices=_fp_choices,
                        value=_fp_default,
                    )
                    fp_btn = gr.Button("开始精读", variant="primary")
                    fp_cancel = gr.Button("停止", variant="stop")

                with gr.Column(scale=2):
                    fp_stage = gr.Textbox(label="当前阶段", interactive=False)
                    fp_log = gr.Textbox(label="运行日志", lines=15, interactive=False)
                    fp_preview = gr.Markdown(label="最终报告预览")
                    fp_dl = gr.Textbox(label="结果目录", interactive=False)

            fp_btn.click(
                fn=run_full_pipeline,
                inputs=[fp_pdf, fp_method],
                outputs=[fp_stage, fp_log, fp_preview, fp_dl],
            )
            fp_cancel.click(fn=_request_cancel, outputs=[fp_stage])

        # ===== Tab 3: 批量精读 =====
        with gr.Tab("批量精读"):
            with gr.Row():
                with gr.Column(scale=1):
                    bp_folder = gr.Textbox(label="PDF 文件夹路径", placeholder=r"E:\pdf\002")
                    bp_validate = gr.Button("验证路径")
                    bp_status = gr.Textbox(label="文件夹状态", interactive=False)
                    bp_skip = gr.Checkbox(label="跳过已处理", value=True)
                    _bp_choices = ["PaddleOCR (本地GPU)", "PaddleOCR (远程API)", "Legacy (pdfplumber)"]
                    _bp_default = "PaddleOCR (本地GPU)" if _LOCAL_POCR else "PaddleOCR (远程API)"
                    bp_method = gr.Radio(
                        label="提取方式",
                        choices=_bp_choices,
                        value=_bp_default,
                    )
                    bp_btn = gr.Button("开始批量精读", variant="primary")
                    bp_cancel = gr.Button("停止", variant="stop")

                with gr.Column(scale=2):
                    bp_df = gr.Dataframe(
                        label="处理进度",
                        headers=["文件名", "类型", "状态", "耗时"],
                        interactive=False,
                    )
                    bp_log = gr.Textbox(label="当前日志", lines=10, interactive=False)
                    bp_total = gr.Textbox(label="总体进度", interactive=False)

            bp_validate.click(fn=validate_folder, inputs=[bp_folder], outputs=[bp_status])
            bp_btn.click(
                fn=run_batch,
                inputs=[bp_folder, bp_skip, bp_method],
                outputs=[bp_df, bp_log, bp_total],
            )
            bp_cancel.click(fn=_request_cancel, outputs=[bp_total])

        # ===== Tab 4: PDF 提取 =====
        with gr.Tab("PDF 提取"):
            with gr.Row():
                with gr.Column(scale=1):
                    ext_pdf = gr.File(label="上传 PDF 文件", file_types=[".pdf"])
                    ext_out_dir = gr.Textbox(label="输出目录", value="paddleocr_md")
                    ext_local_gpu = gr.Checkbox(
                        label="使用本地 PaddleOCR (GPU)",
                        value=_LOCAL_POCR,
                        interactive=_LOCAL_POCR,
                        info="需要 paddleocr + paddlex" if not _LOCAL_POCR else "已检测到 PPStructureV3",
                    )
                    ext_table = gr.Checkbox(label="表格识别", value=True)
                    ext_formula = gr.Checkbox(label="公式识别", value=True)
                    ext_chart = gr.Checkbox(label="图表解析", value=False)
                    ext_orient = gr.Checkbox(label="方向矫正", value=False)
                    ext_images = gr.Checkbox(label="下载图片", value=False)
                    ext_pages = gr.Slider(label="每批页数", minimum=5, maximum=50, step=5, value=10)
                    ext_no_fb = gr.Checkbox(label="禁用回退", value=False)
                    ext_legacy = gr.Checkbox(label="强制使用 pdfplumber", value=False)
                    ext_btn = gr.Button("开始提取", variant="primary")

                with gr.Column(scale=2):
                    ext_log = gr.Textbox(label="提取日志", lines=12, interactive=False)
                    ext_preview = gr.Markdown(label="Markdown 预览")
                    ext_meta = gr.Code(label="元数据 (JSON)", language="json")
                    ext_dl = gr.File(label="下载结果")

            ext_btn.click(
                fn=run_extraction,
                inputs=[ext_pdf, ext_out_dir, ext_local_gpu, ext_table, ext_formula, ext_chart,
                        ext_orient, ext_images, ext_pages, ext_no_fb, ext_legacy],
                outputs=[ext_log, ext_preview, ext_meta, ext_dl],
            )

        # ===== Tab 5: MD 文件精读 =====
        with gr.Tab("MD 文件精读"):
            with gr.Row():
                with gr.Column(scale=1):
                    md_mode = gr.Radio(
                        label="模式",
                        choices=["单文件", "文件夹"],
                        value="单文件",
                    )
                    md_file_row = gr.Row(visible=True)
                    with md_file_row:
                        md_file = gr.File(label="上传 MD 文件", file_types=[".md"])
                    md_folder_row = gr.Row(visible=False)
                    with md_folder_row:
                        md_folder = gr.Textbox(
                            label="MD 文件夹路径",
                            placeholder=r"E:\papers\paddleocr_md",
                        )
                        md_validate_btn = gr.Button("验证路径")
                    md_folder_status = gr.Textbox(label="文件夹状态", interactive=False, visible=False)
                    md_skip = gr.Checkbox(label="跳过已处理", value=True)
                    md_btn = gr.Button("开始精读", variant="primary")
                    md_cancel = gr.Button("停止", variant="stop")

                with gr.Column(scale=2):
                    md_df = gr.Dataframe(
                        label="处理进度",
                        headers=["文件名", "类型", "状态", "耗时"],
                        interactive=False,
                    )
                    md_log = gr.Textbox(label="当前日志", lines=12, interactive=False)
                    md_total = gr.Textbox(label="总体进度", interactive=False)
                    md_preview = gr.Markdown(label="最终报告预览")
                    md_dl = gr.File(label="下载结果")

            def _toggle_md_mode(mode):
                return (
                    gr.update(visible=(mode == "单文件")),
                    gr.update(visible=(mode == "文件夹")),
                    gr.update(visible=(mode == "文件夹")),
                )

            md_mode.change(
                fn=_toggle_md_mode,
                inputs=[md_mode],
                outputs=[md_file_row, md_folder_row, md_folder_status],
            )
            md_validate_btn.click(
                fn=validate_md_folder,
                inputs=[md_folder],
                outputs=[md_folder_status],
            )
            md_btn.click(
                fn=run_md_reading,
                inputs=[md_mode, md_file, md_folder, md_skip],
                outputs=[md_df, md_log, md_total, md_preview, md_dl],
            )
            md_cancel.click(fn=_request_cancel, outputs=[md_total])

    return app


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = build_ui()
    app.queue()
    app.launch(server_name="127.0.0.1", server_port=7860, theme=gr.themes.Soft())
