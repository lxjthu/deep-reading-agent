from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TaskQueueManager:
    """任务队列管理器"""

    def __init__(self):
        self._queue: list[dict] = []
        self._running: dict[str, dict] = {}
        self._avg_duration: dict[str, float] = {
            "quant": 600,
            "qual": 480,
            "long": 720,
            "reference": 300,
            "filter": 180,
        }

    def enqueue(self, task_id: str, user_id: int, task_type: str) -> dict:
        entry = {
            "task_id": task_id,
            "user_id": user_id,
            "task_type": task_type,
            "created_at": datetime.now(),
        }
        self._queue.append(entry)

        position = self._get_position(task_id)
        estimated_wait = self._estimate_wait_seconds(position, task_type)

        logger.info(
            f"Task {task_id} enqueued at position {position}, "
            f"estimated wait: {estimated_wait}s"
        )

        return {
            "queue_position": position,
            "estimated_wait_seconds": estimated_wait,
            "estimated_wait_minutes": round(estimated_wait / 60, 1),
        }

    def dequeue_next(self) -> Optional[dict]:
        if self._queue:
            return self._queue.pop(0)
        return None

    def mark_running(self, task_id: str):
        self._running[task_id] = {"start_time": datetime.now()}
        self._queue = [t for t in self._queue if t["task_id"] != task_id]

    def mark_completed(self, task_id: str):
        if task_id in self._running:
            start_time = self._running[task_id]["start_time"]
            duration = (datetime.now() - start_time).total_seconds()

            task_type = self._running[task_id].get("task_type", "quant")
            if task_type in self._avg_duration:
                old_avg = self._avg_duration[task_type]
                self._avg_duration[task_type] = old_avg * 0.8 + duration * 0.2

            del self._running[task_id]
            logger.info(f"Task {task_id} completed, duration: {duration}s")

    def _get_position(self, task_id: str) -> int:
        for i, entry in enumerate(self._queue):
            if entry["task_id"] == task_id:
                return i + 1
        return 0

    def _estimate_wait_seconds(self, position: int, task_type: str) -> int:
        if position <= 0:
            return 0

        avg_duration = self._avg_duration.get(task_type, 600)
        running_count = len(self._running)
        avg_remaining = avg_duration / 2

        if running_count > 0:
            estimated = (position - 1) * avg_duration / max(running_count, 1) + avg_remaining
        else:
            estimated = (position - 1) * avg_duration

        return int(estimated)

    def get_queue_status(self) -> dict:
        return {
            "queue_length": len(self._queue),
            "running_count": len(self._running),
            "running_tasks": [
                {
                    "task_id": tid,
                    "start_time": info["start_time"].isoformat(),
                    "running_seconds": int(
                        (datetime.now() - info["start_time"]).total_seconds()
                    ),
                }
                for tid, info in self._running.items()
            ],
            "queue_tasks": [
                {
                    "task_id": entry["task_id"],
                    "position": i + 1,
                    "task_type": entry["task_type"],
                    "waiting_seconds": int(
                        (datetime.now() - entry["created_at"]).total_seconds()
                    ),
                }
                for i, entry in enumerate(self._queue)
            ],
        }

    def get_task_queue_info(self, task_id: str) -> Optional[dict]:
        position = self._get_position(task_id)
        if position > 0:
            entry = self._queue[position - 1]
            estimated_wait = self._estimate_wait_seconds(position, entry["task_type"])
            return {
                "status": "queued",
                "queue_position": position,
                "estimated_wait_seconds": estimated_wait,
                "estimated_wait_minutes": round(estimated_wait / 60, 1),
                "waiting_seconds": int(
                    (datetime.now() - entry["created_at"]).total_seconds()
                ),
            }

        if task_id in self._running:
            start_time = self._running[task_id]["start_time"]
            return {
                "status": "running",
                "running_seconds": int(
                    (datetime.now() - start_time).total_seconds()
                ),
            }

        return None


task_queue = TaskQueueManager()
