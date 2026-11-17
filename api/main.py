from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.custom_runner import run_custom_code, run_builtin_code as execute_code
from api.environments import EnvironmentManager, EnvironmentBusyError
from api.environment_routes import create_environment_router
from api.library import LibraryStore, TestCasesConflictError, empty_progress, timestamp
from api.parser import get_all_templates
from torch_judge.tasks import TASKS


Difficulty = Literal["", "Easy", "Medium", "Hard"]
Status = Literal["todo", "attempted", "solved"]
MAX_TEXT_LENGTH = 1_000_000


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    difficulty: Difficulty = ""
    initial_code: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    source_url: str = Field(default="", max_length=2000)
    category_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        if not value.strip():
            raise ValueError("请填写问题标题")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def validate_source(cls, value):
        value = value.strip()
        if value and (urlsplit(value).scheme not in {"http", "https"} or not urlsplit(value).netloc):
            raise ValueError("来源链接需要使用 http:// 或 https://")
        return value


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if not value.strip():
            raise ValueError("分类名称不能为空")
        return value.strip()


class CategorySelection(BaseModel):
    category_ids: list[str] = Field(max_length=100)


class MergeCategory(BaseModel):
    target_id: str


class ProgressChange(BaseModel):
    status: Status = "todo"
    code: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    notes: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    draft_updated_at: datetime | None = None

    @field_validator("draft_updated_at")
    @classmethod
    def validate_draft_time(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("保存时间必须包含时区")
        return value


class TestCaseInput(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(default="", max_length=100_000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_case(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("请填写测试用例名称")
        if self.enabled and not self.code.strip():
            raise ValueError(f"请填写“{self.name}”的测试代码，或暂时停用该用例")
        return self


def validate_test_cases(cases):
    if len({test.id for test in cases}) != len(cases):
        raise ValueError("测试用例 ID 不能重复")
    if sum(len(test.code) for test in cases) > MAX_TEXT_LENGTH:
        raise ValueError("测试代码总长度不能超过 100 万字符")
    return cases


class TestCaseSuite(BaseModel):
    test_cases: list[TestCaseInput] = Field(default_factory=list, max_length=50)
    expected_revision: int = Field(ge=0)

    @field_validator("test_cases")
    @classmethod
    def validate_suite(cls, values):
        return validate_test_cases(values)


class SubmitRequest(BaseModel):
    code: str = Field(max_length=MAX_TEXT_LENGTH)
    tests_revision: int | None = Field(default=None, ge=0)


class LegacyRecords(BaseModel):
    solved_ids: list[str] = Field(default_factory=list, max_length=10000)
    drafts: dict[str, str] = Field(default_factory=dict, max_length=10000)

    @field_validator("drafts")
    @classmethod
    def validate_drafts(cls, values):
        if any(len(value) > MAX_TEXT_LENGTH for value in values.values()):
            raise ValueError("代码草稿过长")
        return values


class BackupTask(TaskInput):
    id: str = Field(pattern=r"^custom_[a-f0-9]{32}$")
    created_at: str
    updated_at: str
    test_cases: list[TestCaseInput] = Field(default_factory=list, max_length=50)
    tests_revision: int = Field(default=0, ge=0)

    @field_validator("test_cases")
    @classmethod
    def validate_suite(cls, values):
        return validate_test_cases(values)


class BackupCategory(CategoryInput):
    id: str = Field(min_length=1, max_length=100)
    position: int = Field(ge=0)


class BackupAssignment(BaseModel):
    task_id: str
    category_id: str


class BackupProgress(BaseModel):
    status: Status
    completion_source: Literal["manual", "tests", "legacy"] | None = None
    solved_at: str | None = None
    code: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    notes: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    draft_updated_at: str = ""
    updated_at: str = ""


class Backup(BaseModel):
    version: Literal[1]
    exported_at: str
    task_ids: list[str] = Field(max_length=10000)
    custom_tasks: list[BackupTask] = Field(max_length=10000)
    categories: list[BackupCategory] = Field(max_length=1000)
    task_categories: list[BackupAssignment] = Field(max_length=100000)
    progress: dict[str, BackupProgress] = Field(max_length=10000)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        for values in (self.custom_tasks, self.categories):
            identifiers = [value.id for value in values]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("备份中包含重复 ID")
        names = [category.name.casefold() for category in self.categories]
        if len(names) != len(set(names)):
            raise ValueError("备份中包含重名分类")
        return self


def create_app(database_path=None, environment_manager=None):
    store = LibraryStore(database_path or os.environ.get(
        "TORCHCODE_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "library.db")))
    templates = get_all_templates()
    environments = environment_manager or EnvironmentManager(store.path.with_suffix(".runtime.json"))

    @asynccontextmanager
    async def lifespan(application):
        store.initialize(set(TASKS))
        try:
            yield
        finally:
            environments.close()

    application = FastAPI(title="TorchCode UI Backend", lifespan=lifespan)
    application.state.environments = environments
    application.include_router(create_environment_router(environments))

    @application.exception_handler(EnvironmentBusyError)
    async def environment_busy(request, exception):
        return JSONResponse(status_code=409, content={"detail": str(exception)})
    application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                               allow_methods=["*"], allow_headers=["*"])

    @application.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, exception):
        return JSONResponse(status_code=409, content={"detail": "分类名称已存在，或数据关联已变化，请检查后重试"})

    @application.exception_handler(ValueError)
    async def invalid_operation(request, exception):
        return JSONResponse(status_code=400, content={"detail": str(exception)})

    @application.exception_handler(KeyError)
    async def missing_record(request, exception):
        return JSONResponse(status_code=404, content={"detail": str(exception.args[0])})

    def library_tasks(snapshot):
        assignments = {}
        for assignment in snapshot["task_categories"]:
            assignments.setdefault(assignment["task_id"], []).append(assignment["category_id"])
        builtins = [{"id": task_id, "title": task["title"], "difficulty": task.get("difficulty", ""),
                     "source": "builtin", "source_url": "", "hint": task.get("hint", ""),
                     "description": templates.get(task_id, {}).get("description", "Description not found."),
                     "initial_code": templates.get(task_id, {}).get("initial_code", "# Write your code here."),
                     "created_at": "", "updated_at": "", "test_cases": [], "tests_revision": 0} for task_id, task in TASKS.items()]
        tasks = builtins + [{**task, "source": "custom", "hint": ""} for task in snapshot["custom_tasks"]]
        return [{**task, "category_ids": assignments.get(task["id"], []),
                 "progress": snapshot["progress"].get(task["id"], empty_progress())} for task in tasks]

    def task_details(task_id):
        task = next((task for task in library_tasks(store.snapshot()) if task["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="题目不存在，可能已被删除")
        return task

    def task_summaries(tasks):
        return [{key: value for key, value in task.items() if key not in {"hint", "description", "initial_code", "progress", "test_cases", "tests_revision"}}
                | {"search_text": task["description"] + "\n" + task["progress"]["notes"],
                   "progress": {key: value for key, value in task["progress"].items() if key not in {"code", "notes"}}}
                for task in tasks]

    @application.get("/api/health")
    def health():
        return {"status": "ok", "database_id": store.database_id(), "service": "torchcode",
                "project_root": str(Path(__file__).resolve().parent.parent)}

    @application.get("/api/library")
    def get_library():
        snapshot = store.snapshot()
        return {"database_id": store.database_id(), "categories": snapshot["categories"],
                "tasks": task_summaries(library_tasks(snapshot))}

    @application.get("/api/tasks")
    def list_tasks():
        return task_summaries(library_tasks(store.snapshot()))

    @application.post("/api/tasks", status_code=201)
    def create_task(request: TaskInput):
        return task_details(store.create_task(request.model_dump()))

    @application.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        return task_details(task_id)

    @application.put("/api/tasks/{task_id}")
    def update_task(task_id: str, request: TaskInput):
        if task_details(task_id)["source"] != "custom":
            raise HTTPException(status_code=400, detail="内置题目内容由判题引擎维护，可以调整分类或添加个人解法")
        store.update_task(task_id, request.model_dump())
        return task_details(task_id)

    @application.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str):
        store.delete_task(task_id)
        return {"deleted": True}

    @application.put("/api/tasks/{task_id}/categories")
    def assign_categories(task_id: str, request: CategorySelection):
        task_details(task_id)
        store.assign_categories(task_id, request.category_ids)
        return {"saved": True}

    @application.put("/api/tasks/{task_id}/tests")
    def save_test_cases(task_id: str, request: TestCaseSuite):
        if task_details(task_id)["source"] != "custom":
            raise HTTPException(status_code=400, detail="内置题目使用原有测试用例；自建问题可以编辑测试用例")
        try:
            store.save_test_cases(task_id, [test.model_dump() for test in request.test_cases], request.expected_revision)
        except TestCasesConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return task_details(task_id)

    @application.patch("/api/tasks/{task_id}/progress")
    def update_progress(task_id: str, request: ProgressChange):
        task = task_details(task_id)
        changes = request.model_dump(exclude_unset=True)
        if task["source"] == "builtin" and changes.get("status") == "solved":
            raise HTTPException(status_code=400, detail="内置题目通过运行测试标记完成")
        if "draft_updated_at" in changes:
            changes["draft_updated_at"] = (request.draft_updated_at.astimezone(timezone.utc).isoformat(timespec="milliseconds")
                                            if request.draft_updated_at else timestamp())
        return store.update_progress(task_id, changes)

    @application.post("/api/submit/{task_id}")
    def submit_code(task_id: str, request: SubmitRequest):
        task = task_details(task_id)
        if task["source"] == "custom":
            if request.tests_revision is not None and request.tests_revision != task["tests_revision"]:
                raise HTTPException(status_code=409, detail="测试用例已更新，请刷新后重新运行")
            with environments.lease() as (environment, command):
                result = run_custom_code(request.code, task["test_cases"], **({"command_prefix": command} if command else {}))
            result["environment"] = {"id": environment["id"], "name": environment["name"]}
            status = "solved" if result.get("mode") == "tests" and result.get("success") else "attempted"
            if status == "solved" or task["progress"]["status"] != "solved":
                try:
                    result["progress"] = store.update_progress(task_id, {"status": status}, "tests", task["tests_revision"])
                except TestCasesConflictError:
                    result["warning"] = "运行期间测试用例已修改。本次结果对应旧用例，未更新完成状态，请重新运行。"
            return result
        with environments.lease() as (environment, command):
            result = execute_code(task_id, request.code, **({"command_prefix": command} if command else {}))
        result["environment"] = {"id": environment["id"], "name": environment["name"]}
        if result.get("success"):
            result["progress"] = store.update_progress(task_id, {"status": "solved"}, "tests")
        if not result.get("success") and task["progress"]["status"] != "solved":
            result["progress"] = store.update_progress(task_id, {"status": "attempted"}, "tests")
        return result

    @application.post("/api/categories", status_code=201)
    def create_category(request: CategoryInput):
        category_id = store.create_category(request.name)
        return next(category for category in store.snapshot()["categories"] if category["id"] == category_id)

    @application.put("/api/categories/order")
    def reorder_categories(request: CategorySelection):
        store.reorder_categories(request.category_ids)
        return {"saved": True}

    @application.put("/api/categories/{category_id}")
    def rename_category(category_id: str, request: CategoryInput):
        store.rename_category(category_id, request.name)
        return {"saved": True}

    @application.delete("/api/categories/{category_id}")
    def delete_category(category_id: str):
        store.delete_category(category_id)
        return {"deleted": True}

    @application.post("/api/categories/{category_id}/merge")
    def merge_category(category_id: str, request: MergeCategory):
        store.delete_category(category_id, request.target_id)
        return {"merged": True}

    @application.post("/api/library/migrate")
    def migrate_legacy(request: LegacyRecords):
        known_ids = {task["id"] for task in library_tasks(store.snapshot())}
        return {"migrated": store.migrate_legacy(set(request.solved_ids), request.drafts, known_ids)}

    @application.get("/api/library/backup")
    def export_backup():
        backup = store.export_backup()
        backup["task_ids"] = list(TASKS) + [task["id"] for task in backup["custom_tasks"]]
        return backup

    @application.post("/api/library/restore")
    def import_backup(request: Backup):
        return store.import_backup(request.model_dump(), set(TASKS))

    return application


app = create_app()
