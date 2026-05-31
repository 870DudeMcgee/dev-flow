from __future__ import annotations

from pathlib import Path

from devflow.control_room.log_sanitizer import latest_visible_log_line, sanitize_log_line
from devflow.control_room.shell_worker import _latest_log_line as worker_latest_log_line
from devflow.control_room.verification import _latest_log_line as verification_latest_log_line


def test_sanitize_log_line_strips_ansi_and_control_sequences() -> None:
    raw = "\x1b[?2026h\x1b[?25l\x1b[1Ghello\x1b[K\x1b[?25h\x1b[?2026l"

    assert sanitize_log_line(raw) == "hello"


def test_sanitize_log_line_drops_spinner_only_lines() -> None:
    assert sanitize_log_line("⠙ ⠹ ⠸ ⠼") == ""


def test_latest_visible_log_line_skips_progress_noise(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text(
        "$ /bin/sh -c run-local-model\n"
        "real status line\n"
        "\x1b[?2026h\x1b[1G⠙ \x1b[K\x1b[?2026l\n",
        encoding="utf-8",
    )

    assert latest_visible_log_line(log) == "real status line"


def test_worker_latest_log_line_uses_visible_sanitized_line(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text(
        "$ /bin/sh -c run-local-model\n"
        "ready for review\n"
        "\x1b[?2026h\x1b[1G⠙ \x1b[K\x1b[?2026l\n",
        encoding="utf-8",
    )

    assert worker_latest_log_line(log) == "ready for review"


def test_verification_latest_log_line_uses_visible_sanitized_line(tmp_path: Path) -> None:
    log = tmp_path / "verify.log"
    log.write_text(
        "$ /bin/sh -c pytest\n"
        "verification done\n"
        "\x1b[?25l\x1b[1G⠼ \x1b[K\x1b[?25h\n",
        encoding="utf-8",
    )

    assert verification_latest_log_line(log) == "verification done"
