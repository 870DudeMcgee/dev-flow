from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from devflow.control_room.service import list_tasks


def create_app(repo_root: Path | None = None) -> FastAPI:
    root = (repo_root or Path.cwd()).resolve()
    app = FastAPI(title="Dev-Flow Control Room")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        tasks = list_tasks(root)
        rows = "".join(
            "<tr>"
            f"<td>{escape(task.id)}</td>"
            f"<td>{escape(task.title)}</td>"
            f"<td><span class='status {escape(task.status)}'>{escape(task.status)}</span></td>"
            f"<td>{escape(task.worker_adapter or '')}</td>"
            f"<td>{escape(task.verification_status or '')}</td>"
            f"<td>{'yes' if task.merge_ready else 'no'}</td>"
            f"<td>{escape(task.workspace_kind or '')}</td>"
            f"<td>{escape(task.branch_name or '')}</td>"
            f"<td>{escape(task.latest_log_line or '')}</td>"
            f"<td>{escape(task.log_path or '')}</td>"
            f"<td>{escape(task.result_path or '')}</td>"
            "</tr>"
            for task in tasks
        )
        return f"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta http-equiv="refresh" content="5">
            <title>Dev-Flow Control Room</title>
            <style>
              body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f7f7f4; color: #1d2528; }}
              table {{ width: 100%; border-collapse: collapse; background: white; }}
              th, td {{ text-align: left; border-bottom: 1px solid #ddd; padding: 0.65rem; vertical-align: top; }}
              th {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0; color: #59666b; }}
              .status {{ font-weight: 700; }}
              .complete {{ color: #146c43; }}
              .worker_failed, .timeout {{ color: #b42318; }}
              .running {{ color: #9a6700; }}
            </style>
          </head>
          <body>
            <h1>Dev-Flow Control Room</h1>
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Worker</th>
                  <th>Verify</th>
                  <th>Ready</th>
                  <th>Workspace</th>
                  <th>Branch</th>
                  <th>Latest Log</th>
                  <th>Log Path</th>
                  <th>Result Path</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </body>
        </html>
        """

    return app


app = create_app()


def run_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(Path.cwd()), host=host, port=port)
