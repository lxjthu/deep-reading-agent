from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.reading import _run_units_serially  # noqa: E402


class ReadingSerialExecutionTests(unittest.TestCase):
    def test_run_units_serially_preserves_input_order(self) -> None:
        calls: list[str] = []

        def analyze(unit: str):
            calls.append(unit)
            return unit, f"answer-{unit}", None

        results, cancelled = _run_units_serially(
            ["研究问题", "理论框架", "识别策略"],
            analyze,
        )

        self.assertFalse(cancelled)
        self.assertEqual(calls, ["研究问题", "理论框架", "识别策略"])
        self.assertEqual(
            results,
            {
                "研究问题": "answer-研究问题",
                "理论框架": "answer-理论框架",
                "识别策略": "answer-识别策略",
            },
        )

    def test_run_units_serially_stops_on_cancelled_result(self) -> None:
        calls: list[str] = []

        def analyze(unit: str):
            calls.append(unit)
            if unit == "理论框架":
                return unit, None, "cancelled"
            return unit, f"answer-{unit}", None

        results, cancelled = _run_units_serially(
            ["研究问题", "理论框架", "识别策略"],
            analyze,
        )

        self.assertTrue(cancelled)
        self.assertEqual(calls, ["研究问题", "理论框架"])
        self.assertEqual(results, {"研究问题": "answer-研究问题"})

    def test_run_units_serially_reports_progress_after_each_success(self) -> None:
        progress: list[tuple[int, int, str, str | None]] = []

        def analyze(unit: str):
            return unit, f"answer-{unit}", None

        def on_progress(done: int, total: int, key: str, err: str | None) -> None:
            progress.append((done, total, key, err))

        results, cancelled = _run_units_serially(
            ["A", "B"],
            analyze,
            on_progress=on_progress,
        )

        self.assertFalse(cancelled)
        self.assertEqual(results, {"A": "answer-A", "B": "answer-B"})
        self.assertEqual(progress, [(1, 2, "A", None), (2, 2, "B", None)])

    def test_empty_dimension_retry_runs_serially(self) -> None:
        from routers import reading

        task_id = "serial-retry-task"
        reading.tasks[task_id] = {
            "status": "running",
            "logs": [],
        }
        calls: list[str] = []

        def retry_fn(key: str) -> str:
            calls.append(key)
            return f"这是重试后恢复的 {key} 维度结果，长度足够，并且包含中文标点。"

        try:
            results = reading._check_and_retry_empty_dimensions(
                {"A": "", "B": "", "C": "这是一段已经足够长且包含中文标点的正常精读结果。它不应该进入重试流程。"},
                task_id,
                retry_fn,
                max_retries=1,
            )
        finally:
            reading.tasks.pop(task_id, None)

        self.assertEqual(calls, ["A", "B"])
        self.assertEqual(results["A"], "这是重试后恢复的 A 维度结果，长度足够，并且包含中文标点。")
        self.assertEqual(results["B"], "这是重试后恢复的 B 维度结果，长度足够，并且包含中文标点。")
        self.assertEqual(results["C"], "这是一段已经足够长且包含中文标点的正常精读结果。它不应该进入重试流程。")


if __name__ == "__main__":
    unittest.main()
