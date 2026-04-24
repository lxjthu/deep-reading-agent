"""
Filter Router - Literature filtering with AI scoring
"""
import os
import sys
import uuid
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add parent directory to path to import existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()

# In-memory task store (replace with Redis in production)
tasks = {}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_uploads")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "deep_reading_results", "literature_filter")
os.makedirs(RESULTS_DIR, exist_ok=True)


class FilterRequest(BaseModel):
    file_id: str
    mode: str  # explorer, reviewer, empiricist
    topic: str
    min_year: int = 0
    keywords: Optional[str] = None
    api_key: Optional[str] = None


def get_file_path(file_id: str) -> Optional[str]:
    """Find uploaded file by file_id"""
    if not os.path.exists(UPLOAD_DIR):
        return None
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id):
            return os.path.join(UPLOAD_DIR, filename)
    return None


def run_filter_task(task_id: str, file_path: str, mode: str, topic: str, min_year: int, keywords: Optional[str], api_key: Optional[str] = None):
    """Run filter pipeline in background thread. api_key is REQUIRED."""
    try:
        # Validate API key first
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始筛选。")
        
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "解析文献题录..."
        
        from parsers import get_parser
        from smart_literature_filter import filter_literature, AIEvaluator, PromptManager
        
        # 1. Parse file
        parser = get_parser(file_path)
        if not parser:
            raise ValueError("不支持的文件格式")
        
        parser.parse()
        df = parser.to_dataframe()
        
        tasks[task_id]["progress"] = 25
        tasks[task_id]["stage"] = f"解析完成: {len(df)} 篇文献"
        tasks[task_id]["logs"].append(f"✓ 解析完成: {len(df)} 篇文献")
        
        # 2. Basic filtering
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
        df = filter_literature(df, min_year=min_year, keywords=kw_list)
        
        tasks[task_id]["progress"] = 40
        tasks[task_id]["stage"] = f"过滤后: {len(df)} 篇文献"
        tasks[task_id]["logs"].append(f"✓ 过滤后: {len(df)} 篇文献")
        
        if df.empty:
            raise ValueError("过滤后无匹配文献")
        
        # 3. AI Evaluation
        tasks[task_id]["progress"] = 50
        tasks[task_id]["stage"] = "AI 评估中..."
        
        evaluator = AIEvaluator(api_key=api_key)
        prompt_template = PromptManager.load_prompt(mode)
        
        ai_results = evaluator.evaluate_batch(df, prompt_template, topic)
        
        tasks[task_id]["progress"] = 80
        tasks[task_id]["stage"] = f"AI 评估完成: {len(ai_results)} 篇"
        tasks[task_id]["logs"].append(f"✓ AI 评估完成: {len(ai_results)} 篇")
        
        # 4. Export
        import pandas as pd
        ai_df = pd.DataFrame(ai_results)
        if not ai_df.empty and "original_index" in ai_df.columns:
            ai_df.set_index("original_index", inplace=True)
            df = df.join(ai_df, how="left")
            if "score" in df.columns:
                df["score"] = pd.to_numeric(df["score"], errors="coerce")
                df = df.sort_values(by="score", ascending=False)
        
        out_path = os.path.join(RESULTS_DIR, f"filtered_{mode}_{task_id}.xlsx")
        display_cols = ["Title", "Authors", "Journal", "Year", "score", "reason"]
        final_cols = [c for c in display_cols if c in df.columns]
        df_display = df[final_cols].copy()
        df_display.to_excel(out_path, index=False)
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append(f"✓ 已导出: {os.path.basename(out_path)}")
        tasks[task_id]["result"] = {
            "output_path": out_path,
            "row_count": len(df_display),
            "preview": df_display.head(20).to_dict('records')
        }
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ 错误: {str(e)}")
        tasks[task_id]["error"] = str(e)


@router.post("/start")
async def start_filter(request: FilterRequest):
    """Start literature filtering task"""
    # Validate mode
    if request.mode not in ("explorer", "reviewer", "empiricist"):
        raise HTTPException(status_code=400, detail="Invalid mode")
    
    # Validate topic
    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")
    
    # Find file
    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Create task
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "type": "filter",
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None
    }
    
    # Start background thread
    thread = threading.Thread(
        target=run_filter_task,
        args=(task_id, file_path, request.mode, request.topic, request.min_year, request.keywords, request.api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """Get task status"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel task (best effort)"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    tasks[task_id]["status"] = "cancelled"
    tasks[task_id]["stage"] = "已取消"
    return {"success": True}
