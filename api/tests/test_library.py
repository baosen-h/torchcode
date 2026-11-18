"""Run with python -m unittest discover -s api/tests -v."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import create_app


class LibraryApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "library.db"
        self.client_context = TestClient(create_app(self.database))
        self.client = self.client_context.__enter__()
        self.library = self.client.get("/api/library").json()
        self.category_id = self.library["categories"][0]["id"]

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.directory.cleanup()

    def create_task(self, **changes):
        values = {"title": "排查训练 NaN", "description": "定位 loss 为 NaN 的原因", "category_ids": [self.category_id], **changes}
        response = self.client.post("/api/tasks", json=values)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_builtin_catalog_and_details_remain_available(self):
        self.assertGreater(len(self.library["tasks"]), 30)
        task = self.client.get("/api/tasks/relu").json()
        self.assertEqual(task["source"], "builtin")
        self.assertEqual(task["source_url"], "https://github.com/duoan/TorchCode")
        self.assertEqual(task["problem_number"], 1)
        self.assertIsNotNone(task["progress"]["last_opened_at"])
        self.assertIn("torch", task["initial_code"])
        self.assertTrue(task["description"])

    def test_problem_numbers_are_stable_and_recent_open_is_persisted(self):
        first = self.create_task()
        second = self.create_task(title="另一个问题")
        self.assertGreater(first["problem_number"], self.library["tasks"][-1]["problem_number"])
        self.assertEqual(second["problem_number"], first["problem_number"] + 1)
        opened = self.client.get(f"/api/tasks/{first['id']}").json()
        self.assertIsNotNone(opened["progress"]["last_opened_at"])
        opened_at = opened["progress"]["last_opened_at"]
        saved = self.client.patch(f"/api/tasks/{first['id']}/progress", json={"status": "solved", "notes": "保留"}).json()
        self.assertEqual(saved["last_opened_at"], opened_at)
        listed = next(task for task in self.client.get("/api/tasks").json() if task["id"] == first["id"])
        self.assertEqual(listed["progress"]["last_opened_at"], opened_at)
        self.client.delete(f"/api/tasks/{first['id']}")
        third = self.create_task(title="新问题")
        self.assertEqual(third["problem_number"], second["problem_number"] + 1)

    def test_open_time_and_number_survive_backup_restore(self):
        task = self.create_task()
        opened = self.client.get(f"/api/tasks/{task['id']}").json()
        backup = self.client.get("/api/library/backup").json()
        self.assertEqual(backup["progress"][task["id"]]["last_opened_at"], opened["progress"]["last_opened_at"])
        self.client.post("/api/library/restore", json=backup)
        after_restore = self.client.get("/api/library/backup").json()
        self.assertEqual(after_restore["progress"][task["id"]]["last_opened_at"], opened["progress"]["last_opened_at"])
        restored = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(restored["problem_number"], task["problem_number"])

    def test_large_markdown_description_accepts_embedded_image_data(self):
        task = self.create_task(description="![image](data:image/png;base64," + "A" * 1_400_000 + ")")
        self.assertEqual(len(task["description"]), 1_400_032)
        listed = next(item for item in self.client.get("/api/tasks").json() if item["id"] == task["id"])
        self.assertNotIn("A" * 100, listed["search_text"])

    def test_backup_preserves_number_gaps_and_handles_collisions(self):
        deleted = self.create_task()
        self.client.delete(f"/api/tasks/{deleted['id']}")
        kept = self.create_task(title="Kept number")
        highest = self.create_task()
        self.client.delete(f"/api/tasks/{highest['id']}")
        backup = self.client.get("/api/library/backup").json()
        with TestClient(create_app(Path(self.directory.name) / "gap-restore.db")) as target:
            response = target.post("/api/library/restore", json=backup)
            self.assertEqual(response.status_code, 200, response.text)
            restored = target.get(f"/api/tasks/{kept['id']}").json()
            self.assertEqual(restored["problem_number"], kept["problem_number"])
            new = target.post("/api/tasks", json={"title": "After restore"}).json()
            self.assertGreater(new["problem_number"], highest["problem_number"])
        with TestClient(create_app(Path(self.directory.name) / "collision.db")) as target:
            target.post("/api/tasks", json={"title": "Existing A"})
            existing = target.post("/api/tasks", json={"title": "Existing B"}).json()
            target.post("/api/library/restore", json=backup)
            tasks = target.get("/api/tasks").json()
            numbers = [item["problem_number"] for item in tasks]
            self.assertEqual(len(numbers), len(set(numbers)))
            self.assertEqual(target.get(f"/api/tasks/{existing['id']}").json()["problem_number"], existing["problem_number"])

    def test_custom_problem_crud_and_manual_completion(self):
        task = self.create_task()
        task_id = task["id"]
        response = self.client.patch(f"/api/tasks/{task_id}/progress", json={"status": "solved", "code": "", "notes": "使用 FP32 累加"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["completion_source"], "manual")
        self.assertEqual(response.json()["code"], "")
        updated = self.client.put(f"/api/tasks/{task_id}", json={"title": "排查 AMP NaN", "category_ids": []})
        self.assertEqual(updated.json()["progress"]["notes"], "使用 FP32 累加")
        self.assertEqual(updated.json()["category_ids"], [])
        undone = self.client.patch(f"/api/tasks/{task_id}/progress", json={"status": "todo"}).json()
        self.assertIsNone(undone["solved_at"])
        self.assertIsNone(undone["completion_source"])
        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/tasks/{task_id}").status_code, 404)

    def test_builtin_content_and_judged_completion_are_protected(self):
        self.assertEqual(self.client.put("/api/tasks/relu", json={"title": "overwrite"}).status_code, 400)
        self.assertEqual(self.client.delete("/api/tasks/relu").status_code, 404)
        self.assertEqual(self.client.patch("/api/tasks/relu/progress", json={"status": "solved"}).status_code, 400)
        task = self.create_task()
        result = self.client.post(f"/api/submit/{task['id']}", json={"code": "print('ok')"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["mode"], "run")

    def test_auto_judge_completion_is_persisted_and_failure_does_not_clear_it(self):
        with patch("api.main.execute_code", return_value={"success": True, "passed": 1, "total": 1, "tests": []}):
            result = self.client.post("/api/submit/relu", json={"code": "sample"}).json()
        self.assertEqual(result["progress"]["completion_source"], "tests")
        with patch("api.main.execute_code", return_value={"success": False, "passed": 0, "total": 1, "tests": []}):
            self.client.post("/api/submit/relu", json={"code": "broken"})
        self.assertEqual(self.client.get("/api/tasks/relu").json()["progress"]["status"], "solved")

    def test_draft_updates_do_not_overwrite_status_and_stale_saves_are_ignored(self):
        task_id = self.create_task()["id"]
        path = f"/api/tasks/{task_id}/progress"
        self.client.patch(path, json={"status": "solved"})
        self.client.patch(path, json={"code": "new", "notes": "new note", "draft_updated_at": "2026-11-17T04:00:01.000Z"})
        response = self.client.patch(path, json={"code": "old", "notes": "old note", "draft_updated_at": "2026-11-17T04:00:00.000Z"})
        self.assertEqual(response.json()["code"], "new")
        self.assertEqual(response.json()["notes"], "new note")
        self.assertEqual(response.json()["status"], "solved")

    def test_category_rename_reorder_merge_and_delete_preserve_tasks(self):
        category = self.client.post("/api/categories", json={"name": "自定义分类"}).json()
        task = self.create_task(category_ids=[category["id"], self.category_id])
        self.assertEqual(self.client.put(f"/api/categories/{category['id']}", json={"name": "排错记录"}).status_code, 200)
        ordered = [category["id"]] + [item["id"] for item in self.library["categories"]]
        self.assertEqual(self.client.put("/api/categories/order", json={"category_ids": ordered}).status_code, 200)
        self.assertEqual(self.client.get("/api/library").json()["categories"][0]["name"], "排错记录")
        self.client.post(f"/api/categories/{category['id']}/merge", json={"target_id": self.category_id})
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()["category_ids"], [self.category_id])
        self.client.delete(f"/api/categories/{self.category_id}")
        persisted = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertEqual(persisted["category_ids"], [])
        self.assertEqual(persisted["title"], task["title"])

    def test_migration_is_non_destructive_and_preserves_empty_drafts(self):
        payload = {"solved_ids": ["relu", "unknown"], "drafts": {"relu": "", "softmax": "legacy draft"}}
        self.assertEqual(self.client.post("/api/library/migrate", json=payload).status_code, 200)
        relu = self.client.get("/api/tasks/relu").json()["progress"]
        self.assertEqual(relu["code"], "")
        self.assertEqual(relu["completion_source"], "legacy")
        self.client.patch("/api/tasks/softmax/progress", json={"code": "new database draft", "status": "attempted"})
        self.client.post("/api/library/migrate", json=payload)
        self.assertEqual(self.client.get("/api/tasks/softmax").json()["progress"]["code"], "new database draft")

    def test_backup_roundtrip_and_bad_import_are_atomic(self):
        task = self.create_task()
        self.client.patch(f"/api/tasks/{task['id']}/progress", json={"status": "solved", "notes": "重要结论", "code": "answer"})
        self.client.put("/api/tasks/relu/categories", json={"category_ids": []})
        backup = self.client.get("/api/library/backup").json()
        self.client.delete(f"/api/tasks/{task['id']}")
        response = self.client.post("/api/library/restore", json=backup)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()["progress"]["notes"], "重要结论")
        self.assertEqual(self.client.get("/api/tasks/relu").json()["category_ids"], [])
        invalid = copy.deepcopy(backup)
        invalid["custom_tasks"][0]["title"] = "MUST ROLLBACK"
        invalid["task_categories"].append({"task_id": task["id"], "category_id": "missing"})
        self.assertEqual(self.client.post("/api/library/restore", json=invalid).status_code, 400)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()["title"], task["title"])

    def test_validation_rejects_empty_names_unsafe_links_and_invalid_categories(self):
        self.assertEqual(self.client.post("/api/tasks", json={"title": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", json={"title": "test", "source_url": "javascript:alert(1)"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", json={"title": "test", "category_ids": ["missing"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/categories", json={"name": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/categories", json={"name": self.library["categories"][0]["name"]}).status_code, 409)

    def test_library_survives_restart_and_deleted_defaults_are_not_reseeded(self):
        task_id = self.create_task()["id"]
        self.client.delete(f"/api/categories/{self.category_id}")
        identity = self.library["database_id"]
        with TestClient(create_app(self.database)) as restarted:
            data = restarted.get("/api/library").json()
            self.assertEqual(data["database_id"], identity)
            self.assertNotIn(self.category_id, [category["id"] for category in data["categories"]])
            self.assertEqual(restarted.get(f"/api/tasks/{task_id}").status_code, 200)

    def test_backup_restores_to_a_new_database_without_duplicate_category_names(self):
        task = self.create_task()
        self.client.put("/api/tasks/relu/categories", json={"category_ids": []})
        backup = self.client.get("/api/library/backup").json()
        with TestClient(create_app(Path(self.directory.name) / "restored.db")) as restored:
            response = restored.post("/api/library/restore", json=backup)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(restored.get("/api/library").json()["categories"]), len(backup["categories"]))
            self.assertEqual(restored.get(f"/api/tasks/{task['id']}").json()["title"], task["title"])
            self.assertEqual(restored.get("/api/tasks/relu").json()["category_ids"], [])

    def test_concurrent_failing_test_cannot_overwrite_a_success(self):
        def failing_after_success(task_id, code):
            from api.library import LibraryStore
            LibraryStore(self.database).update_progress(task_id, {"status": "solved"}, "tests")
            return {"success": False, "passed": 0, "total": 1, "tests": []}

        with patch("api.main.execute_code", side_effect=failing_after_success):
            self.client.post("/api/submit/relu", json={"code": "broken"})
        self.assertEqual(self.client.get("/api/tasks/relu").json()["progress"]["status"], "solved")


if __name__ == "__main__":
    unittest.main()
