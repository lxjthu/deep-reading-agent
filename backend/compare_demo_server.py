#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比综述Demo独立后端服务
完全独立于主应用，运行在单独端口
"""
import os
import json
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Compare Demo API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")


def _load_json(filename: str):
    filepath = os.path.join(DOCS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/compare-demo/long")
async def get_long_demo_data():
    return _load_json("compare-long-demo-data.json")


@app.get("/api/compare-demo/qual")
async def get_qual_demo_data():
    return _load_json("compare-qual-demo-data.json")


@app.get("/api/compare-demo/quant")
async def get_quant_demo_data():
    return _load_json("compare-quant-demo-data.json")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "compare-demo"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
