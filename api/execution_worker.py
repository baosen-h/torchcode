"""Execute one personal submission in a disposable Python process."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import time
import traceback

OUTPUT_LIMIT = 64_000


class BoundedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.remaining = OUTPUT_LIMIT
        self.truncated = False

    def write(self, text):
        if self.remaining:
            written = text[:self.remaining]
            super().write(written)
            self.remaining -= len(written)
        if len(text) and not self.remaining and not self.truncated:
            super().write("\n…输出过长，后续内容已截断。\n")
            self.truncated = True
        return len(text)


def exception_details(error):
    return f"{type(error).__name__}: {error}".rstrip(": "), "".join(traceback.format_exception(type(error), error, error.__traceback__))


def run_script(compiled_code, test=None):
    stdout, stderr = BoundedOutput(), BoundedOutput()
    started = time.perf_counter()
    error_message = None
    error_traceback = None
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            namespace = {"__name__": "__main__"}
            exec(compiled_code, namespace)
            if test is not None:
                exec(compile(test["code"], f"<test:{test['name']}>", "exec"), namespace)
        except BaseException as error:
            error_message, error_traceback = exception_details(error)
    return {"passed": error_message is None, "time_ms": (time.perf_counter() - started) * 1000,
            "error_msg": error_message, "error_traceback": error_traceback,
            "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def execute(payload):
    tests = [test for test in payload["test_cases"] if test.get("enabled", True)]
    result = {"mode": "tests" if tests else "run", "success": False, "passed": 0,
              "total": len(tests), "tests": [], "stdout": "", "stderr": "", "total_time_ms": 0}
    started = time.perf_counter()
    try:
        compiled_code = compile(payload["code"], "<user_code>", "exec")
    except BaseException as error:
        result["error"], result["traceback"] = exception_details(error)
        return result
    if not tests:
        execution = run_script(compiled_code)
        result.update(success=execution["passed"], stdout=execution["stdout"], stderr=execution["stderr"])
        if not execution["passed"]:
            result.update(error=execution["error_msg"], traceback=execution["error_traceback"])
        result["total_time_ms"] = (time.perf_counter() - started) * 1000
        return result
    for test in tests:
        execution = run_script(compiled_code, test)
        result["tests"].append({"id": test["id"], "name": test["name"], "code": test["code"], **execution})
        result["passed"] += int(execution["passed"])
    result["success"] = result["passed"] == result["total"]
    result["total_time_ms"] = (time.perf_counter() - started) * 1000
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    output_path = Path(sys.argv[1])
    try:
        payload = json.load(sys.stdin)
        if "builtin_task_id" in payload:
            from torch_judge.web_engine import execute_code
            output = execute_code(payload["builtin_task_id"], payload["code"])
        if "builtin_task_id" not in payload:
            output = execute(payload)
    except BaseException as error:
        message, details = exception_details(error)
        output = {"success": False, "error": message, "traceback": details,
                  "passed": 0, "total": 0, "tests": [], "stdout": "", "stderr": ""}
    output_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
