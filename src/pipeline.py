from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from agents import Runner, ToolApprovalItem, ToolCallItem, ToolCallOutputItem
from agents.result import RunResult
from agents.run_state import RunState
from dotenv import load_dotenv

from src.context import PipelineContext, checklist_as_text
from src.models import Checklist, ImplementationResult
from src.snippet_agents import implementer_agent, planner_agent

load_dotenv()


def _log_tool_calls(label: str, run_result: RunResult) -> None:
    """Print which tools an agent run actually called, and what they returned.

    This is here for debugging tool-call reliability — check your terminal running
    `streamlit run` to see it.
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


async def generate_checklist(request: str) -> Checklist:
    """Planner MODE A: turn a fresh request into a first checklist draft."""
    run = await Runner.run(planner_agent, request)
    return run.final_output_as(Checklist)


async def revise_checklist(request: str, checklist: Checklist, feedback: str) -> Checklist:
    """Planner MODE B: revise a checklist a human has reviewed and left feedback on."""
    revise_input = (
        f"User request:\n{request}\n\n"
        f"Current checklist:\n{checklist_as_text(checklist)}\n\n"
        f"Human feedback on this checklist:\n{feedback}\n\n"
        "Revise the checklist to address this feedback."
    )
    run = await Runner.run(planner_agent, revise_input)
    return run.final_output_as(Checklist)


@dataclass
class SaveApprovalRequired:
    """The implementer tried to save code to disk; a human must approve or reject
    before the run can finish. Pass this to resume_after_save_decision()."""

    state: RunState
    approval_item: ToolApprovalItem
    checklist: Checklist
    code: str


@dataclass
class ImplementationDone:
    checklist: Checklist
    result: ImplementationResult
    summary: str
    saved_path: Optional[Path]


ImplementationOutcome = Union[ImplementationDone, SaveApprovalRequired]


async def run_implementation(
    request: str,
    checklist: Checklist,
    save_dir: Optional[str] = None,
    on_update: Optional[Callable[[Checklist], None]] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> ImplementationOutcome:
    """Run the implementer through an already human-approved checklist, one task at a
    time. Each task is marked "in_progress", implemented, then marked "done" before
    the next one starts.

    If save_dir is given, a final dedicated turn (MODE B in implementer_agent's
    instructions) asks the implementer whether the code should be saved. Because
    save_code_to_file requires approval, calling it pauses the run instead of writing
    immediately — in that case this returns a SaveApprovalRequired for the caller to
    show a human and then resolve via resume_after_save_decision().
    """
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

        if save_run.interruptions:
            return SaveApprovalRequired(
                state=save_run.to_state(),
                approval_item=save_run.interruptions[0],
                checklist=checklist,
                code=code_so_far,
            )

    if on_stage:
        on_stage("Done.")
    result = ImplementationResult(code=code_so_far)
    return ImplementationDone(checklist, result, build_summary(checklist), ctx.saved_path)


async def resume_after_save_decision(
    pending: SaveApprovalRequired,
    approve: bool,
    on_stage: Optional[Callable[[str], None]] = None,
) -> ImplementationDone:
    """Apply a human's approve/reject decision to a paused save request, then finish
    the run. The decision is remembered (always_approve/always_reject) in case the
    model tries calling save_code_to_file again in the same run."""
    if approve:
        pending.state.approve(pending.approval_item, always_approve=True)
    else:
        pending.state.reject(
            pending.approval_item,
            always_reject=True,
            rejection_message="The human reviewer did not approve saving this file.",
        )

    resumed_run = await Runner.run(implementer_agent, pending.state)
    code_so_far = resumed_run.final_output_as(ImplementationResult).code
    _log_tool_calls("save check (resumed)", resumed_run)

    ctx: PipelineContext = resumed_run.context_wrapper.context
    if on_stage:
        on_stage("Done.")
    result = ImplementationResult(code=code_so_far)
    return ImplementationDone(pending.checklist, result, build_summary(pending.checklist), ctx.saved_path)