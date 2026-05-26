"""Global DeepSeek API concurrency limiter.

All DeepSeek API calls should acquire this semaphore before sending requests.
This prevents hitting the DeepSeek rate limit (500 concurrent) when multiple
tasks run in parallel (e.g. batch reading × dimension concurrency).

Usage:
    from services.deepseek_limiter import deepseek_semaphore

    with deepseek_semaphore:
        resp = client.chat.completions.create(...)

The semaphore value (100) is conservative:
  - 10 papers × 12 dims = 120 max from batch reading
  - Plus AI synthesis, translation, etc.
  - Well under the 500 limit.
"""
import threading

DEEPSEEK_MAX_CONCURRENT = 100
deepseek_semaphore = threading.Semaphore(DEEPSEEK_MAX_CONCURRENT)
