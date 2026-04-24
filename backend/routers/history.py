import os
from datetime import datetime
from typing import List, Dict, Optional

import markdown
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deep_reading_results")
FILTER_DIR = os.path.join(RESULTS_DIR, "literature_filter")


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
    """Find file in results or filter directory"""
    filepath = os.path.join(RESULTS_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return filepath
    filepath = os.path.join(FILTER_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return filepath
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
        raise HTTPException(status_code=404, detail="File not found")
    
    os.remove(filepath)
    return {"success": True, "message": f"已删除 {filename}"}
