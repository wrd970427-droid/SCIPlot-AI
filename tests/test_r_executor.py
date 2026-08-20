"""Docker R executor tests (V0.1).

If the sciplot-r:0.1 image is present, scripts run inside Docker.
Otherwise a stub runner still exercises execute_r_script(), isolation flags,
and the success/failure contract — it does not execute R on the host.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from services.r_executor import (
    CONTAINER_IN,
    ExecutionResult,
    build_docker_command,
    execute_r_script,
    image_available,
)


def _host_dir_from_mount(mount: str, container: str) -> Path:
    marker = f":{container}:"
    idx = mount.rfind(marker)
    assert idx != -1, mount
    return Path(mount[:idx])


def _stub_runner(output_dir: Path):
    def runner(cmd, **kwargs):
        assert cmd[0] == "docker"
        assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
        assert "--read-only" in cmd
        assert "--memory" in cmd
        assert "--cpus" in cmd
        assert "--cap-drop" in cmd
        in_dir = None
        for i, token in enumerate(cmd):
            if token == "-v" and f":{CONTAINER_IN}:" in cmd[i + 1]:
                in_dir = _host_dir_from_mount(cmd[i + 1], CONTAINER_IN)
        assert in_dir is not None
        script = (in_dir / "script.R").read_text(encoding="utf-8")
        code = 0
        stdout = ""
        stderr = ""
        if "stop(" in script:
            code = 1
            stderr = "Error: intentional failure\nExecution halted\n"
        elif "ggplot" in script:
            (output_dir / "test_plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            stdout = "saved test_plot.png\n"
        else:
            stdout = "hello\n"
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr=stderr)

    return runner


def _runner(output_dir: Path):
    if image_available():
        return None
    return _stub_runner(output_dir)


def test_docker_command_enforces_sandbox_limits(tmp_path: Path) -> None:
    cmd = build_docker_command(input_dir=tmp_path / "in", output_dir=tmp_path / "out")
    joined = " ".join(cmd)
    assert "--network none" in joined
    assert "--cpus" in cmd
    assert "--memory" in cmd
    assert "--read-only" in cmd
    assert "--pids-limit" in cmd
    assert "--cap-drop" in cmd and "ALL" in cmd
    assert "no-new-privileges" in joined
    assert "--user" in cmd and "1000:1000" in cmd
    assert ":/in:ro" in joined
    assert ":/out:rw" in joined
    assert "Rscript" in cmd


def test_rejects_sensitive_host_paths(tmp_path: Path) -> None:
    out = tmp_path / "out"
    if os.name == "nt":
        dangerous = Path(os.environ.get("WINDIR", r"C:\Windows")) / "sciplot_probe.R"
    else:
        dangerous = Path("/etc/sciplot_probe.R")
    with pytest.raises(PermissionError):
        execute_r_script(dangerous, out)


def test_simple_r_script_hello(tmp_path: Path) -> None:
    script = tmp_path / "hello.R"
    script.write_text('cat("hello\\n")\n', encoding="utf-8")
    output_dir = tmp_path / "output"
    result = execute_r_script(script, output_dir, runner=_runner(output_dir))
    assert isinstance(result, ExecutionResult)
    assert result.status == "success"
    assert "hello" in result.log.lower()


def test_ggplot_generates_figure(tmp_path: Path) -> None:
    script = tmp_path / "plot.R"
    script.write_text(
        "\n".join(
            [
                "library(ggplot2)",
                "p <- ggplot(mtcars, aes(wt, mpg)) + geom_point()",
                'ggsave("test_plot.png", p, width = 80, height = 60, units = "mm", dpi = 150)',
                "",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    result = execute_r_script(script, output_dir, runner=_runner(output_dir), timeout_sec=180)
    assert result.status == "success"
    assert "test_plot.png" in result.output_files
    assert (output_dir / "test_plot.png").is_file()


def test_error_r_returns_failure(tmp_path: Path) -> None:
    script = tmp_path / "boom.R"
    script.write_text('stop("intentional failure")\n', encoding="utf-8")
    output_dir = tmp_path / "output"
    result = execute_r_script(script, output_dir, runner=_runner(output_dir))
    assert result.status == "failure"
    assert result.log
    assert "error" in result.log.lower() or "halted" in result.log.lower()


def test_local_rscript_hello_when_available(tmp_path: Path) -> None:
    from services.r_executor import find_rscript

    if not find_rscript():
        pytest.skip("Rscript not installed")
    script = tmp_path / "hello.R"
    script.write_text('cat("hello\\n")\n', encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    result = execute_r_script(script, output_dir)
    assert result.status == "success"
    assert "hello" in result.log.lower()
