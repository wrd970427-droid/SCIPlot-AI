"""Execution manager — sole gateway to R executor for the Generic Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from services.r_executor import ExecutionResult, execute_r_script

ExecuteFn = Callable[..., ExecutionResult]


class ExecutionManager:
    """Run generated R against a work directory. Figure agents must not call Docker directly."""

    def __init__(self, execute_fn: ExecuteFn | None = None) -> None:
        self.execute_fn = execute_fn or execute_r_script

    def execute_figure(
        self,
        r_script_path: str | Path,
        work_dir: str | Path,
    ) -> ExecutionResult:
        return self.execute_fn(Path(r_script_path), Path(work_dir))
