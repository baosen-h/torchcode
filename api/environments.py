"""Discover Conda runtimes and perform explicit, logged installation jobs."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from api.custom_runner import stop_worker

LOG_LIMIT = 64_000
JOB_TIMEOUT_SECONDS = 1800
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:(?:==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+(?:,(?:==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)*)?$")
PYTHON_VERSIONS = {"3.10", "3.11", "3.12", "3.13"}


class EnvironmentBusyError(ValueError):
    pass


def process_flags():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def find_conda():
    candidates = [os.environ.get("TORCHCODE_CONDA_EXE"), os.environ.get("CONDA_EXE"), shutil.which("conda.exe")]
    for name in ("anaconda3", "miniconda3", "Anaconda3", "Miniconda3"):
        candidates.append(str(Path.home() / name / "Scripts" / "conda.exe"))
    candidates.append(shutil.which("conda"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate).suffix.lower() not in {".bat", ".cmd"}:
            return str(Path(candidate).resolve())
    return None


def python_path(prefix):
    return Path(prefix) / ("python.exe" if os.name == "nt" else "bin/python")


def environment_id(prefix):
    normalized = os.path.normcase(str(Path(prefix).resolve()))
    return "conda_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def validate_packages(packages):
    if not isinstance(packages, list) or not 1 <= len(packages) <= 30:
        raise ValueError("请填写 1–30 个依赖包，每行一个")
    for package in packages:
        if not isinstance(package, str) or len(package) > 200 or not PACKAGE_PATTERN.fullmatch(package):
            raise ValueError("依赖请使用包名或版本条件，例如 numpy、pandas==2.2.3；不支持命令、网址或本地文件")
    return list(dict.fromkeys(packages))


class EnvironmentManager:
    def __init__(self, settings_path, conda_executable=None):
        self.path = Path(settings_path)
        self.conda = conda_executable or find_conda()
        self.lock = threading.RLock()
        self.catalog_lock = threading.Lock()
        self.catalog = []
        self.catalog_at = 0
        self.discovery_error = ""
        self.active_runs = 0
        self.job = None
        self.job_process = None
        self.is_closing = False
        self.selected_id = "backend"
        try:
            self.selected_id = json.loads(self.path.read_text(encoding="utf-8")).get("selected_id", "backend")
        except (OSError, ValueError, AttributeError):
            pass

    def backend(self):
        return {"id": "backend", "name": "后端 Python（默认）", "prefix": sys.prefix,
                "python": sys.executable, "has_python": True, "is_backend": True,
                "can_install": False, "version": sys.version.split()[0]}

    def discover(self, refresh=False):
        with self.catalog_lock:
            if not refresh and self.catalog_at and time.monotonic() - self.catalog_at < 30:
                return deepcopy(self.catalog)
            environments = [self.backend()]
            self.discovery_error = ""
            if not self.conda:
                self.discovery_error = "未找到 Conda，可继续使用默认 Python。请从 Anaconda Prompt 启动，或设置 TORCHCODE_CONDA_EXE。"
                self.catalog = environments
                return deepcopy(environments)
            try:
                result = subprocess.run([self.conda, "info", "--json"], capture_output=True,
                                        text=True, encoding="utf-8", errors="replace", timeout=20, **process_flags())
                if result.returncode:
                    raise ValueError(result.stderr[-2000:] or result.stdout[-2000:])
                info = json.loads(result.stdout)
                for prefix in dict.fromkeys(info.get("envs", [])):
                    python = python_path(prefix)
                    is_backend = os.path.normcase(str(python.resolve())) == os.path.normcase(str(Path(sys.executable).resolve()))
                    environments.append({"id": environment_id(prefix), "name": "base" if prefix == info.get("root_prefix") else Path(prefix).name,
                                         "prefix": prefix, "python": str(python), "has_python": python.is_file(),
                                         "is_backend": is_backend, "can_install": not is_backend and prefix != info.get("root_prefix")})
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                self.discovery_error = f"读取 Conda 环境失败：{str(error)[:2000]}"
            self.catalog = environments
            self.catalog_at = time.monotonic()
            return deepcopy(environments)

    def resolve(self, identifier, require_python=True):
        if identifier == "backend":
            return self.backend()
        environment = next((item for item in self.discover() if item["id"] == identifier), None)
        if environment is None:
            raise ValueError("环境已不存在，请刷新环境列表重新选择")
        if require_python and not python_path(environment["prefix"]).is_file():
            raise ValueError("这个 Conda 环境尚未安装 Python，请先在环境管理中安装 Python")
        return environment

    def command(self, environment):
        if environment["id"] == "backend":
            return [sys.executable]
        if not self.conda:
            raise ValueError("Conda 不可用，请刷新环境列表")
        # Use the absolute interpreter so an empty Conda prefix cannot fall back to system Python.
        return [self.conda, "run", "--no-capture-output", "--prefix", environment["prefix"], environment["python"]]

    def current(self):
        with self.lock:
            identifier = self.selected_id
        try:
            return {"selected": self.resolve(identifier), "error": ""}
        except ValueError as error:
            return {"selected": {"id": identifier, "name": "所选环境不可用", "has_python": False}, "error": str(error)}

    def snapshot(self, refresh=False):
        environments = self.discover(refresh)
        with self.lock:
            job = deepcopy(self.job)
            active_runs = self.active_runs
        if job:
            try:
                with Path(job.pop("log_path")).open("rb") as log:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell() - LOG_LIMIT))
                    job["log"] = log.read().decode("utf-8", errors="replace")
            except OSError:
                job["log"] = "正在准备…"
        return {"environments": environments, **self.current(), "conda_available": bool(self.conda),
                "discovery_error": self.discovery_error, "job": job, "active_runs": active_runs}

    def ensure_idle(self):
        if self.is_closing:
            raise EnvironmentBusyError("后端正在关闭，请稍后重试")
        if self.job and self.job["status"] == "running":
            raise EnvironmentBusyError("环境安装任务正在执行，请等待完成")

    def select(self, identifier):
        environment = self.resolve(identifier)
        with self.lock:
            self.ensure_idle()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as temporary:
                json.dump({"selected_id": identifier}, temporary)
                temporary_path = Path(temporary.name)
            try:
                os.replace(temporary_path, self.path)
            finally:
                temporary_path.unlink(missing_ok=True)
            self.selected_id = identifier
        return environment

    @contextmanager
    def lease(self):
        with self.lock:
            self.ensure_idle()
            environment = self.resolve(self.selected_id)
            self.active_runs += 1
        try:
            yield environment, None if environment["id"] == "backend" else self.command(environment)
        finally:
            with self.lock:
                self.active_runs -= 1

    def start_job(self, title, commands):
        with self.lock:
            self.ensure_idle()
            if self.active_runs:
                raise EnvironmentBusyError("有代码正在运行，请运行结束后再安装环境或依赖")
            job_id = uuid4().hex
            directory = self.path.parent / "environment-logs"
            directory.mkdir(parents=True, exist_ok=True)
            self.job = {"id": job_id, "title": title, "status": "running", "log_path": str(directory / f"{job_id}.log"),
                        "message": "正在执行，请等待…", "started_at": time.time(), "finished_at": None}
            threading.Thread(target=self.run_job, args=(job_id, commands), daemon=True).start()
            return job_id

    def run_job(self, job_id, commands):
        message = "安装完成。刷新环境列表后即可使用。"
        status = "succeeded"
        try:
            with Path(self.job["log_path"]).open("wb") as log:
                for command in commands:
                    with self.lock:
                        if self.is_closing:
                            raise RuntimeError("服务已关闭，安装中断；环境可能只安装了一部分，请检查后重试。")
                        log.write(("> " + subprocess.list2cmdline(command) + "\n\n").encode("utf-8"))
                        log.flush()
                        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PIP_USER": "0", "PIP_NO_INPUT": "1", "PYTHONNOUSERSITE": "1"}
                        environment.pop("PYTHONPATH", None)
                        self.job_process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                                            env=environment, **process_flags())
                        process = self.job_process
                    try:
                        return_code = process.wait(timeout=JOB_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        stop_worker(process)
                        process.wait(timeout=10)
                        raise RuntimeError("安装超过 30 分钟，已停止。请检查网络及下方日志后重试。")
                    if return_code:
                        raise RuntimeError(f"安装失败（退出码 {return_code}），请查看日志。已有环境可能部分更新，请检查后重试。")
        except Exception as error:
            status, message = "failed", str(error)
        finally:
            with self.lock:
                self.job_process = None
                if self.job and self.job["id"] == job_id:
                    self.job.update(status=status, message=message, finished_at=time.time())
                self.catalog_at = 0

    def create(self, name, version):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name):
            raise ValueError("环境名需以英文字母开头，仅支持字母、数字、下划线和短横线，最长 40 字符")
        if name.lower() in {"base", "root"} or version not in PYTHON_VERSIONS:
            raise ValueError("请选择有效的环境名及 Python 版本")
        if not self.conda:
            raise ValueError("未找到 Conda，不能创建环境")
        if any(item["name"].lower() == name.lower() for item in self.discover(refresh=True)):
            raise ValueError("同名环境已存在，请使用其他名称，或为已有环境安装 Python")
        return self.start_job(f"创建环境 {name}", [[self.conda, "create", "--name", name, f"python={version}", "pip", "--yes"]])

    def install_python(self, identifier, version):
        environment = self.resolve(identifier, require_python=False)
        if version not in PYTHON_VERSIONS or not environment["can_install"]:
            raise ValueError("不能修改后端或 base 环境，请新建独立环境")
        if python_path(environment["prefix"]).is_file():
            raise ValueError("该环境已有 Python，无需重复安装")
        return self.start_job(f"安装 Python · {environment['name']}", [[self.conda, "install", "--prefix", environment["prefix"], f"python={version}", "pip", "--yes"]])

    def install_packages(self, identifier, packages):
        packages = validate_packages(packages)
        environment = self.resolve(identifier)
        if not environment["can_install"]:
            raise ValueError("后端及 base 环境仅用于运行；请新建独立环境后安装依赖")
        command = self.command(environment) + ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", *packages]
        return self.start_job(f"安装依赖 · {environment['name']}", [command])

    def close(self):
        with self.lock:
            self.is_closing = True
            process = self.job_process
        if process and process.poll() is None:
            stop_worker(process)
