"""FastAPI routes for the local SCIPlot AI demo."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.tasks import task_manager
from services.workflow import FigureWorkflow, WorkflowResult

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"
FORBIDDEN_DOWNLOADS = {"input.csv", "upload.csv", "upload.tsv"}

router = APIRouter(prefix="/api/figure")


class RefineBody(BaseModel):
    request: str = Field(default="", description="Natural-language design refinement")
    action: str = Field(default="refine", description="refine | undo | redo")


@router.post("/generate")
async def generate_figure(
    prompt: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    suffix = Path(file.filename or "input.csv").suffix.lower() or ".csv"
    if suffix not in {".csv", ".tsv"}:
        return {
            "task_id": None,
            "status": "failure",
            "message": "Invalid input file",
        }

    task_id = task_manager.create()
    work_dir = OUTPUT_ROOT / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    upload_path = work_dir / f"upload{suffix}"
    payload = await file.read()
    upload_path.write_bytes(payload)

    thread = threading.Thread(
        target=_run_task,
        args=(task_id, prompt, upload_path, work_dir),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "running"}


@router.post("/refine/{task_id}")
async def refine_figure(task_id: str, body: RefineBody) -> dict:
    work_dir = OUTPUT_ROOT / task_id
    if not work_dir.is_dir() or task_manager.get(task_id) is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    action = (body.action or "refine").strip().lower()
    if action not in {"refine", "undo", "redo"}:
        raise HTTPException(status_code=400, detail="action must be refine|undo|redo")
    if action == "refine" and not body.request.strip():
        raise HTTPException(status_code=400, detail="request text required for refine")

    task_manager.mark_running(task_id)
    thread = threading.Thread(
        target=_run_refine,
        args=(task_id, work_dir, body.request, action),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "running"}


@router.get("/result/{task_id}")
def figure_result(task_id: str) -> dict:
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    result = task.get("result") or {}
    return {
        "task_id": task_id,
        "status": task.get("status", "running"),
        "figure_files": result.get("output_files", []),
        "qc_report": result.get("qc_report"),
        "spec": result.get("spec"),
        "previous_spec": result.get("previous_spec"),
        "modifications": result.get("modifications", []),
        "history": result.get("history"),
        "previous_version": result.get("previous_version", 0),
        "current_version": result.get("current_version", 0),
        "r_script_path": result.get("r_script_path", ""),
        "questions": result.get("questions", []),
        "missing_parameters": result.get("missing_parameters", []),
        "message": result.get("message", ""),
        "log": result.get("log", ""),
        "result": result,
    }


@router.get("/download/{task_id}/{filename}")
def download_artifact(task_id: str, filename: str):
    name = Path(filename).name
    if name != filename or name in FORBIDDEN_DOWNLOADS or name.startswith("."):
        raise HTTPException(status_code=400, detail="File is not downloadable")
    path = OUTPUT_ROOT / task_id / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)


def _run_task(task_id: str, prompt: str, upload_path: Path, work_dir: Path) -> None:
    try:
        result: WorkflowResult = FigureWorkflow().generate_figure(
            prompt,
            upload_path,
            work_dir=work_dir,
        )
        task_manager.set_result(task_id, result.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 — demo boundary
        task_manager.set_error(task_id, str(exc))


def _run_refine(task_id: str, work_dir: Path, request: str, action: str) -> None:
    try:
        result = FigureWorkflow().refine_figure(work_dir, request, action=action)  # type: ignore[arg-type]
        task_manager.set_result(task_id, result.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        task_manager.set_error(task_id, str(exc))
