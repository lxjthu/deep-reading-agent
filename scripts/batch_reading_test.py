# -*- coding: utf-8 -*-
"""
Batch reading test script
Upload PDF, run quant/qual/long reading, reference tracing
"""
import json
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Config
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# PDF directory
PDF_DIR = Path(r"D:\code\deepagent\deep-reading-agent-online\deep-reading-agent\_uploads\test_pdfs")

# Reading dimensions
QUANT_STEPS = ["Research Question", "Theory", "Identification", "Data", "Variables", "Assumptions", "Results"]
QUAL_STEPS = ["Context", "Theory", "Logic", "Value"]
LONG_DIMS = ["Research Question", "Theory", "Identification"]


def get_auth_token():
    """Get auth token"""
    try:
        # Use form data for OAuth2
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            data="username=admin&password=admin123",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token")
        else:
            print(f"  Login response: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"  Login error: {e}")
    return None


def upload_pdf(file_path, token=None):
    """Upload PDF"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/upload/",
            files={"file": (file_path.name, f, "application/pdf")},
            headers=headers
        )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  OK Upload success: file_id={data.get('file_id')}")
        return data
    else:
        print(f"  FAIL Upload failed: {resp.status_code} {resp.text[:200]}")
        return None


def start_quant_reading(file_id, token=None):
    """Start quant reading (7-step)"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.post(
        f"{BASE_URL}/api/reading/quant/start",
        json={
            "file_id": file_id,
            "extraction_method": "full",
            "api_key": API_KEY
        },
        headers=headers
    )

    if resp.status_code == 200:
        task_id = resp.json().get("task_id")
        print(f"  OK Quant reading started: task_id={task_id}")
        return task_id
    else:
        print(f"  FAIL Start failed: {resp.status_code} {resp.text[:200]}")
        return None


def start_qual_reading(file_id, token=None):
    """Start qual reading (4-step)"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.post(
        f"{BASE_URL}/api/reading/qual/start",
        json={
            "file_id": file_id,
            "extraction_method": "full",
            "api_key": API_KEY
        },
        headers=headers
    )

    if resp.status_code == 200:
        task_id = resp.json().get("task_id")
        print(f"  OK Qual reading started: task_id={task_id}")
        return task_id
    else:
        print(f"  FAIL Start failed: {resp.status_code} {resp.text[:200]}")
        return None


def start_long_reading(file_id, token=None):
    """Start long reading"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.post(
        f"{BASE_URL}/api/reading/long/start",
        json={
            "file_id": file_id,
            "analysis_dims": LONG_DIMS,
            "extraction_method": "full",
            "api_key": API_KEY
        },
        headers=headers
    )

    if resp.status_code == 200:
        task_id = resp.json().get("task_id")
        print(f"  OK Long reading started: task_id={task_id}")
        return task_id
    else:
        print(f"  FAIL Start failed: {resp.status_code} {resp.text[:200]}")
        return None


def start_reference_trace(bib_entry_id, token=None):
    """Start reference tracing"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.post(
        f"{BASE_URL}/api/references/entries/{bib_entry_id}/trace",
        json={"api_key": API_KEY},
        headers=headers
    )

    if resp.status_code == 200:
        task_id = resp.json().get("task_id")
        print(f"  OK Reference trace started: task_id={task_id}")
        return task_id
    else:
        print(f"  FAIL Start failed: {resp.status_code} {resp.text[:200]}")
        return None


def poll_task_status(task_id, task_type="reading", token=None):
    """Poll task status"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if task_type == "reading":
        url = f"{BASE_URL}/api/reading/task/{task_id}/status"
    elif task_type == "reference":
        url = f"{BASE_URL}/api/references/task/{task_id}/status"
    else:
        return None

    while True:
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                progress = data.get("progress", 0)
                stage = data.get("stage", "")

                print(f"\r  Progress: {progress}% - {stage}", end="", flush=True)

                if status in ["completed", "success"]:
                    print(f"\n  OK Task completed")
                    return data
                elif status in ["failed", "canceled"]:
                    print(f"\n  FAIL Task failed: {data.get('error', 'Unknown error')}")
                    return data
            time.sleep(2)
        except Exception as e:
            print(f"\n  FAIL Poll failed: {e}")
            return None


def process_pdf(pdf_path, token=None):
    """Process single PDF: upload + readings + reference trace"""
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*60}")

    # 1. Upload
    print("\n[1/5] Upload PDF...")
    upload_result = upload_pdf(pdf_path, token)
    if not upload_result:
        return None

    file_id = upload_result.get("file_id")
    bib_entry_id = upload_result.get("bib_entry_id")

    # 2. Quant reading
    print("\n[2/5] Quant reading (7-step)...")
    task_id = start_quant_reading(file_id, token)
    if task_id:
        poll_task_status(task_id, "reading", token)

    # 3. Qual reading
    print("\n[3/5] Qual reading (4-step)...")
    task_id = start_qual_reading(file_id, token)
    if task_id:
        poll_task_status(task_id, "reading", token)

    # 4. Long reading
    print("\n[4/5] Long reading...")
    task_id = start_long_reading(file_id, token)
    if task_id:
        poll_task_status(task_id, "reading", token)

    # 5. Reference trace
    if bib_entry_id:
        print("\n[5/5] Reference trace...")
        task_id = start_reference_trace(bib_entry_id, token)
        if task_id:
            poll_task_status(task_id, "reference", token)

    return {
        "file_name": pdf_path.name,
        "file_id": file_id,
        "bib_entry_id": bib_entry_id,
    }


def main():
    """Main function"""
    print("=" * 60)
    print("Batch Reading Test Script")
    print("=" * 60)

    # Check API Key
    if not API_KEY:
        print("Warning: DEEPSEEK_API_KEY not set")
        print("Please set: set DEEPSEEK_API_KEY=sk-xxx")
        return

    print(f"API Key: {API_KEY[:10]}...")

    # Get token
    print("\nGetting auth token...")
    token = get_auth_token()
    if token:
        print(f"  OK Token obtained")
    else:
        print("  WARN Token failed, using no-auth mode")

    # Get PDF list
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"\nError: No PDF files found in {PDF_DIR}")
        return

    print(f"\nFound {len(pdf_files)} PDF files:")
    for f in pdf_files:
        print(f"  - {f.name}")

    # Process each PDF
    results = []
    for pdf_path in pdf_files:
        result = process_pdf(pdf_path, token)
        if result:
            results.append(result)

    # Output summary
    print("\n" + "=" * 60)
    print("Processing complete! Summary:")
    print("=" * 60)
    for r in results:
        print(f"  {r['file_name']}")
        print(f"    file_id: {r['file_id']}")
        print(f"    bib_entry_id: {r['bib_entry_id']}")

    # Save results
    result_file = PDF_DIR / "processing_results.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {result_file}")


if __name__ == "__main__":
    main()
