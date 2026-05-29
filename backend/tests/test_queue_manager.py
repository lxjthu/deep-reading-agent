from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.queue_manager import TaskQueueManager  # noqa: E402


class TestEnqueue(unittest.TestCase):
    """enqueue: 任务入队并返回排队信息"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_single_task_returns_position_1(self):
        info = self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.assertEqual(info["queue_position"], 1)

    def test_single_task_has_estimated_wait_fields(self):
        info = self.qm.enqueue("t1", user_id=1, task_type="quant")
        # position=1 且无运行任务 → 等待 0（立即可执行）
        self.assertEqual(info["estimated_wait_seconds"], 0)
        self.assertEqual(info["estimated_wait_minutes"], 0.0)
        self.assertIn("queue_position", info)

    def test_enqueue_returns_rounded_minutes(self):
        info = self.qm.enqueue("t1", user_id=1, task_type="quant")
        # estimated_wait_minutes 应该是 round(x, 1)，最多 1 位小数
        self.assertEqual(
            info["estimated_wait_minutes"],
            round(info["estimated_wait_seconds"] / 60, 1),
        )

    def test_multiple_tasks_positions_increment(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="qual")
        info3 = self.qm.enqueue("t3", user_id=3, task_type="quant")
        self.assertEqual(info3["queue_position"], 3)

    def test_enqueue_by_different_task_types(self):
        for task_type in ("quant", "qual", "long", "reference", "filter"):
            self.qm.enqueue(f"t-{task_type}", user_id=1, task_type=task_type)
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 5)


class TestDequeue(unittest.TestCase):
    """dequeue_next: 从队列取出下一个任务"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_dequeue_from_nonempty_returns_first(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="quant")
        entry = self.qm.dequeue_next()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["task_id"], "t1")

    def test_dequeue_from_empty_returns_none(self):
        entry = self.qm.dequeue_next()
        self.assertIsNone(entry)

    def test_dequeue_reduces_queue_length(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="quant")
        self.qm.dequeue_next()
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 1)

    def test_dequeue_preserves_fifo_order(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="quant")
        self.qm.enqueue("t3", user_id=3, task_type="quant")
        ids = []
        while True:
            entry = self.qm.dequeue_next()
            if entry is None:
                break
            ids.append(entry["task_id"])
        self.assertEqual(ids, ["t1", "t2", "t3"])


class TestMarkRunning(unittest.TestCase):
    """mark_running: 标记任务为运行中"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_mark_running_adds_to_running(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        info = self.qm.get_task_queue_info("t1")
        self.assertIsNotNone(info)
        self.assertEqual(info["status"], "running")

    def test_mark_running_removes_from_queue(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 0)
        self.assertEqual(status["running_count"], 1)

    def test_mark_running_task_not_in_queue_does_not_raise(self):
        self.qm.mark_running("nonexistent")
        status = self.qm.get_queue_status()
        self.assertEqual(status["running_count"], 1)


class TestMarkCompleted(unittest.TestCase):
    """mark_completed: 标记任务完成"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_mark_completed_removes_from_running(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        self.qm.mark_completed("t1")
        status = self.qm.get_queue_status()
        self.assertEqual(status["running_count"], 0)

    def test_mark_completed_updates_avg_duration(self):
        old_avg = self.qm._avg_duration["quant"]
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        self.qm.mark_completed("t1")
        new_avg = self.qm._avg_duration["quant"]
        # 移动平均: old * 0.8 + actual * 0.2，actual 很小（瞬间完成），所以 new_avg < old_avg
        self.assertLess(new_avg, old_avg)

    def test_mark_completed_nonexistent_does_not_raise(self):
        self.qm.mark_completed("nonexistent")


class TestRemoveQueued(unittest.TestCase):
    """remove_queued: remove tasks that never reached running state."""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_remove_queued_task_removes_from_queue(self):
        self.qm.enqueue("t1", user_id=1, task_type="long")
        self.qm.enqueue("t2", user_id=1, task_type="long")

        removed = self.qm.remove_queued("t1")

        self.assertTrue(removed)
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 1)
        self.assertEqual(status["queue_tasks"][0]["task_id"], "t2")

    def test_remove_queued_running_task_returns_false(self):
        self.qm.enqueue("t1", user_id=1, task_type="long")
        self.qm.mark_running("t1")

        removed = self.qm.remove_queued("t1")

        self.assertFalse(removed)
        self.assertEqual(self.qm.get_queue_status()["running_count"], 1)


class TestGetTaskQueueInfo(unittest.TestCase):
    """get_task_queue_info: 查询特定任务的队列信息"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_queued_task_returns_queued_status(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        info = self.qm.get_task_queue_info("t1")
        self.assertEqual(info["status"], "queued")
        self.assertEqual(info["queue_position"], 1)
        self.assertIn("estimated_wait_seconds", info)
        self.assertIn("waiting_seconds", info)

    def test_running_task_returns_running_status(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        info = self.qm.get_task_queue_info("t1")
        self.assertEqual(info["status"], "running")
        self.assertIn("running_seconds", info)

    def test_unknown_task_returns_none(self):
        info = self.qm.get_task_queue_info("nonexistent")
        self.assertIsNone(info)

    def test_completed_task_returns_none(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.mark_running("t1")
        self.qm.mark_completed("t1")
        info = self.qm.get_task_queue_info("t1")
        self.assertIsNone(info)


class TestGetQueueStatus(unittest.TestCase):
    """get_queue_status: 获取整体队列状态"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_empty_queue_status(self):
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 0)
        self.assertEqual(status["running_count"], 0)
        self.assertEqual(status["running_tasks"], [])
        self.assertEqual(status["queue_tasks"], [])

    def test_with_queued_and_running_tasks(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="qual")
        self.qm.mark_running("t1")
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 1)
        self.assertEqual(status["running_count"], 1)
        self.assertEqual(len(status["running_tasks"]), 1)
        self.assertEqual(len(status["queue_tasks"]), 1)

    def test_queue_tasks_have_position(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="quant")
        status = self.qm.get_queue_status()
        positions = [t["position"] for t in status["queue_tasks"]]
        self.assertEqual(positions, [1, 2])


class TestEstimateWait(unittest.TestCase):
    """_estimate_wait_seconds: 预估等待时间"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_position_zero_returns_zero(self):
        result = self.qm._estimate_wait_seconds(0, "quant")
        self.assertEqual(result, 0)

    def test_negative_position_returns_zero(self):
        result = self.qm._estimate_wait_seconds(-1, "quant")
        self.assertEqual(result, 0)

    def test_no_running_tasks(self):
        # position=1 → 前面 0 个任务 → 0
        result = self.qm._estimate_wait_seconds(1, "quant")
        self.assertEqual(result, 0)

    def test_no_running_position_3(self):
        # position=3 → 前面 2 个任务 * avg_duration
        avg = self.qm._avg_duration["quant"]
        result = self.qm._estimate_wait_seconds(3, "quant")
        self.assertEqual(result, int(2 * avg))

    def test_with_running_tasks(self):
        self.qm.enqueue("t0", user_id=0, task_type="quant")
        self.qm.mark_running("t0")
        avg = self.qm._avg_duration["quant"]
        # position=1, running_count=1
        # estimated = 0 * avg / 1 + avg/2 = avg/2
        result = self.qm._estimate_wait_seconds(1, "quant")
        self.assertEqual(result, int(avg / 2))

    def test_unknown_task_type_uses_default(self):
        result = self.qm._estimate_wait_seconds(2, "unknown_type")
        self.assertEqual(result, int(1 * 600))  # default 600s


class TestIntegration(unittest.TestCase):
    """端到端集成场景"""

    def setUp(self):
        self.qm = TaskQueueManager()

    def test_full_lifecycle(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="qual")
        self.qm.enqueue("t3", user_id=3, task_type="quant")

        info1 = self.qm.get_task_queue_info("t1")
        self.assertEqual(info1["status"], "queued")
        self.assertEqual(info1["queue_position"], 1)

        self.qm.mark_running("t1")
        info1 = self.qm.get_task_queue_info("t1")
        self.assertEqual(info1["status"], "running")

        info2 = self.qm.get_task_queue_info("t2")
        self.assertEqual(info2["status"], "queued")
        self.assertEqual(info2["queue_position"], 1)

        self.qm.mark_completed("t1")
        self.assertIsNone(self.qm.get_task_queue_info("t1"))

        entry = self.qm.dequeue_next()
        self.assertEqual(entry["task_id"], "t2")

    def test_multiple_concurrent_running(self):
        self.qm.enqueue("t1", user_id=1, task_type="quant")
        self.qm.enqueue("t2", user_id=2, task_type="qual")
        self.qm.mark_running("t1")
        self.qm.mark_running("t2")
        status = self.qm.get_queue_status()
        self.assertEqual(status["running_count"], 2)
        self.assertEqual(status["queue_length"], 0)


if __name__ == "__main__":
    unittest.main()
