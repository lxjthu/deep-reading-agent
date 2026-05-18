"""
Deploy Router - Auto deploy from GitHub webhook
"""
import os
import subprocess
import hmac
import hashlib
import threading
import time
from fastapi import APIRouter, Depends, HTTPException, Header, Request

from auth.dependencies import current_user
from db.models import User

router = APIRouter()

DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET")
DEPLOY_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deploy.sh")


def is_packaged_app() -> bool:
    return os.environ.get("DRA_PACKAGED_APP") == "1"


def local_shutdown_allowed() -> bool:
    return is_packaged_app() and os.environ.get("DRA_ALLOW_LOCAL_SHUTDOWN") == "1"


def shutdown_process_later() -> None:
    time.sleep(0.5)
    os._exit(0)


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature (sha256=...)"""
    if not signature:
        return False
    expected = hmac.new(
        DEPLOY_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    # GitHub format: sha256=<hex>
    if signature.startswith("sha256="):
        signature = signature[7:]
    return hmac.compare_digest(expected, signature)


@router.post("/")
async def deploy(request: Request, x_hub_signature_256: str = Header(None)):
    """
    GitHub webhook endpoint for auto deployment.
    Triggered when online branch is pushed.
    """
    if not DEPLOY_SECRET:
        raise HTTPException(status_code=503, detail="DEPLOY_SECRET not configured")
    payload = await request.body()

    # Verify signature
    if not verify_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Run deploy script in background
    try:
        proc = subprocess.Popen(
            ["bash", DEPLOY_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(DEPLOY_SCRIPT)
        )
        return {
            "status": "deploy_triggered",
            "message": "Deployment started in background. Check logs for details."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deploy failed: {str(e)}")


@router.get("/runtime")
async def runtime_info():
    return {
        "packaged": is_packaged_app(),
        "can_shutdown": local_shutdown_allowed(),
    }


@router.post("/shutdown")
async def shutdown_app(user: User = Depends(current_user)):
    if not local_shutdown_allowed():
        raise HTTPException(status_code=403, detail="Local shutdown is disabled")
    threading.Thread(target=shutdown_process_later, daemon=True).start()
    return {"status": "shutting_down", "user": user.username}
