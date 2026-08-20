"""R execution service."""

from services.r_executor import (
    DockerNotAvailableError,
    ExecutionResult,
    docker_available,
    execute_r_script,
    image_available,
)

__all__ = [
    "DockerNotAvailableError",
    "ExecutionResult",
    "FigureWorkflow",
    "WorkflowResult",
    "docker_available",
    "execute_r_script",
    "image_available",
]


def __getattr__(name: str):
    if name in {"FigureWorkflow", "WorkflowResult"}:
        from services.workflow import FigureWorkflow, WorkflowResult

        return {"FigureWorkflow": FigureWorkflow, "WorkflowResult": WorkflowResult}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
