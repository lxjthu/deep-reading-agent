"""
Reading Router - Long context / Quant / Qual analysis
"""
import os
import sys
import uuid
import threading
import time
import re
from typing import Optional

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_uploads")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deep_reading_results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Prompts directory
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")

QUANT_PROMPT_FILES = {
    "第一步：核心贡献识别": "quant_analysis/step_1_overview.md",
    "第二步：理论框架评估": "quant_analysis/step_2_theory.md",
    "第三步：方法论批判": "quant_analysis/step_3_data.md",
    "第四步：实证结果解读": "quant_analysis/step_4_vars.md",
    "第五步：局限性分析": "quant_analysis/step_5_identification.md",
    "第六步：实践意义": "quant_analysis/step_6_results.md",
    "第七步：未来方向": "quant_analysis/step_7_critique.md",
}

QUAL_PROMPT_FILES = {
    "第一步：背景与问题": "qual_analysis/L1_Context_Prompt.md",
    "第二步：理论视角": "qual_analysis/L2_Theory_Prompt.md",
    "第三步：逻辑与证据": "qual_analysis/L3_Logic_Prompt.md",
    "第四步：价值与启示": "qual_analysis/L4_Value_Prompt.md",
}

def load_prompt_file(relative_path: str) -> str:
    """Load a prompt file from prompts directory and append no-greeting instruction"""
    path = os.path.join(PROMPTS_DIR, relative_path)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Append no-greeting instruction if not already present
        if "寒暄" not in content and "客套" not in content:
            content += "\n\n# 重要\n直接输出分析内容，不要\"好的\"\"我将\"\"作为...\"等客套开场白。"
        return content
    # Fallback: return a simple prompt
    return "请分析这个维度。直接输出分析内容，不要客套开场白。"


# In-memory task store
tasks = {}


class LongContextRequest(BaseModel):
    file_id: str
    analysis_dims: list[str]  # e.g. ["研究问题", "理论框架", "识别策略"]
    custom_question: Optional[str] = None
    extraction_method: str = "full"  # full or preview
    api_key: Optional[str] = None


def get_file_path(file_id: str) -> Optional[str]:
    if not os.path.exists(UPLOAD_DIR):
        return None
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id) and not filename.endswith('.meta'):
            return os.path.join(UPLOAD_DIR, filename)
    return None


def get_original_filename(file_path: str) -> str:
    """Get original uploaded filename from .meta file"""
    file_id = os.path.splitext(os.path.basename(file_path))[0]
    meta_path = os.path.join(UPLOAD_DIR, f"{file_id}.meta")
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    # Fallback: use file path basename
    return os.path.splitext(os.path.basename(file_path))[0]


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem"""
    # Remove extension
    name = os.path.splitext(name)[0]
    # Replace invalid chars
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


def run_long_context_task(task_id: str, file_path: str, analysis_dims: list, custom_question: Optional[str], extraction_method: str, api_key: Optional[str] = None):
    """Run long context analysis in background thread. api_key is REQUIRED."""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[阶段 1/3] 提取 PDF...")
        
        # Validate API key first
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        final_api_key = api_key.strip()
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(final_api_key)
        
        # 3. Read PDF text and create cache
        tasks[task_id]["progress"] = 30
        tasks[task_id]["stage"] = "读取论文内容..."
        tasks[task_id]["logs"].append("[阶段 2/3] 读取论文内容...")
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
        metadata = PaperMetadata(
            title=os.path.basename(file_path),
            authors=[],
            source="upload"
        )
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["progress"] = 30
        tasks[task_id]["stage"] = "PDF 提取完成"
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        # 2. Build analysis plan
        tasks[task_id]["progress"] = 40
        tasks[task_id]["stage"] = "构建分析计划..."
        
        tasks[task_id]["progress"] = 50
        tasks[task_id]["stage"] = "执行多维分析..."
        
        # Build questions from dimensions
        from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS
        
        results = {}
        total_dims = len(analysis_dims)
        for i, dim_key in enumerate(analysis_dims):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            # Map Chinese dim name to key
            dim_map = {
                "研究问题": "overview",
                "理论框架": "theory", 
                "数据与方法": "methodology",
                "识别策略": "methodology",
                "结果解读": "results",
                "稳健性": "results",
                "局限与拓展": "limitations",
                "实践意义": "implications",
                "跨文献对比": "comparison",
                "未来方向": "future",
            }
            mapped_key = dim_map.get(dim_key, "overview")
            
            tasks[task_id]["stage"] = f"分析维度 {i+1}/{total_dims}: {dim_key}..."
            tasks[task_id]["logs"].append(f"[{i+1}/{total_dims}] {dim_key}...")
            
            try:
                answer = engine.analyze_dimension(mapped_key)
                results[dim_key] = answer
                tasks[task_id]["logs"].append(f"✓ {dim_key} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {dim_key} 出错: {str(e)[:80]}")
                results[dim_key] = f"[分析出错: {str(e)[:200]}]"
        
        # 4. Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        report_path = os.path.join(RESULTS_DIR, f"{safe_name}_long_context.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 长文本精读报告\n\n")
            f.write(f"## 分析维度\n\n")
            for dim_key, answer in results.items():
                f.write(f"### {dim_key}\n\n")
                f.write(f"{answer}\n\n---\n\n")
        
        # Summary
        preview_parts = []
        for dim_key, answer in results.items():
            preview_parts.append(f"## {dim_key}\n{answer[:500]}...")
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 全部完成！")
        tasks[task_id]["result"] = {
            "output_path": report_path,
            "preview": "\n\n".join(preview_parts[:3]),
            "dimensions": list(results.keys()),
        }
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)


def run_quant_task(task_id: str, file_path: str, api_key: Optional[str] = None):
    """Run 7-step quantitative analysis. api_key is REQUIRED."""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[步骤 1/7] 提取 PDF...")
        
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key.strip())
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        # 7 steps with full prompts from prompts directory
        steps = [
            ("第一步：核心贡献识别", "quant_analysis/step_1_overview.md"),
            ("第二步：理论框架评估", "quant_analysis/step_2_theory.md"),
            ("第三步：方法论批判", "quant_analysis/step_3_data.md"),
            ("第四步：实证结果解读", "quant_analysis/step_4_vars.md"),
            ("第五步：局限性分析", "quant_analysis/step_5_identification.md"),
            ("第六步：实践意义", "quant_analysis/step_6_results.md"),
            ("第七步：未来方向", "quant_analysis/step_7_critique.md"),
        ]
        
        results = {}
        for i, (step_name, prompt_file) in enumerate(steps):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            tasks[task_id]["progress"] = 15 + i * 12
            tasks[task_id]["stage"] = step_name
            tasks[task_id]["logs"].append(f"[{i+1}/7] {step_name}...")
            
            try:
                prompt_content = load_prompt_file(prompt_file)
                answer = engine.ask(prompt_content)
                results[step_name] = answer
                tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(e)[:80]}")
                results[step_name] = f"[分析出错: {str(e)[:200]}]"
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成七步精读报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        report_path = os.path.join(RESULTS_DIR, f"{safe_name}_7step.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 七步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:3]])
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 七步精读全部完成！")
        tasks[task_id]["result"] = {
            "output_path": report_path,
            "preview": preview,
            "steps": list(results.keys()),
        }
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)


def run_qual_task(task_id: str, file_path: str, api_key: Optional[str] = None):
    """Run 4-step qualitative analysis. api_key is REQUIRED."""
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[步骤 1/4] 提取 PDF...")
        
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key.strip())
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        # 4 steps with full prompts from prompts directory
        steps = [
            ("第一步：背景与问题", "qual_analysis/L1_Context_Prompt.md"),
            ("第二步：理论视角", "qual_analysis/L2_Theory_Prompt.md"),
            ("第三步：逻辑与证据", "qual_analysis/L3_Logic_Prompt.md"),
            ("第四步：价值与启示", "qual_analysis/L4_Value_Prompt.md"),
        ]
        
        results = {}
        for i, (step_name, prompt_file) in enumerate(steps):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            tasks[task_id]["progress"] = 20 + i * 20
            tasks[task_id]["stage"] = step_name
            tasks[task_id]["logs"].append(f"[{i+1}/4] {step_name}...")
            
            try:
                prompt_content = load_prompt_file(prompt_file)
                answer = engine.ask(prompt_content)
                results[step_name] = answer
                tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(e)[:80]}")
                results[step_name] = f"[分析出错: {str(e)[:200]}]"
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成四步精读报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        report_path = os.path.join(RESULTS_DIR, f"{safe_name}_4step.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 四步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:2]])
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 四步精读全部完成！")
        tasks[task_id]["result"] = {
            "output_path": report_path,
            "preview": preview,
            "steps": list(results.keys()),
        }
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)


@router.post("/long/start")
async def start_long_context(request: LongContextRequest):
    """Start long context analysis"""
    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "type": "long_context",
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None
    }
    
    thread = threading.Thread(
        target=run_long_context_task,
        args=(task_id, file_path, request.analysis_dims, request.custom_question, request.extraction_method, request.api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.post("/quant/start")
async def start_quant(request: dict):
    """Start quantitative (7-step) analysis"""
    file_id = request.get("file_id")
    api_key = request.get("api_key")
    file_path = get_file_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "type": "quant",
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None
    }
    
    thread = threading.Thread(
        target=run_quant_task,
        args=(task_id, file_path, api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.post("/qual/start")
async def start_qual(request: dict):
    """Start qualitative (4-step) analysis"""
    file_id = request.get("file_id")
    api_key = request.get("api_key")
    file_path = get_file_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "type": "qual",
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None
    }
    
    thread = threading.Thread(
        target=run_qual_task,
        args=(task_id, file_path, api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id]["status"] = "cancelled"
    tasks[task_id]["stage"] = "已取消"
    return {"success": True}
