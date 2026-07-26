from dataclasses import dataclass
from typing import Callable, Optional

from agents import RunContextWrapper, function_tool

from src.models import Checklist


@dataclass
class PipelineContext:
    checklist: Checklist
    current_task_id: Optional[int] = None
    on_update: Optional[Callable[[Checklist], None]] = None


STATUS_MARK = {"pending": "[pending]", "in_progress": "[in progress]", "done": "[done]"}


def checklist_as_text(checklist: Checklist) -> str:
    lines = [f"Language: {checklist.language}"]
    for item in checklist.items:
        lines.append(f"{item.id}. {STATUS_MARK[item.status]} {item.title} — {item.description}")
    return "\n".join(lines)


@function_tool
def get_checklist(ctx: RunContextWrapper[PipelineContext]) -> str:
    """Return the current checklist with the status of every task."""
    return checklist_as_text(ctx.context.checklist)


@function_tool
def mark_task_done(ctx: RunContextWrapper[PipelineContext], summary: str) -> str:
    """Mark the task you are currently implementing as done. There is no task id
    parameter on purpose — you can only ever mark the one task you were asked to
    implement in this turn, so it isn't possible to mark the wrong task done.

    Args:
        summary: A one-line summary of how the code satisfies this task.
    """
    checklist = ctx.context.checklist
    task_id = ctx.context.current_task_id
    for item in checklist.items:
        if item.id == task_id:
            item.status = "done"
            item.done_summary = summary
            if ctx.context.on_update:
                ctx.context.on_update(checklist)
            return f"Task {task_id} marked as done."
    return "Error: no active task to mark done."