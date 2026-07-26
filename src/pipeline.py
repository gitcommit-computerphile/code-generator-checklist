from typing import Callable, Optional

from agents import Runner
from dotenv import load_dotenv

from src.context import PipelineContext, checklist_as_text
from src.models import Checklist, ImplementationResult
from src.snippet_agents import implementer_agent, planner_agent

load_dotenv()


def build_summary(checklist: Checklist) -> str:
    lines = ["## Task summary"]
    pending = []
    for item in checklist.items:
        if item.status == "done":
            lines.append(f"- ✅ **{item.title}** — {item.done_summary or 'done'}")
        else:
            pending.append(item)
            lines.append(f"- ⬜ **{item.title}** — not completed")
    if pending:
        lines.append(
            f"\n⚠️ {len(pending)} task(s) were not completed — review the code to confirm."
        )
    return "\n".join(lines)


async def run_pipeline(
    request: str,
    on_update: Optional[Callable[[Checklist], None]] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> tuple[Checklist, ImplementationResult, str]:
    """Run planner -> implementer and assemble the final summary.

    The implementer works through the checklist one task at a time: each task is
    marked "in_progress", implemented, then marked "done" before the next one starts.
    on_update receives the checklist whenever it changes; on_stage reports pipeline stages.
    """
    # Step 1: Planner turns the request into a checklist.
    if on_stage:
        on_stage("Planner is breaking the request into a checklist…")
    planner_run = await Runner.run(planner_agent, request)
    checklist = planner_run.final_output_as(Checklist)
    if on_update:
        on_update(checklist)

    # Step 2: Implementer works through the checklist one task at a time, extending
    # the same code string on each pass so the snippet stays cohesive.
    code_so_far = ""
    for item in checklist.items:
        if on_stage:
            on_stage(f"Implementing: {item.title}")
        item.status = "in_progress"
        if on_update:
            on_update(checklist)

        ctx = PipelineContext(checklist=checklist, current_task_id=item.id, on_update=on_update)
        step_input = (
            f"User request:\n{request}\n\n"
            f"Full checklist (for context):\n{checklist_as_text(checklist)}\n\n"
            f"Code written so far:\n{code_so_far or '(nothing yet)'}\n\n"
            f"Task to implement now: {item.title} — {item.description}"
        )
        step_run = await Runner.run(implementer_agent, step_input, context=ctx)
        code_so_far = step_run.final_output_as(ImplementationResult).code

        if item.status != "done":  # safety net if the model forgot to call the tool
            item.status = "done"
            item.done_summary = "Completed (not explicitly confirmed by the model)."
            if on_update:
                on_update(checklist)

    if on_stage:
        on_stage("Done.")
    result = ImplementationResult(code=code_so_far)
    return checklist, result, build_summary(checklist)