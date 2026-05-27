from __future__ import annotations

import sqlite3
from pathlib import Path

from devflow.control_room.paths import db_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    worker_adapter TEXT,
    workspace_path TEXT,
    workspace_kind TEXT,
    branch_name TEXT,
    latest_log_line TEXT,
    log_path TEXT,
    result_path TEXT,
    verification_status TEXT,
    verification_command TEXT,
    verification_exit_code INTEGER,
    verification_log_path TEXT,
    merge_ready INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    timeout_seconds INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
"""


MIGRATIONS = {
    "workspace_kind": "ALTER TABLE tasks ADD COLUMN workspace_kind TEXT",
    "branch_name": "ALTER TABLE tasks ADD COLUMN branch_name TEXT",
    "verification_status": "ALTER TABLE tasks ADD COLUMN verification_status TEXT",
    "verification_command": "ALTER TABLE tasks ADD COLUMN verification_command TEXT",
    "verification_exit_code": "ALTER TABLE tasks ADD COLUMN verification_exit_code INTEGER",
    "verification_log_path": "ALTER TABLE tasks ADD COLUMN verification_log_path TEXT",
    "merge_ready": "ALTER TABLE tasks ADD COLUMN merge_ready INTEGER NOT NULL DEFAULT 0",
}


def connect(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    for column, statement in MIGRATIONS.items():
        if column not in columns:
            conn.execute(statement)
