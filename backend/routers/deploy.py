"""
Deploy Router - Auto deploy from GitHub webhook
"""
import os
import subprocess
import hmac
import hashlib
from fastapi import APIRouter, HTTPException, Header, Request

router = APIRouter()

DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET", "39e8df50fa0d1b1995641064c64899f4")
DEPLOY_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deploy.sh")


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
