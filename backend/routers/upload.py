"""
Upload Router - File upload handling
"""
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file (PDF or TXT)
    Returns file_id for subsequent API calls
    """
    # Validate file type
    allowed_extensions = {'.pdf', '.txt'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}"
        )
    
    # Generate unique file_id
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    try:
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Save original filename mapping
        meta_path = os.path.join(UPLOAD_DIR, f"{file_id}.meta")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(file.filename)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        return {
            "success": True,
            "file_id": file_id,
            "filename": file.filename,
            "size": file_size,
            "type": "pdf" if file_ext == '.pdf' else 'txt',
            "message": "上传成功"
        }
    
    except Exception as e:
        # Clean up on error
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{file_id}/info")
async def get_file_info(file_id: str):
    """Get uploaded file info"""
    # Find file by file_id prefix
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id):
            file_path = os.path.join(UPLOAD_DIR, filename)
            return {
                "file_id": file_id,
                "filename": filename,
                "size": os.path.getsize(file_path),
                "exists": True
            }
    
    raise HTTPException(status_code=404, detail="File not found")


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """Delete uploaded file"""
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id):
            file_path = os.path.join(UPLOAD_DIR, filename)
            os.remove(file_path)
            return {"success": True, "message": "File deleted"}
    
    raise HTTPException(status_code=404, detail="File not found")
