import tempfile
import unittest
from pathlib import Path

from backend.models.analysis_task_models import AnalysisTaskStatus
from backend.services import analysis_task_service as service


class AnalysisTaskServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = service.DATA_DIR
        self.original_tasks_dir = service.TASKS_DIR
        self.original_task_cache_dir = service.TASK_CACHE_DIR
        root = Path(self.temp_dir.name)
        service.DATA_DIR = root / "data"
        service.TASKS_DIR = service.DATA_DIR / "analysis_tasks"
        service.TASK_CACHE_DIR = service.DATA_DIR / "task_cache"

    def tearDown(self):
        service.DATA_DIR = self.original_data_dir
        service.TASKS_DIR = self.original_tasks_dir
        service.TASK_CACHE_DIR = self.original_task_cache_dir
        self.temp_dir.cleanup()

    def test_create_task_initializes_pending_task_with_checkpoint(self):
        task = service.create_task("测试查询", "analysis_test_1")
        loaded = service.load_task(task.id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.status, AnalysisTaskStatus.PENDING)
        self.assertEqual(loaded.query, "测试查询")
        self.assertEqual(loaded.current_step, 0)
        self.assertEqual(loaded.max_steps, 15)
        self.assertEqual(loaded.events, [])
        self.assertEqual(loaded.error, "")
        self.assertIsNotNone(loaded.checkpoint)
        self.assertNotEqual(loaded.created_at, "")
        self.assertNotEqual(loaded.updated_at, "")

    def test_task_status_transitions_keep_current_observable_fields(self):
        task = service.create_task("测试查询", "analysis_test_2")

        running = service.mark_task_running(task)
        self.assertEqual(running.status, AnalysisTaskStatus.RUNNING)
        self.assertFalse(running.pause_requested)
        self.assertEqual(running.error, "")
        self.assertNotEqual(running.started_at, "")

        pause_requested = service.request_task_pause(running)
        self.assertEqual(pause_requested.status, AnalysisTaskStatus.RUNNING)
        self.assertTrue(pause_requested.pause_requested)
        self.assertEqual(pause_requested.error, "已收到暂停请求，将在当前SOP环节完成后暂停")

        paused = service.mark_task_paused(pause_requested, "人工暂停")
        self.assertEqual(paused.status, AnalysisTaskStatus.PAUSED)
        self.assertFalse(paused.pause_requested)
        self.assertEqual(paused.error, "人工暂停")
        self.assertEqual(paused.finished_at, "")

        pending = service.mark_task_pending(paused)
        self.assertEqual(pending.status, AnalysisTaskStatus.PENDING)
        self.assertFalse(pending.pause_requested)
        self.assertEqual(pending.error, "")
        self.assertEqual(pending.finished_at, "")

        failed = service.mark_task_failed(pending, "执行失败")
        self.assertEqual(failed.status, AnalysisTaskStatus.FAILED)
        self.assertFalse(failed.pause_requested)
        self.assertEqual(failed.error, "执行失败")
        self.assertNotEqual(failed.finished_at, "")

        completed = service.mark_task_completed(failed)
        self.assertEqual(completed.status, AnalysisTaskStatus.COMPLETED)
        self.assertFalse(completed.pause_requested)
        self.assertNotEqual(completed.finished_at, "")

        cancelled = service.mark_task_cancelled(completed, "取消执行")
        self.assertEqual(cancelled.status, AnalysisTaskStatus.CANCELLED)
        self.assertFalse(cancelled.pause_requested)
        self.assertEqual(cancelled.error, "取消执行")
        self.assertNotEqual(cancelled.finished_at, "")

    def test_append_task_event_persists_ordered_event(self):
        task = service.create_task("测试查询", "analysis_test_3")
        updated = service.append_task_event(task, "progress", {"step": 1, "max_steps": 6}, 1)
        loaded = service.load_task(updated.id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(len(loaded.events), 1)
        self.assertEqual(loaded.events[0].seq, 1)
        self.assertEqual(loaded.events[0].type, "progress")
        self.assertEqual(loaded.events[0].data, {"step": 1, "max_steps": 6})
        self.assertNotEqual(loaded.events[0].created_at, "")

    def test_reconcile_running_tasks_pauses_only_running_tasks(self):
        running = service.create_task("运行中", "analysis_running")
        paused = service.create_task("已暂停", "analysis_paused")
        completed = service.create_task("已完成", "analysis_completed")
        service.mark_task_running(running)
        service.mark_task_paused(paused, "原本暂停")
        service.mark_task_completed(completed)

        count = service.reconcile_running_tasks()

        self.assertEqual(count, 1)
        loaded_running = service.load_task("analysis_running")
        loaded_paused = service.load_task("analysis_paused")
        loaded_completed = service.load_task("analysis_completed")
        self.assertIsNotNone(loaded_running)
        self.assertIsNotNone(loaded_paused)
        self.assertIsNotNone(loaded_completed)
        assert loaded_running is not None
        assert loaded_paused is not None
        assert loaded_completed is not None
        self.assertEqual(loaded_running.status, AnalysisTaskStatus.PAUSED)
        self.assertEqual(loaded_running.error, "服务重启时检测到中断的任务，已暂停，可点击「继续」从断点恢复")
        self.assertEqual(loaded_paused.status, AnalysisTaskStatus.PAUSED)
        self.assertEqual(loaded_paused.error, "原本暂停")
        self.assertEqual(loaded_completed.status, AnalysisTaskStatus.COMPLETED)

    def test_delete_task_removes_task_file_and_task_cache(self):
        task = service.create_task("测试查询", "analysis_test_4")
        cache_dir = service.TASK_CACHE_DIR / task.id
        cache_dir.mkdir(parents=True)
        (cache_dir / "quotes.json").write_text("{}", encoding="utf-8")

        deleted = service.delete_task(task.id)

        self.assertTrue(deleted)
        self.assertIsNone(service.load_task(task.id))
        self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
