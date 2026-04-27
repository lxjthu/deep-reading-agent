import os
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import markdown
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import PROJECT_ROOT, get_db
from db.models import Artifact, BibEntry, Job, JobBibEntry, User

router = APIRouter()

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deep_reading_results")
FILTER_DIR = os.path.join(RESULTS_DIR, "literature_filter")
SYNTHESIS_DIR = os.path.join(RESULTS_DIR, "synthesis")
os.makedirs(SYNTHESIS_DIR, exist_ok=True)


class SaveSynthesisRequest(BaseModel):
    dimension: str
    papers: List[str]
    content: str
    bib_entry_ids: List[str] = Field(default_factory=list)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def get_results_dir(user_id: int, job_id: str) -> Path:
    directory = Path(RESULTS_DIR) / str(user_id) / job_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_storage_path(absolute_path: Path) -> str:
    try:
        return absolute_path.relative_to(Path(RESULTS_DIR)).as_posix()
    except ValueError:
        return absolute_path.as_posix()


def _get_file_info(filepath: str) -> Dict:
    """Get file metadata"""
    stat = os.stat(filepath)
    return {
        "filename": os.path.basename(filepath),
        "path": filepath,
        "size": stat.st_size,
        "size_human": _human_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "type": _detect_type(filepath),
    }


def _human_size(size: int) -> str:
    """Convert bytes to human readable"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _detect_type(filepath: str) -> str:
    """Detect file type from name"""
    name = os.path.basename(filepath).lower()
    if "_long_context" in name:
        return "长文本精读"
    elif "_7step" in name:
        return "七步精读"
    elif "_4step" in name:
        return "四步精读"
    elif name.startswith("filtered_"):
        return "文献筛选"
    return "其他"


def _find_file(filename: str) -> Optional[str]:
    """Find file in results, filter, or synthesis directory"""
    filepath = os.path.join(RESULTS_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return filepath
    filepath = os.path.join(FILTER_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return filepath
    filepath = os.path.join(SYNTHESIS_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return filepath
    for root, _, files in os.walk(RESULTS_DIR):
        if filename in files:
            candidate = os.path.join(root, filename)
            if os.path.isfile(candidate):
                return candidate
    return None


def _list_files(directory: str) -> List[Dict]:
    """List all files in directory"""
    if not os.path.exists(directory):
        return []
    files = []
    for filename in sorted(os.listdir(directory), key=lambda f: os.path.getmtime(os.path.join(directory, f)), reverse=True):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            files.append(_get_file_info(filepath))
    return files


@router.get("/")
async def list_history():
    """List all history files (reading reports + filter results)"""
    reading_files = _list_files(RESULTS_DIR)
    filter_files = _list_files(FILTER_DIR)
    
    # Combine and sort by modified time (newest first)
    all_files = reading_files + filter_files
    all_files.sort(key=lambda x: x["modified"], reverse=True)
    
    return {
        "reading": reading_files,
        "filter": filter_files,
        "all": all_files,
    }


@router.get("/{filename}/preview", response_class=HTMLResponse)
async def preview_file(filename: str):
    """Preview a file as HTML (Markdown files rendered, Excel shows message)"""
    filepath = _find_file(filename)
    if not filepath:
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == '.md':
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        html_content = markdown.markdown(content, extensions=['tables', 'fenced_code'])
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{filename}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.8;
            color: #333;
            background: #fff;
        }}
        h1 {{ color: #059669; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
        h2 {{ color: #374151; margin-top: 30px; }}
        h3 {{ color: #4b5563; }}
        code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
        pre {{ background: #f9fafb; padding: 16px; border-radius: 8px; overflow-x: auto; }}
        pre code {{ background: none; padding: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        blockquote {{ border-left: 4px solid #059669; margin: 16px 0; padding-left: 16px; color: #4b5563; }}
        hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 30px 0; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }}
        .download-btn {{ background: #059669; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; }}
        .download-btn:hover {{ background: #047857; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📄 {filename}</h1>
        <a href="/api/download/{filename}" download class="download-btn">⬇ 下载</a>
    </div>
    {html_content}
</body>
</html>"""
    else:
        # For non-markdown files, show a simple page with download link
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{filename}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 100px auto; text-align: center; color: #374151; }}
        .icon {{ font-size: 64px; margin-bottom: 20px; }}
        .download-btn {{ background: #059669; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block; margin-top: 20px; }}
        .download-btn:hover {{ background: #047857; }}
    </style>
</head>
<body>
    <div class="icon">📎</div>
    <h1>{filename}</h1>
    <p>此文件类型不支持在线预览，请下载后查看。</p>
    <a href="/api/download/{filename}" download class="download-btn">⬇ 下载文件</a>
</body>
</html>"""


@router.delete("/{filename}")
async def delete_file(filename: str):
    """Delete a history file by filename"""
    filepath = _find_file(filename)
    if not filepath:
        # Also check synthesis directory
        synth_path = os.path.join(SYNTHESIS_DIR, filename)
        if os.path.exists(synth_path):
            os.remove(synth_path)
            return {"success": True, "message": f"已删除 {filename}"}
        raise HTTPException(status_code=404, detail="File not found")
    
    os.remove(filepath)
    return {"success": True, "message": f"已删除 {filename}"}


# === Synthesis History ===

@router.get("/synthesis/")
async def list_synthesis(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """List synthesis history for current user."""
    artifacts = (
        await db.execute(
            select(Artifact, Job)
            .join(Job, Job.id == Artifact.job_id)
            .where(
                Artifact.owner_user_id == user.id,
                Artifact.artifact_type == "synthesis_md",
                Job.job_type == "synthesis",
            )
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
        )
    ).all()
    files = []
    for artifact, job in artifacts:
        absolute_path = Path(RESULTS_DIR) / artifact.storage_path
        size = artifact.size_bytes or (absolute_path.stat().st_size if absolute_path.exists() else 0)
        modified_dt = artifact.created_at or job.created_at or utcnow_naive()
        modified = modified_dt.strftime("%Y-%m-%d %H:%M")
        files.append(
            {
                "filename": artifact.filename,
                "path": artifact.storage_path,
                "download_path": artifact.storage_path,
                "size": size,
                "size_human": _human_size(size),
                "modified": modified,
                "type": "AI综述",
                "job_id": job.id,
            }
        )
    return {"synthesis": files, "all": files}


@router.post("/synthesis/")
async def save_synthesis(
    req: SaveSynthesisRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a synthesis result as job + artifact."""
    members: list[BibEntry] = []
    seen: set[str] = set()

    if req.bib_entry_ids:
        for bib_entry_id in req.bib_entry_ids:
            bib_entry = await db.get(BibEntry, bib_entry_id)
            if bib_entry is None or bib_entry.owner_user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bib entry not found")
            if bib_entry.id in seen:
                continue
            seen.add(bib_entry.id)
            members.append(bib_entry)
    else:
        for paper_title in req.papers:
            bib_entry = (
                await db.execute(
                    select(BibEntry).where(
                        BibEntry.owner_user_id == user.id,
                        BibEntry.title == paper_title,
                    )
                )
            ).scalar_one_or_none()
            if bib_entry is None or bib_entry.id in seen:
                continue
            seen.add(bib_entry.id)
            members.append(bib_entry)

    if not members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="保存综述至少需要 1 篇文献。")

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            owner_user_id=user.id,
            job_type="synthesis",
            status="success",
            params_json=json.dumps({"dimension": req.dimension, "papers": req.papers}, ensure_ascii=False),
            progress=100,
            current_stage="完成",
            created_at=utcnow_naive(),
            started_at=utcnow_naive(),
            finished_at=utcnow_naive(),
            expires_at=compute_expires_at(user),
        )
    )
    for sort_order, bib_entry in enumerate(members):
        db.add(
            JobBibEntry(
                job_id=job_id,
                bib_entry_id=bib_entry.id,
                role="synthesis_member",
                sort_order=sort_order,
            )
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dim_safe = req.dimension.replace("/", "_").replace("\\", "_")[:30]
    filename = f"synthesis_{dim_safe}_{timestamp}.md"
    filepath = get_results_dir(user.id, job_id) / filename

    papers_str = ", ".join(req.papers[:3])
    if len(req.papers) > 3:
        papers_str += f" 等{len(req.papers)}篇"

    content = f"""# AI文献综述：{req.dimension}

**生成时间**：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**涉及文献**：{papers_str}  
**维度/步骤**：{req.dimension}

---

{req.content}
"""

    filepath.write_text(content, encoding="utf-8")
    storage_path = build_storage_path(filepath)
    db.add(
        Artifact(
            job_id=job_id,
            owner_user_id=user.id,
            artifact_type="synthesis_md",
            filename=filename,
            storage_path=storage_path,
            size_bytes=filepath.stat().st_size,
            expires_at=compute_expires_at(user),
        )
    )
    await db.commit()

    return {"success": True, "filename": filename, "path": storage_path, "job_id": job_id}
