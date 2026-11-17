import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.custom_runner import run_custom_code
from api.library import LibraryStore
from api.main import create_app


def test_case(code, identifier="case_1", **changes):
    return {"id": identifier, "name": identifier, "code": code, "enabled": True, **changes}


class CustomRunnerTests(unittest.TestCase):
    def test_code_only_captures_unicode_stdout_and_stderr(self):
        result = run_custom_code("import sys\nprint('运行输出')\nprint('diagnostic', file=sys.stderr)", [])
        self.assertTrue(result["success"], result)
        self.assertEqual(result["mode"], "run")
        self.assertEqual(result["total"], 0)
        self.assertIn("运行输出", result["stdout"])
        self.assertIn("diagnostic", result["stderr"])

    def test_syntax_and_runtime_errors_are_reported(self):
        for code, message in [("def broken(", "SyntaxError"), ("missing_name", "NameError")]:
            with self.subTest(code=code):
                result = run_custom_code(code, [])
                self.assertFalse(result["success"])
                self.assertIn(message, result["error"])
                self.assertIn("<user_code>", result["traceback"])

    def test_assertions_are_evaluated_and_later_cases_still_run(self):
        cases = [test_case("assert add(1, 2) == 3\nprint('pass output')"),
                 test_case("assert add(1, 2) == 99, 'expected 99'", "case_2"),
                 test_case("assert add(-1, 1) == 0", "case_3")]
        result = run_custom_code("def add(a, b):\n    return a + b", cases)
        self.assertEqual((result["passed"], result["total"]), (2, 3))
        self.assertFalse(result["success"])
        self.assertIn("pass output", result["tests"][0]["stdout"])
        self.assertIn("expected 99", result["tests"][1]["error_msg"])
        self.assertIn("<test:case_2>", result["tests"][1]["error_traceback"])
        self.assertTrue(result["tests"][2]["passed"])

    def test_cases_receive_fresh_user_namespaces(self):
        result = run_custom_code("values = []", [test_case("values.append(1)\nassert values == [1]"), test_case("assert values == []", "case_2")])
        self.assertTrue(result["success"], result)
        self.assertEqual(result["passed"], 2)

    def test_disabled_tests_are_not_judged(self):
        result = run_custom_code("print('executed')", [test_case("assert False", enabled=False)])
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "run")
        self.assertEqual(result["total"], 0)

    def test_system_exit_does_not_stop_the_backend(self):
        result = run_custom_code("raise SystemExit(3)", [])
        self.assertFalse(result["success"])
        self.assertIn("SystemExit", result["error"])
        self.assertTrue(run_custom_code("print('next submission')", [])["success"])

    def test_output_is_bounded(self):
        result = run_custom_code("print('x' * 200000)", [])
        self.assertTrue(result["success"])
        self.assertLess(len(result["stdout"]), 64200)
        self.assertIn("截断", result["stdout"])

    def test_timeout_stops_infinite_loop_and_next_submission_works(self):
        result = run_custom_code("while True:\n    pass", [], timeout_seconds=1)
        self.assertFalse(result["success"])
        self.assertIn("超时", result["error"])
        self.assertTrue(run_custom_code("print('still responsive')", [])["success"])

    def test_unexpected_process_exit_is_not_counted_as_success(self):
        result = run_custom_code("import os\nos._exit(0)", [])
        self.assertFalse(result["success"])
        self.assertIn("意外退出", result["error"])


class CustomTaskApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "library.db"
        self.client_context = TestClient(create_app(self.database))
        self.client = self.client_context.__enter__()
        response = self.client.post("/api/tasks", json={"title": "自定义加法"})
        self.task_id = response.json()["id"]
        self.path = f"/api/tasks/{self.task_id}"

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.directory.cleanup()

    def save_cases(self, cases, revision=0):
        return self.client.put(self.path + "/tests", json={"test_cases": cases, "expected_revision": revision})

    def test_running_code_without_tests_does_not_mark_solved(self):
        response = self.client.post(f"/api/submit/{self.task_id}", json={"code": "print('done')", "tests_revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["mode"], "run")
        self.assertTrue(response.json()["success"])
        self.assertEqual(self.client.get(self.path).json()["progress"]["status"], "attempted")

    def test_saved_assertions_run_and_completion_is_invalidated_by_changed_tests(self):
        self.client.patch(self.path + "/progress", json={"code": "my draft", "notes": "my notes"})
        saved = self.save_cases([test_case("assert add(1, 2) == 3")])
        self.assertEqual(saved.status_code, 200, saved.text)
        revision = saved.json()["tests_revision"]
        result = self.client.post(f"/api/submit/{self.task_id}", json={"code": "def add(a, b):\n    return a + b", "tests_revision": revision})
        self.assertTrue(result.json()["success"], result.text)
        self.assertEqual(result.json()["progress"]["completion_source"], "tests")
        changed = self.save_cases([test_case("assert add(2, 3) == 5")], revision).json()
        self.assertEqual(changed["progress"]["status"], "attempted")
        self.assertIsNone(changed["progress"]["completion_source"])
        self.assertEqual(changed["progress"]["notes"], "my notes")
        self.assertEqual(changed["progress"]["code"], "my draft")

    def test_manual_completion_is_preserved_when_tests_change(self):
        self.client.patch(self.path + "/progress", json={"status": "solved"})
        updated = self.save_cases([test_case("assert True")]).json()
        self.assertEqual(updated["progress"]["status"], "solved")
        self.assertEqual(updated["progress"]["completion_source"], "manual")

    def test_revision_conflicts_cannot_overwrite_saved_cases(self):
        saved = self.save_cases([test_case("assert True")]).json()
        stale = self.save_cases([test_case("assert False")])
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.get(self.path).json()["test_cases"], saved["test_cases"])
        self.assertEqual(self.client.post(f"/api/submit/{self.task_id}", json={"code": "pass", "tests_revision": 0}).status_code, 409)

    def test_invalid_or_duplicate_cases_and_builtin_edits_are_rejected(self):
        self.assertEqual(self.save_cases([test_case("")]).status_code, 422)
        self.assertEqual(self.save_cases([test_case("assert True"), test_case("assert False")]).status_code, 422)
        self.assertEqual(self.save_cases([test_case("", enabled=False)]).status_code, 200)
        builtin = self.client.put("/api/tasks/relu/tests", json={"test_cases": [], "expected_revision": 0})
        self.assertEqual(builtin.status_code, 400)

    def test_cases_survive_backup_restore_and_old_backups_still_import(self):
        cases = [test_case("assert add(1, 2) == 3")]
        self.save_cases(cases)
        backup = self.client.get("/api/library/backup").json()
        exported = next(task for task in backup["custom_tasks"] if task["id"] == self.task_id)
        self.assertEqual(exported["test_cases"], cases)
        self.save_cases([], 1)
        restored = self.client.post("/api/library/restore", json=backup)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(self.client.get(self.path).json()["test_cases"], cases)
        old_backup = copy.deepcopy(backup)
        for task in old_backup["custom_tasks"]:
            task.pop("test_cases", None)
            task.pop("tests_revision", None)
        self.assertEqual(self.client.post("/api/library/restore", json=old_backup).status_code, 200)
        self.assertEqual(self.client.get(self.path).json()["test_cases"], [])

    def test_results_from_changed_test_suite_do_not_mark_solved(self):
        self.save_cases([test_case("assert True")])

        def run_and_change_suite(code, cases):
            LibraryStore(self.database).save_test_cases(self.task_id, [test_case("assert False")], 1)
            return {"mode": "tests", "success": True, "passed": 1, "total": 1, "tests": []}

        with patch("api.main.run_custom_code", side_effect=run_and_change_suite):
            result = self.client.post(f"/api/submit/{self.task_id}", json={"code": "pass", "tests_revision": 1}).json()
        self.assertIn("修改", result["warning"])
        self.assertNotEqual(self.client.get(self.path).json()["progress"]["status"], "solved")

    def test_existing_database_schema_is_upgraded_without_losing_tasks(self):
        legacy_database = Path(self.directory.name) / "legacy.db"
        with sqlite3.connect(legacy_database) as connection:
            connection.executescript("""
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO metadata VALUES ('database_id', 'old-database-id');
                CREATE TABLE custom_tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    difficulty TEXT NOT NULL, initial_code TEXT NOT NULL, source_url TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                INSERT INTO custom_tasks VALUES ('custom_00000000000000000000000000000001', '旧问题', '旧描述', '', 'old code', '', '', '');
            """)
        with TestClient(create_app(legacy_database)) as legacy:
            task = legacy.get("/api/tasks/custom_00000000000000000000000000000001").json()
            self.assertEqual(task["title"], "旧问题")
            self.assertEqual(task["initial_code"], "old code")
            self.assertEqual(task["test_cases"], [])
            self.assertEqual(task["tests_revision"], 0)
            self.assertEqual(legacy.get("/api/health").json()["database_id"], "old-database-id")


if __name__ == "__main__":
    unittest.main()
