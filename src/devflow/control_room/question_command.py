import json
from pathlib import Path

import typer

from devflow.control_room import question_resume


question_app = typer.Typer(help="List, answer, and resolve human-blocking worker questions")


@question_app.command("list")
def question_list(json_output: bool = typer.Option(False, "--json", help="Print question projection as JSON.")) -> None:
    """Show worker and blocker questions without mutating evidence."""
    snapshot = question_resume.build_question_snapshot(Path.cwd())
    if json_output:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    typer.echo(question_resume.render_question_snapshot(snapshot), nl=False)


@question_app.command("show")
def question_show(
    question_id: str = typer.Argument(..., help="Question ID to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print question record as JSON."),
) -> None:
    """Show one derived or persisted question record."""
    snapshot = question_resume.build_question_snapshot(Path.cwd())
    question = next((item for item in snapshot.questions if item.question_id == question_id), None)
    if question is None:
        typer.echo(f"Unknown question id: {question_id}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"task: {question.task_id}")
    typer.echo(f"question_text: {question.question}")
    typer.echo(f"resume: {question.recommended_resume_command}")


@question_app.command("answer")
def question_answer(
    question_id: str = typer.Argument(..., help="Question ID to answer."),
    answer: str = typer.Option(..., "--answer", help="Human answer to persist as evidence."),
    resume_command: str | None = typer.Option(None, "--resume-command", help="Recommended Dev-Flow resume command."),
    json_output: bool = typer.Option(False, "--json", help="Print answer record as JSON."),
) -> None:
    """Persist a human answer without running the resume command."""
    try:
        question = question_resume.answer_question(Path.cwd(), question_id, answer=answer, resume_command=resume_command)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")
    typer.echo(f"next_safe_action: {question.recommended_resume_command}")


@question_app.command("resolve")
def question_resolve(
    question_id: str = typer.Argument(..., help="Question ID to resolve."),
    reason: str = typer.Option(..., "--reason", help="Reason this question is no longer actionable."),
    json_output: bool = typer.Option(False, "--json", help="Print resolved record as JSON."),
) -> None:
    """Persist a resolution without deleting source question evidence."""
    try:
        question = question_resume.resolve_question(Path.cwd(), question_id, reason=reason)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")
