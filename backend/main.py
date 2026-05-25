"""
Deep Reading Agent - FastAPI Backend
"""
import os
import sys
import uuid
from pathlib import Path

# Ensure project root is in sys.path so backend/ modules can import new_architecture
sys.path.insert(0, str(Path(__file__).parent.parent))
from contextlib import asynccontextmanager
from typing import Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
env_path = os.environ.get('DEEP_READING_ENV', os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
load_dotenv(env_path)

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# Routers
from cleanup import cleanup_normal_user_data
from db import AsyncSessionLocal
from dimension_seed import ensure_default_dimension_sets
from prompt_service import ensure_builtin_prompt_templates
from template_seed import ensure_dimension_templates
from routers import admin, auth, upload, filter, reading, prompts, download, history, compare, deploy, library, references, data, dimensions, translation, cards, feedback
from routers import agent
from routers import library_chat

_UPLOAD_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_uploads")
_RESULTS_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "deep_reading_results")
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', _UPLOAD_DIR_DEFAULT)
RESULTS_DIR = os.environ.get('RESULTS_DIR', _RESULTS_DIR_DEFAULT)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


async def _recover_hanging_jobs() -> None:
    """Mark all pending/running jobs as failed after a server restart."""
    from sqlalchemy import update
    from db.models import Job

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Job)
            .where(Job.status.in_(["pending", "running"]))
            .values(
                status="failed",
                current_stage="后端重启，任务中断",
                error_msg="任务因服务器重启而中断，请重新提交。",
                progress=0,
            )
        )
        await db.commit()
        if result.rowcount:
            print(f"[startup] Recovered {result.rowcount} hanging jobs (pending/running -> failed)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("[startup] Deep Reading Agent API starting...")
    try:
        async with AsyncSessionLocal() as db:
            await ensure_builtin_prompt_templates(db)
    except Exception as exc:  # pragma: no cover - defensive startup logging
        print(f"[prompt-seed] skipped: {exc}")

    try:
        async with AsyncSessionLocal() as db:
            await ensure_default_dimension_sets(db)
    except Exception as exc:  # pragma: no cover - defensive startup logging
        print(f"[dimension-seed] skipped: {exc}")

    try:
        async with AsyncSessionLocal() as db:
            await ensure_dimension_templates(db)
    except Exception as exc:  # pragma: no cover - defensive startup logging
        print(f"[template-seed] skipped: {exc}")

    # Recover jobs left hanging from previous crash/restart
    try:
        await _recover_hanging_jobs()
    except Exception as exc:
        print(f"[job-recovery] skipped: {exc}")

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        cleanup_normal_user_data,
        "cron",
        hour=0,
        minute=0,
        id="cleanup-normal-users",
        replace_existing=True,
    )
    scheduler.start()
    app.state.cleanup_scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)
    print("[shutdown] Deep Reading Agent API shutting down...")


app = FastAPI(
    title="Deep Reading Agent API",
    description="学术论文深度精读系统后端 API",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS - allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(filter.router, prefix="/api/filter", tags=["Filter"])
app.include_router(reading.router, prefix="/api/reading", tags=["Reading"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["Prompts"])
app.include_router(download.router, prefix="/api/download", tags=["Download"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(compare.router, prefix="/api/compare", tags=["Compare"])
app.include_router(library.router, prefix="/api/library", tags=["Library"])
app.include_router(cards.router, prefix="/api/cards", tags=["Cards"])
app.include_router(references.router, prefix="/api/references", tags=["References"])
app.include_router(data.router, prefix="/api/data", tags=["Data"])
app.include_router(dimensions.router, prefix="/api/dimensions", tags=["Dimensions"])
app.include_router(translation.router, prefix="/api/translation", tags=["Translation"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
app.include_router(deploy.router, prefix="/api/deploy", tags=["Deploy"])
app.include_router(library_chat.router, prefix="/api/library/chat", tags=["LibraryChat"])


def get_project_root():
    """Get project root, compatible with PyInstaller."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent

project_root = get_project_root()
frontend_dist = project_root / "frontend" / "dist"


@app.get("/")
async def root():
    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html", media_type="text/html")
    return {
        "message": "Deep Reading Agent API",
        "version": "3.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# WebSocket endpoint for real-time progress
class WSManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
    
    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[task_id] = websocket
        print(f"WebSocket connected: {task_id}")
    
    def disconnect(self, task_id: str):
        if task_id in self.connections:
            del self.connections[task_id]
            print(f"WebSocket disconnected: {task_id}")
    
    async def send_progress(self, task_id: str, progress: int, stage: str):
        if task_id in self.connections:
            await self.connections[task_id].send_json({
                "type": "progress",
                "progress": progress,
                "stage": stage
            })
    
    async def send_log(self, task_id: str, message: str):
        if task_id in self.connections:
            await self.connections[task_id].send_json({
                "type": "log",
                "message": message,
            })
    
    async def send_result(self, task_id: str, result: dict):
        if task_id in self.connections:
            await self.connections[task_id].send_json({
                "type": "result",
                "data": result
            })
    
    async def send_error(self, task_id: str, message: str):
        if task_id in self.connections:
            await self.connections[task_id].send_json({
                "type": "error",
                "message": message
            })


ws_manager = WSManager()


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect(task_id, websocket)
    try:
        while True:
            # Keep connection alive, handle client messages if needed
            data = await websocket.receive_text()
            # Echo back or handle ping/pong
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id)
    except Exception as e:
        print(f"WebSocket error for {task_id}: {e}")
        ws_manager.disconnect(task_id)


if frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html", media_type="text/html")
    print(f"[static] Serving frontend from {frontend_dist}")
else:
    print(f"[static] Frontend dist not found at {frontend_dist}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
