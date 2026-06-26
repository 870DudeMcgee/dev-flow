from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_bootstrap_wrapper_missing_venv(tmp_path: Path) -> None:
    # Set up df script copy in the temp directory
    df_src = Path(__file__).parents[1] / "df"
    df_dest = tmp_path / "df"
    df_dest.write_text(df_src.read_text(encoding="utf-8"), encoding="utf-8")
    df_dest.chmod(0o755)

    # Run wrapper without .venv
    res = subprocess.run(
        ["./df", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Error: Virtual environment or devflow entrypoint" in res.stderr
    assert "Please install devflow in editable mode first" in res.stderr


def test_bootstrap_wrapper_healthy_venv(tmp_path: Path) -> None:
    # Set up df script copy
    df_src = Path(__file__).parents[1] / "df"
    df_dest = tmp_path / "df"
    df_dest.write_text(df_src.read_text(encoding="utf-8"), encoding="utf-8")
    df_dest.chmod(0o755)

    # Create mock .venv structure
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    
    # Write mock python that prints imported/working
    python_mock = venv_bin / "python"
    python_mock.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ] && [ \"$2\" = \"import devflow\" ]; then\n"
        "    exit 0\n"
        "fi\n"
        "exec python3 \"$@\"\n",
        encoding="utf-8"
    )
    python_mock.chmod(0o755)

    # Write mock devflow entrypoint
    devflow_mock = venv_bin / "devflow"
    devflow_mock.write_text(
        "#!/bin/sh\n"
        "echo \"mock devflow executing\"\n"
        "exit 0\n",
        encoding="utf-8"
    )
    devflow_mock.chmod(0o755)

    # Run wrapper
    res = subprocess.run(
        ["./df", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "mock devflow executing" in res.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS hidden flags are macOS-only")
def test_bootstrap_wrapper_hidden_site_packages(tmp_path: Path) -> None:
    # Set up df script copy
    df_src = Path(__file__).parents[1] / "df"
    df_dest = tmp_path / "df"
    df_dest.write_text(df_src.read_text(encoding="utf-8"), encoding="utf-8")
    df_dest.chmod(0o755)

    # Create mock .venv/lib/python3.14/site-packages
    site_packages = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages"
    site_packages.mkdir(parents=True)

    # Create venv/bin
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)

    # Mock python: fails to import devflow WHILE the hidden flag is set, and
    # succeeds once the flag has been cleared. The wrapper auto-repairs the flag,
    # so the second import attempt must pass and devflow must run.
    python_mock = venv_bin / "python"
    python_mock.write_text(
        "#!/bin/sh\n"
        f'if find "{site_packages}" -flags +hidden 2>/dev/null | grep -q .; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    python_mock.chmod(0o755)

    # Write mock devflow entrypoint
    devflow_mock = venv_bin / "devflow"
    devflow_mock.write_text(
        "#!/bin/sh\n"
        "echo mock devflow executing\n"
        "exit 0\n",
        encoding="utf-8"
    )
    devflow_mock.chmod(0o755)

    # Mark site-packages as hidden
    subprocess.run(["chflags", "hidden", str(site_packages)], check=True)

    try:
        # Run wrapper - it should auto-repair and recover.
        res = subprocess.run(
            ["./df", "--help"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        assert "auto-repairing" in res.stderr
        assert "mock devflow executing" in res.stdout
        # The hidden flag must actually be cleared after the wrapper runs.
        leftover = subprocess.run(
            ["find", str(site_packages), "-flags", "+hidden"],
            capture_output=True,
            text=True,
        )
        assert leftover.stdout.strip() == ""
    finally:
        # Clear hidden flag so tmp_path cleanup succeeds
        subprocess.run(["chflags", "nohidden", str(site_packages)])
