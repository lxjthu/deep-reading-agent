# -*- coding: utf-8 -*-
"""
对比综述 Demo 后端服务 — 端口 8001
提供三个 API 端点，分别读取三份 JSON demo 数据。
启动: python backend/compare_demo_server.py
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

app = FastAPI(title="Compare Demo Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
FRONTEND_PUBLIC = Path(__file__).resolve().parent.parent / "frontend" / "public"

DATA_FILES = {
    "long": "compare-long-demo-data.json",
    "qual": "compare-qual-demo-data.json",
    "quant": "compare-quant-demo-data.json",
}

_cache: dict = {}


def _load(mode: str) -> dict:
    if mode not in _cache:
        fp = DOCS_DIR / DATA_FILES[mode]
        with open(fp, "r", encoding="utf-8") as f:
            _cache[mode] = json.load(f)
    return _cache[mode]


# ── API ─────────────────────────────────────────────────────────────────

@app.get("/api/compare-demo/long")
def get_long():
    return _load("long")


@app.get("/api/compare-demo/qual")
def get_qual():
    return _load("qual")


@app.get("/api/compare-demo/quant")
def get_quant():
    return _load("quant")


# ── Static HTML serving ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    fp = FRONTEND_PUBLIC / "compare_index.html"
    if fp.exists():
        return FileResponse(fp, media_type="text/html; charset=utf-8")
    return HTMLResponse("<h1>Compare Demo</h1><p>compare_index.html not found</p>")


@app.get("/compare_long.html", response_class=HTMLResponse)
def serve_long():
    return FileResponse(FRONTEND_PUBLIC / "compare_long.html", media_type="text/html; charset=utf-8")


@app.get("/compare_4step.html", response_class=HTMLResponse)
def serve_4step():
    return FileResponse(FRONTEND_PUBLIC / "compare_4step.html", media_type="text/html; charset=utf-8")


@app.get("/compare_7step.html", response_class=HTMLResponse)
def serve_7step():
    return FileResponse(FRONTEND_PUBLIC / "compare_7step.html", media_type="text/html; charset=utf-8")


if __name__ == "__main__":
    print("Compare Demo Server starting on http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
