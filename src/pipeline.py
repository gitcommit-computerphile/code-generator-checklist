from pathlib import Path
from typing import Callable, Optional

from agents import Runner, ToolCallItem, ToolCallOutputItem
from agents.result import RunResult
from dotenv import load_dotenv

from src.context import PipelineContext, checklist_as_text
from src.models import Checklist, ImplementationResult
from src.snippet_agents import implementer_agent, planner_agent

load_dotenv()


def _log_tool_calls(label: str, run_result: RunResult) -> None:
    """Print which tools an agent run actually called, and what they returned.

    This is here for debugging tool-call reliability (e.g. "did the model actually
    call save_code_to_file or not?") — check your terminal running `streamlit run`.
    """
    calls = [item.tool_name for item in run_result.new_items if isinstance(item, ToolCallItem)]
    outputs = [item.output for item in run_result.new_items if isinstance(item, ToolCallOutputItem)]
    print(f"[debug] {label}: tool calls = {calls or 'none'} | outputs = {outputs or 'none'}")


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
    save_dir: Optional[str] = None,
    on_update: Optional[Callable[[Checklist], None]] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> tuple[Checklist, ImplementationResult, str, Optional[Path]]:
    """Run planner -> implementer and assemble the final summary.

    The implementer works through the checklist one task at a time: each task is
    marked "in_progress", implemented, then marked "done" before the next one starts.
    If save_dir is given, a final dedicated turn (MODE B, see implementer_agent's
    instructions) asks the implementer whether the code should be saved via the
    save_code_to_file tool — kept separate from the per-task turns so the save
    decision isn't competing with mark_task_done + coding in the same turn.
    on_update receives the checklist whenever it changes; on_stage reports pipeline stages.
    Returns (checklist, result, summary, saved_path) — saved_path is None if nothing was saved.
    """
    # Step 1: Planner turns the request into a checklist.
    if on_stage:
        on_stage("Planner is breaking the request into a checklist…")
    planner_run = await Runner.run(planner_agent, request)
    checklist = planner_run.final_output_as(Checklist)
    if on_update:
        on_update(checklist)

    # Step 2: Implementer works through the checklist one task at a time, extending
    # the same code string on each pass so the snippet stays cohesive. One context
    # object is reused for the whole loop so ctx.saved_path survives across tasks.
    ctx = PipelineContext(checklist=checklist, save_dir=save_dir, on_update=on_update)

    code_so_far = ""
    for item in checklist.items:
        if on_stage:
            on_stage(f"Implementing: {item.title}")
        item.status = "in_progress"
        if on_update:
            on_update(checklist)

        ctx.current_task_id = item.id
        step_input = (
            f"User request:\n{request}\n\n"
            f"Full checklist (for context):\n{checklist_as_text(checklist)}\n\n"
            f"Code written so far:\n{code_so_far or '(nothing yet)'}\n\n"
            f"Task to implement now: {item.title} — {item.description}"
        )
        step_run = await Runner.run(implementer_agent, step_input, context=ctx)
        code_so_far = step_run.final_output_as(ImplementationResult).code
        _log_tool_calls(f"task '{item.title}'", step_run)

        if item.status != "done":  # safety net if the model forgot to call the tool
            item.status = "done"
            item.done_summary = "Completed (not explicitly confirmed by the model)."
            if on_update:
                on_update(checklist)

    # Step 3: dedicated save-check turn (MODE B) — only runs if a directory was given.
    if save_dir:
        if on_stage:
            on_stage("Checking whether the code should be saved to disk…")
        ctx.current_task_id = None
        save_check_input = (
            f"User request:\n{request}\n\n"
            f"Final code (all tasks complete):\n{code_so_far}\n\n"
            "No task left to implement — this is MODE B: decide only whether to save."
        )
        save_run = await Runner.run(implementer_agent, save_check_input, context=ctx)
        _log_tool_calls("save check", save_run)

    if on_stage:
        on_stage("Done.")
    result = ImplementationResult(code=code_so_far)
    return checklist, result, build_summary(checklist), ctx.saved_path