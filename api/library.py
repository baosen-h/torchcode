"""Persistent personal library, kept separate from the built-in judge definitions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


DEFAULT_CATEGORIES = {
    "基础算子": ["relu", "softmax", "gelu", "embedding", "linear", "mlp", "weight_init"],
    "损失函数": ["cross_entropy", "dpo_loss", "grpo_loss", "ppo_loss", "opd_loss"],
    "归一化与正则化": ["layernorm", "batchnorm", "rmsnorm", "dropout"],
    "Attention": ["attention", "mha", "causal_attention", "cross_attention", "linear_attention", "sliding_window", "gqa", "flash_attention", "rope", "kv_cache"],
    "模型结构": ["gpt2_block", "moe", "lora", "vit_patch", "conv2d", "linear_regression"],
    "优化与训练": ["adam", "gradient_accumulation", "gradient_clipping", "cosine_lr"],
    "推理与分词": ["beam_search", "topk_sampling", "speculative_decoding", "int8_quantization", "bpe"],
    "训练调试": [],
}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def empty_progress():
    return {"status": "todo", "completion_source": None, "solved_at": None,
            "code": None, "notes": "", "draft_updated_at": "", "updated_at": "",
            "last_opened_at": None}


class TestCasesConflictError(Exception):
    pass


def decode_task(row):
    task = dict(row)
    task["test_cases"] = json.loads(task.pop("test_cases_json"))
    return task


class LibraryStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, builtin_ids):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS custom_tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    difficulty TEXT NOT NULL, initial_code TEXT NOT NULL, source_url TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_categories (
                    task_id TEXT NOT NULL, category_id TEXT NOT NULL
                    REFERENCES categories(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, category_id)
                );
                CREATE TABLE IF NOT EXISTS progress (
                    task_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'todo',
                    completion_source TEXT, solved_at TEXT, code TEXT, notes TEXT NOT NULL DEFAULT '',
                    draft_updated_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(custom_tasks)")}
            if "test_cases_json" not in columns:
                connection.execute("ALTER TABLE custom_tasks ADD COLUMN test_cases_json TEXT NOT NULL DEFAULT '[]'")
            if "tests_revision" not in columns:
                connection.execute("ALTER TABLE custom_tasks ADD COLUMN tests_revision INTEGER NOT NULL DEFAULT 0")
            if "problem_number" not in columns:
                connection.execute("ALTER TABLE custom_tasks ADD COLUMN problem_number INTEGER")
            progress_columns = {row["name"] for row in connection.execute("PRAGMA table_info(progress)")}
            if "last_opened_at" not in progress_columns:
                connection.execute("ALTER TABLE progress ADD COLUMN last_opened_at TEXT")
            highest_number = connection.execute("SELECT COALESCE(MAX(problem_number), ?) FROM custom_tasks", (len(builtin_ids),)).fetchone()[0]
            next_number = max(highest_number, len(builtin_ids)) + 1
            for row in connection.execute("SELECT id FROM custom_tasks WHERE problem_number IS NULL ORDER BY created_at, id").fetchall():
                connection.execute("UPDATE custom_tasks SET problem_number = ? WHERE id = ?", (next_number, row["id"]))
                next_number += 1
            highest_number = connection.execute("SELECT COALESCE(MAX(problem_number), ?) FROM custom_tasks", (len(builtin_ids),)).fetchone()[0]
            connection.execute("INSERT OR IGNORE INTO metadata VALUES ('next_problem_number', ?)", (str(highest_number + 1),))
            if connection.execute("SELECT 1 FROM metadata WHERE key = 'database_id'").fetchone():
                return
            connection.execute("INSERT INTO metadata VALUES ('database_id', ?)", (uuid4().hex,))
            for position, (name, task_ids) in enumerate(DEFAULT_CATEGORIES.items()):
                category_id = "category_" + uuid4().hex
                connection.execute("INSERT INTO categories VALUES (?, ?, ?)", (category_id, name, position))
                connection.executemany("INSERT INTO task_categories VALUES (?, ?)",
                                       [(task_id, category_id) for task_id in task_ids if task_id in builtin_ids])

    def database_id(self):
        with self.connection() as connection:
            return connection.execute("SELECT value FROM metadata WHERE key = 'database_id'").fetchone()[0]

    def snapshot(self):
        with self.connection() as connection:
            return {
                "custom_tasks": [decode_task(row) for row in connection.execute("SELECT * FROM custom_tasks ORDER BY created_at DESC")],
                "categories": [dict(row) for row in connection.execute("SELECT * FROM categories ORDER BY position, name")],
                "task_categories": [dict(row) for row in connection.execute("SELECT * FROM task_categories ORDER BY task_id, category_id")],
                "progress": {row["task_id"]: {key: row[key] for key in row.keys() if key != "task_id"}
                             for row in connection.execute("SELECT * FROM progress")},
            }

    def create_task(self, values):
        task_id = "custom_" + uuid4().hex
        now = timestamp()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_categories(connection, values["category_ids"])
            sequence = connection.execute("SELECT value FROM metadata WHERE key = 'next_problem_number'").fetchone()
            problem_number = int(sequence[0])
            connection.execute("UPDATE metadata SET value = ? WHERE key = 'next_problem_number'", (str(problem_number + 1),))
            connection.execute("""INSERT INTO custom_tasks
                               (id, title, description, difficulty, initial_code, source_url, created_at, updated_at, problem_number)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (task_id, values["title"], values["description"], values["difficulty"],
                                values["initial_code"], values["source_url"], now, now, problem_number))
            self._assign_categories(connection, task_id, values["category_ids"])
        return task_id

    def save_test_cases(self, task_id, test_cases, expected_revision):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT test_cases_json, tests_revision FROM custom_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError("未找到自建问题")
            if expected_revision != row["tests_revision"]:
                raise TestCasesConflictError("测试用例已在其他页面更新，请刷新后重试；本页草稿仍保留。")
            serialized = json.dumps(test_cases, ensure_ascii=False)
            if serialized == row["test_cases_json"]:
                return row["tests_revision"]
            connection.execute("UPDATE custom_tasks SET test_cases_json = ?, tests_revision = tests_revision + 1, updated_at = ? WHERE id = ?",
                               (serialized, timestamp(), task_id))
            connection.execute("""UPDATE progress SET status = 'attempted', completion_source = NULL,
                solved_at = NULL, updated_at = ? WHERE task_id = ? AND completion_source = 'tests'""", (timestamp(), task_id))
            return row["tests_revision"] + 1

    def update_task(self, task_id, values):
        with self.connection() as connection:
            self._validate_categories(connection, values["category_ids"])
            cursor = connection.execute("""UPDATE custom_tasks SET title = ?, description = ?, difficulty = ?,
                initial_code = ?, source_url = ?, updated_at = ? WHERE id = ?""",
                (values["title"], values["description"], values["difficulty"], values["initial_code"],
                 values["source_url"], timestamp(), task_id))
            if not cursor.rowcount:
                raise KeyError("未找到自建问题")
            self._assign_categories(connection, task_id, values["category_ids"])

    def delete_task(self, task_id):
        with self.connection() as connection:
            if not connection.execute("DELETE FROM custom_tasks WHERE id = ?", (task_id,)).rowcount:
                raise KeyError("未找到自建问题")
            connection.execute("DELETE FROM task_categories WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM progress WHERE task_id = ?", (task_id,))

    def _validate_categories(self, connection, category_ids):
        existing = {row[0] for row in connection.execute("SELECT id FROM categories")}
        if not set(category_ids).issubset(existing):
            raise ValueError("分类已变化，请刷新后重新选择")

    def _assign_categories(self, connection, task_id, category_ids):
        connection.execute("DELETE FROM task_categories WHERE task_id = ?", (task_id,))
        connection.executemany("INSERT INTO task_categories VALUES (?, ?)",
                               [(task_id, category_id) for category_id in set(category_ids)])

    def assign_categories(self, task_id, category_ids):
        with self.connection() as connection:
            self._validate_categories(connection, category_ids)
            self._assign_categories(connection, task_id, category_ids)

    def create_category(self, name):
        category_id = "category_" + uuid4().hex
        with self.connection() as connection:
            position = connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM categories").fetchone()[0]
            connection.execute("INSERT INTO categories VALUES (?, ?, ?)", (category_id, name, position))
        return category_id

    def rename_category(self, category_id, name):
        with self.connection() as connection:
            if not connection.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id)).rowcount:
                raise KeyError("未找到分类")

    def reorder_categories(self, category_ids):
        with self.connection() as connection:
            existing = {row[0] for row in connection.execute("SELECT id FROM categories")}
            if set(category_ids) != existing or len(category_ids) != len(existing):
                raise ValueError("分类列表已变化，请刷新后重新排序")
            connection.executemany("UPDATE categories SET position = ? WHERE id = ?", enumerate(category_ids))

    def delete_category(self, category_id, target_id=None):
        with self.connection() as connection:
            self._validate_categories(connection, [category_id])
            if target_id:
                if category_id == target_id:
                    raise ValueError("不能合并到同一个分类")
                self._validate_categories(connection, [target_id])
                connection.execute("""INSERT OR IGNORE INTO task_categories
                    SELECT task_id, ? FROM task_categories WHERE category_id = ?""", (target_id, category_id))
            connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def _write_progress(self, connection, task_id, values):
        connection.execute("""INSERT INTO progress
            (task_id, status, completion_source, solved_at, code, notes, draft_updated_at, updated_at, last_opened_at)
            VALUES (:task_id, :status, :completion_source, :solved_at, :code, :notes, :draft_updated_at, :updated_at, :last_opened_at)
            ON CONFLICT(task_id) DO UPDATE SET status = excluded.status,
            completion_source = excluded.completion_source, solved_at = excluded.solved_at,
            code = excluded.code, notes = excluded.notes, draft_updated_at = excluded.draft_updated_at,
            updated_at = excluded.updated_at, last_opened_at = COALESCE(excluded.last_opened_at, progress.last_opened_at)""",
            {"last_opened_at": None, "task_id": task_id, **values})

    def record_opened(self, task_id):
        opened_at = timestamp()
        with self.connection() as connection:
            connection.execute("INSERT INTO progress (task_id, updated_at, last_opened_at) "
                               "VALUES (?, ?, ?) ON CONFLICT(task_id) DO UPDATE "
                               "SET last_opened_at = excluded.last_opened_at",
                               (task_id, opened_at, opened_at))

    def update_progress(self, task_id, changes, completion_source="manual", expected_tests_revision=None):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if expected_tests_revision is not None:
                task_row = connection.execute("SELECT tests_revision FROM custom_tasks WHERE id = ?", (task_id,)).fetchone()
                if task_row is None or task_row["tests_revision"] != expected_tests_revision:
                    raise TestCasesConflictError("测试用例已修改")
            row = connection.execute("SELECT * FROM progress WHERE task_id = ?", (task_id,)).fetchone()
            values = {**empty_progress(), **(dict(row) if row else {})}
            values.pop("task_id", None)
            if "code" in changes or "notes" in changes:
                draft_time = changes.get("draft_updated_at") or timestamp()
                if draft_time >= values["draft_updated_at"]:
                    values.update({key: changes[key] for key in ("code", "notes") if key in changes})
                    values["draft_updated_at"] = draft_time
            if "status" in changes:
                should_keep_solved = completion_source == "tests" and changes["status"] == "attempted" and values["status"] == "solved"
                if not should_keep_solved:
                    values["status"] = changes["status"]
                    values["completion_source"] = completion_source if changes["status"] == "solved" else None
                    values["solved_at"] = (values["solved_at"] or timestamp()) if changes["status"] == "solved" else None
            values["updated_at"] = timestamp()
            self._write_progress(connection, task_id, values)
            return values

    def migrate_legacy(self, solved_ids, drafts, known_ids):
        migrated = 0
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for task_id in (set(solved_ids) | set(drafts)) & known_ids:
                row = connection.execute("SELECT * FROM progress WHERE task_id = ?", (task_id,)).fetchone()
                values = {**empty_progress(), **(dict(row) if row else {})}
                values.pop("task_id", None)
                has_only_visit = values["status"] == "todo" and values["code"] is None and not values["notes"] and not values["draft_updated_at"]
                if (not row or has_only_visit) and task_id in solved_ids:
                    values.update(status="solved", completion_source="legacy", solved_at=timestamp())
                if values["code"] is None and task_id in drafts:
                    values.update(code=drafts[task_id], draft_updated_at=timestamp())
                values["updated_at"] = timestamp()
                self._write_progress(connection, task_id, values)
                migrated += 1
        return migrated

    def export_backup(self):
        with self.connection() as connection:
            next_number = int(connection.execute("SELECT value FROM metadata WHERE key = 'next_problem_number'").fetchone()[0])
        return {"version": 1, "exported_at": timestamp(), "next_problem_number": next_number, **self.snapshot()}

    def _import_problem_number(self, connection, task, builtin_count):
        existing = connection.execute("SELECT problem_number FROM custom_tasks WHERE id = ?", (task["id"],)).fetchone()
        if existing and existing["problem_number"] is not None:
            return existing["problem_number"]
        next_number = int(connection.execute("SELECT value FROM metadata WHERE key = 'next_problem_number'").fetchone()[0])
        requested_number = task.get("problem_number")
        is_available = requested_number and requested_number > builtin_count and not connection.execute(
            "SELECT 1 FROM custom_tasks WHERE problem_number = ?", (requested_number,)).fetchone()
        problem_number = requested_number if is_available else next_number
        connection.execute("UPDATE metadata SET value = ? WHERE key = 'next_problem_number'",
                           (str(max(next_number, problem_number + 1)),))
        return problem_number

    def import_backup(self, backup, builtin_ids):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_ids = {row[0] for row in connection.execute("SELECT id FROM custom_tasks")}
            imported_ids = {task["id"] for task in backup["custom_tasks"]}
            known_ids = builtin_ids | existing_ids | imported_ids
            category_map = {}
            for category in backup["categories"]:
                matching = connection.execute("SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (category["name"],)).fetchone()
                category_id = matching[0] if matching else category["id"]
                category_map[category["id"]] = category_id
                if matching:
                    continue
                connection.execute("""INSERT INTO categories VALUES (?, ?, ?) ON CONFLICT(id)
                    DO UPDATE SET name = excluded.name, position = excluded.position""",
                    (category_id, category["name"], category["position"]))
            for task in backup["custom_tasks"]:
                if task["id"] in builtin_ids:
                    raise ValueError("备份中的自建问题 ID 与内置题目冲突")
                problem_number = self._import_problem_number(connection, task, len(builtin_ids))
                connection.execute("""INSERT INTO custom_tasks
                    (id, title, description, difficulty, initial_code, source_url, created_at, updated_at, test_cases_json, tests_revision, problem_number)
                    VALUES (:id, :title, :description, :difficulty, :initial_code, :source_url, :created_at, :updated_at, :test_cases_json, :tests_revision, :problem_number)
                    ON CONFLICT(id) DO UPDATE SET title = excluded.title, description = excluded.description,
                    difficulty = excluded.difficulty, initial_code = excluded.initial_code,
                    source_url = excluded.source_url, updated_at = excluded.updated_at,
                    test_cases_json = excluded.test_cases_json,
                    tests_revision = MAX(custom_tasks.tests_revision, excluded.tests_revision) + 1""",
                    {**task, "test_cases_json": json.dumps(task.get("test_cases", []), ensure_ascii=False),
                     "tests_revision": task.get("tests_revision", 0), "problem_number": problem_number})
            assignments = {}
            for assignment in backup["task_categories"]:
                task_id, category_id = assignment["task_id"], assignment["category_id"]
                if task_id not in known_ids or category_id not in category_map:
                    raise ValueError("备份中存在无效的题目或分类关联")
                assignments.setdefault(task_id, []).append(category_map[category_id])
            for task_id in set(backup["task_ids"]) | imported_ids | set(backup["progress"]) | set(assignments):
                if task_id not in known_ids:
                    raise ValueError("备份中存在未知题目的记录")
                self._assign_categories(connection, task_id, assignments.get(task_id, []))
            for task_id, progress in backup["progress"].items():
                self._write_progress(connection, task_id, progress)
            next_number = int(connection.execute("SELECT value FROM metadata WHERE key = 'next_problem_number'").fetchone()[0])
            connection.execute("UPDATE metadata SET value = ? WHERE key = 'next_problem_number'",
                               (str(max(next_number, backup.get("next_problem_number") or next_number)),))
        return {"tasks": len(imported_ids), "categories": len(category_map), "progress": len(backup["progress"])}
