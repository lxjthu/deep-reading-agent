"""
Download Router - File downloads for analysis results
"""
import os
import urllib.parse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deep_reading_results")


@router.get("/{file_path:path}")
async def download_file(file_path: str):
    """
    Download a result file by path.
    Path should be URL-encoded.
    """
    # URL decode the path
    decoded_path = urllib.parse.unquote(file_path)
    
    # Security: ensure the path is within RESULTS_DIR
    # Handle both absolute and relative paths
    if os.path.isabs(decoded_path):
        # If absolute, check it's under RESULTS_DIR
        real_path = os.path.realpath(decoded_path)
        real_results_dir = os.path.realpath(RESULTS_DIR)
        if not real_path.startswith(real_results_dir):
            raise HTTPException(status_code=403, detail="Access denied")
        target_path = decoded_path
    else:
        # Relative path - resolve against RESULTS_DIR
        target_path = os.path.join(RESULTS_DIR, decoded_path)
    
    if not os.path.exists(target_path):
        # Also check if it's directly in results dir
        basename = os.path.basename(decoded_path)
        alt_path = os.path.join(RESULTS_DIR, basename)
        if os.path.exists(alt_path):
            target_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=400, detail="Not a file")
    
    # Determine MIME type by extension
    ext = os.path.splitext(target_path)[1].lower()
    media_types = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.md': 'text/markdown; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8',
        '.pdf': 'application/pdf',
        '.csv': 'text/csv; charset=utf-8',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        target_path,
        filename=os.path.basename(target_path),
        media_type=media_type
    )
