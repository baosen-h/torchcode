from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.custom_runner import run_builtin_code
from api.environments import EnvironmentManager, EnvironmentBusyError, environment_id, python_path, validate_packages
from api.main import create_app


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.manager = EnvironmentManager(self.root / "runtime.json", conda_executable="conda-test.exe")
        self.prefix = self.root / "study"
        python = python_path(self.prefix)
        python.parent.mkdir(parents=True)
        python.touch()
        self.environment = {"id": environment_id(self.prefix), "name": "study", "prefix": str(self.prefix),
                            "python": str(python), "has_python": True, "is_backend": False, "can_install": True}
        self.discovery = patch.object(self.manager, "discover", return_value=[self.manager.backend(), self.environment])
        self.discovery.start()

    def tearDown(self):
        self.manager.close()
        self.discovery.stop()
        self.directory.cleanup()

    def test_selection_is_persisted_and_absolute_interpreter_is_used(self):
        self.manager.select(self.environment["id"])
        restored = EnvironmentManager(self.manager.path, conda_executable="conda-test.exe")
        self.assertEqual(restored.selected_id, self.environment["id"])
        with self.manager.lease() as (selected, command):
            self.assertEqual(selected["id"], self.environment["id"])
            self.assertEqual(command[-1], self.environment["python"])
            self.assertIn("--prefix", command)
        self.assertEqual(self.manager.active_runs, 0)

    def test_unknown_and_empty_environments_do_not_fall_back_to_system_python(self):
        with self.assertRaises(ValueError):
            self.manager.select("../../python.exe")
        python_path(self.prefix).unlink()
        with self.assertRaisesRegex(ValueError, "尚未安装 Python"):
            self.manager.select(self.environment["id"])
        self.manager.selected_id = self.environment["id"]
        self.assertIn("安装 Python", self.manager.current()["error"])
        with self.assertRaises(ValueError):
            with self.manager.lease():
                pass

    def test_backend_and_base_are_not_modified_by_package_installation(self):
        with self.assertRaisesRegex(ValueError, "独立环境"):
            self.manager.install_packages("backend", ["numpy"])
        self.environment["can_install"] = False
        with self.assertRaises(ValueError):
            self.manager.install_packages(self.environment["id"], ["torch"])

    def test_packages_reject_commands_urls_options_and_paths(self):
        for package in ["--index-url", "x;echo", "https://example.com/a.whl", "../pkg", "torch && whoami", "-r requirements.txt"]:
            with self.subTest(package=package), self.assertRaises(ValueError):
                validate_packages([package])
        self.assertEqual(validate_packages(["numpy>=1.26,<3", "pandas==2.2.3", "foo[bar]", "numpy>=1.26,<3"]),
                         ["numpy>=1.26,<3", "pandas==2.2.3", "foo[bar]"])

    def test_install_commands_are_argv_lists_in_requested_environment(self):
        with patch.object(self.manager, "start_job", return_value="job") as start:
            self.manager.install_packages(self.environment["id"], ["numpy==1.26.4"])
        command = start.call_args.args[1][0]
        self.assertEqual(command[-1], "numpy==1.26.4")
        self.assertIn(self.environment["python"], command)
        self.assertIn("--no-input", command)
        self.assertNotIn("--user", command)

    def test_create_checks_names_versions_and_existing_names(self):
        for name, version in [("base", "3.11"), ("../bad", "3.11"), ("study", "3.11"), ("good", "2.7")]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.manager.create(name, version)
        with patch.object(self.manager, "start_job", return_value="new") as start:
            self.manager.create("torchcode-study", "3.11")
        self.assertEqual(start.call_args.args[1][0], ["conda-test.exe", "create", "--name", "torchcode-study", "python=3.11", "pip", "--yes"])

    def test_empty_environment_can_receive_python_but_existing_python_cannot_be_replaced(self):
        with self.assertRaises(ValueError):
            self.manager.install_python(self.environment["id"], "3.11")
        python_path(self.prefix).unlink()
        with patch.object(self.manager, "start_job", return_value="python") as start:
            self.manager.install_python(self.environment["id"], "3.11")
        self.assertIn(str(self.prefix), start.call_args.args[1][0])

    def test_runtime_lease_prevents_installation_and_releases_on_error(self):
        with self.assertRaises(RuntimeError):
            with self.manager.lease():
                with self.assertRaises(EnvironmentBusyError):
                    self.manager.start_job("busy", [])
                raise RuntimeError("submission failed")
        self.assertEqual(self.manager.active_runs, 0)

    def wait_for_job(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.manager.snapshot()
            if state["job"]["status"] != "running":
                return state["job"]
            time.sleep(.03)
        self.fail("Job did not finish")

    def test_background_job_reports_unicode_output_and_failure(self):
        self.manager.start_job("test output", [[sys.executable, "-c", "print('安装日志')"]])
        job = self.wait_for_job()
        self.assertEqual(job["status"], "succeeded")
        self.assertIn("安装日志", job["log"])
        self.assertNotIn("log_path", job)
        self.manager.start_job("test failure", [[sys.executable, "-c", "raise SystemExit(7)"]])
        job = self.wait_for_job()
        self.assertEqual(job["status"], "failed")
        self.assertIn("7", job["message"])

    def test_running_installation_prevents_runs_and_second_jobs(self):
        self.manager.job = {"status": "running"}
        with self.assertRaises(EnvironmentBusyError):
            self.manager.start_job("second", [])
        with self.assertRaises(EnvironmentBusyError):
            self.manager.select("backend")
        with self.assertRaises(EnvironmentBusyError):
            with self.manager.lease():
                pass


class EnvironmentDiscoveryTests(unittest.TestCase):
    def test_conda_discovery_marks_empty_prefixes_and_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = EnvironmentManager(root / "runtime.json", conda_executable="conda-test.exe")
            info = {"envs": [str(root / "base"), str(root / "empty")], "root_prefix": str(root / "base")}
            completed = subprocess.CompletedProcess([], 0, json.dumps(info), "")
            with patch("api.environments.subprocess.run", return_value=completed) as run:
                state = manager.snapshot()
                manager.snapshot()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(len(state["environments"]), 3)
            self.assertFalse(state["environments"][1]["can_install"])
            self.assertFalse(state["environments"][2]["has_python"])
            self.assertTrue(state["environments"][2]["can_install"])

    def test_missing_conda_keeps_backend_usable(self):
        with tempfile.TemporaryDirectory() as directory, patch("api.environments.find_conda", return_value=None):
            manager = EnvironmentManager(Path(directory) / "runtime.json")
            self.assertFalse(manager.snapshot()["conda_available"])
            with manager.lease() as (environment, command):
                self.assertEqual(environment["id"], "backend")
                self.assertIsNone(command)


class EnvironmentApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.manager = EnvironmentManager(root / "runtime.json", conda_executable="conda-test.exe")
        self.manager.discover = lambda refresh=False: [self.manager.backend()]
        self.context = TestClient(create_app(root / "library.db", self.manager))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.directory.cleanup()

    def test_api_lists_and_selects_without_changing_backend_process(self):
        self.assertEqual(self.client.get("/api/environments").status_code, 200)
        response = self.client.put("/api/environments/current", json={"environment_id": "backend"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected"]["python"], sys.executable)
        self.assertEqual(self.client.get("/api/health").json()["service"], "torchcode")

    def test_environment_mutations_reject_foreign_origins_and_remote_hosts(self):
        response = self.client.post("/api/environments", json={"name": "study"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)
        response = self.client.put("/api/environments/current", json={"environment_id": "backend"}, headers={"Host": "other-host"})
        self.assertEqual(response.status_code, 403)

    def test_busy_installation_is_a_visible_conflict_and_not_a_submission(self):
        task = self.client.post("/api/tasks", json={"title": "test"}).json()
        self.manager.job = {"status": "running"}
        response = self.client.post(f"/api/submit/{task['id']}", json={"code": "print('no')"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("安装", response.json()["detail"])

    def test_selected_command_is_used_for_custom_and_builtin_tasks(self):
        @contextmanager
        def selected_lease():
            yield {"id": "selected", "name": "study"}, ["selected-python.exe"]

        self.manager.lease = selected_lease
        task = self.client.post("/api/tasks", json={"title": "test"}).json()
        result = {"mode": "run", "success": True, "passed": 0, "total": 0, "tests": []}
        with patch("api.main.run_custom_code", return_value=result.copy()) as run:
            response = self.client.post(f"/api/submit/{task['id']}", json={"code": "print('yes')"})
        self.assertEqual(run.call_args.kwargs["command_prefix"], ["selected-python.exe"])
        self.assertEqual(response.json()["environment"]["name"], "study")
        with patch("api.main.execute_code", return_value={**result, "mode": "tests"}) as run:
            self.client.post("/api/submit/relu", json={"code": "test code"})
        self.assertEqual(run.call_args.kwargs["command_prefix"], ["selected-python.exe"])

    def test_builtin_subprocess_judge_still_passes(self):
        result = run_builtin_code("relu", "import torch\ndef relu(x):\n    return torch.clamp(x, min=0)")
        self.assertTrue(result["success"], result)
        self.assertEqual((result["passed"], result["total"]), (4, 4))


if __name__ == "__main__":
    unittest.main()
