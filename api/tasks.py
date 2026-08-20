"""In-memory task store for the local single-user demo."""

from __future__ import annotations

import threading
import uuid
from typing import Any


class TaskManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(self) -> str:
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[task_id] = {"status": "running", "result": None, "error": None}
        return task_id

    def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.setdefault(task_id, {})
            task["status"] = result.get("status", "success")
            task["result"] = result
            task["error"] = None

    def set_error(self, task_id: str, message: str) -> None:
        with self._lock:
            task = self._tasks.setdefault(task_id, {})
            task["status"] = "failure"
            task["result"] = {"status": "failure", "message": message}
            task["error"] = message

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.setdefault(task_id, {})
            task["status"] = "running"
            task["error"] = None

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None


task_manager = TaskManager()
