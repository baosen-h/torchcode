"""Run custom code using the backend's Python environment, with a wall-clock timeout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

OUTPUT_LIMIT = 64_000
DEFAULT_TIMEOUT_SECONDS = 30


def stop_worker(process):
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def failure_result(message, mode, total, elapsed, stdout="", stderr=""):
    return {"success": False, "mode": mode, "error": message, "passed": 0, "total": total,
            "tests": [], "stdout": stdout, "stderr": stderr, "total_time_ms": elapsed}


def run_custom_code(code, test_cases, timeout_seconds=None, command_prefix=None):
    enabled_count = sum(bool(test.get("enabled", True)) for test in test_cases)
    mode = "tests" if enabled_count else "run"
    return run_payload({"code": code, "test_cases": test_cases}, mode, enabled_count, timeout_seconds, command_prefix)


def run_builtin_code(task_id, code, command_prefix=None, timeout_seconds=None):
    from torch_judge.tasks import TASKS
    total = len(TASKS.get(task_id, {}).get("tests", []))
    return run_payload({"code": code, "builtin_task_id": task_id}, "tests", total, timeout_seconds, command_prefix)


def run_payload(request, mode, enabled_count, timeout_seconds, command_prefix):
    if timeout_seconds is None:
        try:
            timeout_seconds = max(1, min(120, int(os.environ.get("TORCHCODE_RUN_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))))
        except ValueError:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    started = time.perf_counter()
    worker = Path(__file__).with_name("execution_worker.py")
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONOPTIMIZE": "0"}
    if command_prefix:
        environment["PYTHONNOUSERSITE"] = "1"
        environment.pop("PYTHONPATH", None)
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    payload = json.dumps(request, ensure_ascii=False)
    with tempfile.TemporaryDirectory(prefix="torchcode-run-") as directory:
        output_path = Path(directory) / "result.json"
        log_path = Path(directory) / "worker.log"
        timed_out = False
        with log_path.open("wb") as log:
            command = [*(command_prefix or [sys.executable]), "-B", str(worker), str(output_path)]
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                           text=True, encoding="utf-8", cwd=worker.parent.parent, env=environment, **flags)
            except OSError as error:
                return failure_result(f"无法启动所选 Python 环境：{error}", mode, enabled_count, 0)
            try:
                process.communicate(payload, timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_worker(process)
                process.communicate(timeout=5)
        elapsed = (time.perf_counter() - started) * 1000
        log_content = log_path.read_bytes()[:OUTPUT_LIMIT].decode("utf-8", errors="replace")
        if timed_out:
            return failure_result(f"运行超时（{timeout_seconds} 秒），请检查是否存在死循环或减少计算量。", mode, enabled_count, elapsed, stderr=log_content)
        if process.returncode != 0 or not output_path.exists():
            return failure_result(f"Python 进程意外退出（退出码 {process.returncode}）。", mode, enabled_count, elapsed, stderr=log_content)
        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return failure_result("无法读取运行结果，请重试。", mode, enabled_count, elapsed, stderr=log_content)
        result["mode"] = mode
        if log_content:
            result["stderr"] = (result.get("stderr", "") + log_content)[:OUTPUT_LIMIT]
        return result
