"""Isolated Docker runner for generated R scripts.

User R code is never evaluated on the host interpreter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

IMAGE_NAME = os.environ.get("SCIPLOT_R_IMAGE", "sciplot-r:0.1")
DEFAULT_CPUS = os.environ.get("SCIPLOT_R_CPUS", "2")
DEFAULT_MEMORY = os.environ.get("SCIPLOT_R_MEMORY", "4g")
DEFAULT_TIMEOUT_SEC = int(os.environ.get("SCIPLOT_R_TIMEOUT", "120"))
CONTAINER_IN = "/in"
CONTAINER_OUT = "/out"
SCRIPT_NAME = "script.R"

Runner = Callable[..., subprocess.CompletedProcess[str]]

_WINDOWS_FORBIDDEN = (
    Path(os.environ.get("WINDIR", r"C:\Windows")),
    Path(r"C:\Windows\System32"),
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
)
_POSIX_FORBIDDEN = (
    Path("/etc"),
    Path("/root"),
    Path("/proc"),
    Path("/sys"),
    Path("/boot"),
    Path("/dev"),
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failure"]
    output_files: list[str] = Field(default_factory=list)
    log: str = ""


class DockerNotAvailableError(RuntimeError):
    """Raised when the docker CLI or daemon cannot be used."""


def find_rscript() -> str | None:
    """Locate a host Rscript for the no-Docker demo fallback."""
    env = os.environ.get("SCIPLOT_RSCRIPT")
    if env and Path(env).is_file():
        return env
    which = shutil.which("Rscript")
    if which:
        return which
    roots = [
        Path(r"D:\Software"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "R",
        Path(r"C:\Program Files\R"),
    ]
    hits: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        hits.extend(root.glob("R-*/bin/Rscript.exe"))
        hits.extend(root.glob("R-*/bin/x64/Rscript.exe"))
        hits.extend(root.glob("Rscript.exe"))
    if not hits:
        return None
    hits.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return str(hits[0])


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "info"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def image_available(image: str = IMAGE_NAME) -> bool:
    if not docker_available():
        return False
    proc = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode == 0


def _is_forbidden(path: Path) -> bool:
    resolved = path.resolve()
    if os.name == "nt":
        drive_root = Path(resolved.drive + "\\") if resolved.drive else None
        if drive_root is not None and resolved == drive_root:
            return True
        roots = _WINDOWS_FORBIDDEN
    else:
        if resolved == Path("/"):
            return True
        roots = _POSIX_FORBIDDEN

    for root in roots:
        try:
            if not root.exists():
                continue
            base = root.resolve()
            if resolved == base or resolved.is_relative_to(base):
                return True
        except (OSError, ValueError):
            continue

    ssh_dir = Path.home() / ".ssh"
    try:
        if ssh_dir.exists() and resolved.is_relative_to(ssh_dir.resolve()):
            return True
    except (OSError, ValueError):
        pass
    return False


def _safe_file(path: Path, *, must_exist: bool) -> Path:
    resolved = Path(path).expanduser().resolve()
    if _is_forbidden(resolved):
        raise PermissionError(f"Refusing to use sensitive path: {resolved}")
    if must_exist and not resolved.is_file():
        raise FileNotFoundError(f"R script not found: {resolved}")
    return resolved


def _safe_dir(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if _is_forbidden(resolved):
        raise PermissionError(f"Refusing to use sensitive path: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise NotADirectoryError(str(resolved))
    return resolved


def _docker_mount(path: Path) -> str:
    return str(path.resolve())


def build_docker_command(
    *,
    input_dir: Path,
    output_dir: Path,
    image: str = IMAGE_NAME,
    cpus: str = DEFAULT_CPUS,
    memory: str = DEFAULT_MEMORY,
    container_name: str | None = None,
) -> list[str]:
    name = container_name or f"sciplot-r-{uuid.uuid4().hex[:12]}"
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--cpus",
        str(cpus),
        "--memory",
        str(memory),
        "--memory-swap",
        str(memory),
        "--pids-limit",
        "256",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--user",
        "1000:1000",
        "-v",
        f"{_docker_mount(input_dir)}:{CONTAINER_IN}:ro",
        "-v",
        f"{_docker_mount(output_dir)}:{CONTAINER_OUT}:rw",
        "-w",
        CONTAINER_OUT,
        image,
        "Rscript",
        "--vanilla",
        f"{CONTAINER_IN}/{SCRIPT_NAME}",
    ]


def _collect_output_files(output_dir: Path, before: set[str]) -> list[str]:
    files: list[str] = []
    for item in sorted(output_dir.iterdir(), key=lambda p: p.name.lower()):
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        if item.name not in before:
            files.append(item.name)
    return files


def execute_r_script(
    script_path: str | Path,
    output_dir: str | Path,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cpus: str = DEFAULT_CPUS,
    memory: str = DEFAULT_MEMORY,
    image: str = IMAGE_NAME,
    runner: Runner | None = None,
) -> ExecutionResult:
    """Run an R script inside the SCIPlot Docker sandbox.

    Parameters
    ----------
    script_path:
        Host path to a ``.R`` file. Copied into an isolated read-only mount.
    output_dir:
        Host directory that is mounted read-write at ``/out``.
    runner:
        Optional ``subprocess.run`` replacement for tests. Production leaves this None.
    """
    script = _safe_file(Path(script_path), must_exist=True)
    if script.suffix.lower() != ".r":
        raise ValueError("script_path must be an .R file")
    out_dir = _safe_dir(Path(output_dir))

    before = {p.name for p in out_dir.iterdir() if p.is_file()}
    container_name = f"sciplot-r-{uuid.uuid4().hex[:12]}"

    if runner is None and not docker_available():
        return _execute_local_rscript(script, out_dir, timeout_sec, before)

    with tempfile.TemporaryDirectory(prefix="sciplot-r-") as tmp:
        input_dir = Path(tmp)
        shutil.copy2(script, input_dir / SCRIPT_NAME)
        cmd = build_docker_command(
            input_dir=input_dir,
            output_dir=out_dir,
            image=image,
            cpus=cpus,
            memory=memory,
            container_name=container_name,
        )
        run = runner or subprocess.run
        started = time.time()
        try:
            proc = run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            _kill_container(container_name)
            elapsed = time.time() - started
            log = _combine_log(exc.stdout, exc.stderr)
            return ExecutionResult(
                status="failure",
                output_files=_collect_output_files(out_dir, before),
                log=f"Timeout after {timeout_sec}s (elapsed {elapsed:.1f}s).\n{log}".strip(),
            )
        except OSError as exc:
            return ExecutionResult(status="failure", output_files=[], log=str(exc))

        log = _combine_log(getattr(proc, "stdout", ""), getattr(proc, "stderr", ""))
        files = _collect_output_files(out_dir, before)
        status: Literal["success", "failure"] = "success" if proc.returncode == 0 else "failure"
        if proc.returncode != 0 and not log:
            log = f"Rscript exited with code {proc.returncode}"
        return ExecutionResult(status=status, output_files=files, log=log)


def _execute_local_rscript(
    script: Path,
    out_dir: Path,
    timeout_sec: int,
    before: set[str],
) -> ExecutionResult:
    rscript = find_rscript()
    if not rscript:
        return ExecutionResult(
            status="failure",
            output_files=[],
            log="Docker is not installed, and Rscript was not found on this machine. "
            "Install Docker Desktop and run: docker build -t sciplot-r:0.1 docker "
            "or install R and set SCIPLOT_RSCRIPT to Rscript.exe.",
        )
    cmd = [rscript, "--vanilla", str(script)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(out_dir),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        log = _combine_log(exc.stdout, exc.stderr)
        return ExecutionResult(
            status="failure",
            output_files=_collect_output_files(out_dir, before),
            log=f"Timeout after {timeout_sec}s (local Rscript).\n{log}".strip(),
        )
    except OSError as exc:
        return ExecutionResult(status="failure", output_files=[], log=str(exc))

    log = _combine_log(proc.stdout, proc.stderr)
    prefix = f"[local Rscript fallback — Docker not found]\n{rscript}\n"
    files = _collect_output_files(out_dir, before)
    status: Literal["success", "failure"] = "success" if proc.returncode == 0 else "failure"
    if proc.returncode != 0 and not log:
        log = f"Rscript exited with code {proc.returncode}"
    return ExecutionResult(status=status, output_files=files, log=prefix + log)


def _kill_container(name: str) -> None:
    if not shutil.which("docker"):
        return
    subprocess.run(
        ["docker", "kill", name],
        capture_output=True,
        timeout=15,
        encoding="utf-8",
        errors="replace",
    )


def _combine_log(stdout: str | None, stderr: str | None) -> str:
    chunks: Sequence[str] = [c for c in (stdout or "", stderr or "") if c]
    text = "\n".join(chunks).strip()
    max_len = 50_000
    if len(text) > max_len:
        return text[:max_len] + "\n...[log truncated]..."
    return text
