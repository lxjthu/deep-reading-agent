"""
Deep Reading Agent - FastAPI Backend
"""
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional

from dotenv import load_dotenv
# Load .env from project root (parent of backend/)
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# Routers
from routers import upload, filter, reading, prompts, download, history

# Create upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_uploads")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "deep_reading_results")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 Deep Reading Agent API starting...")
    yield
    print("👋 Deep Reading Agent API shutting down...")


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
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(filter.router, prefix="/api/filter", tags=["Filter"])
app.include_router(reading.router, prefix="/api/reading", tags=["Reading"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["Prompts"])
app.include_router(download.router, prefix="/api/download", tags=["Download"])
app.include_router(history.router, prefix="/api/history", tags=["History"])


@app.get("/")
async def root():
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
