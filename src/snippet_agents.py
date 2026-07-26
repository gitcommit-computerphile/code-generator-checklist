from agents import Agent

from src.context import PipelineContext, get_checklist, mark_task_done
from src.models import Checklist, ImplementationResult

PLANNER_MODEL = "gpt-5.4-mini"
IMPLEMENTER_MODEL = "gpt-5.4-mini"

planner_agent = Agent(
    name="Planner",
    model=PLANNER_MODEL,
    output_type=Checklist,
    instructions=(
        "You are a planning agent. The user wants a code snippet. Break their request "
        "into a checklist of 3 to 7 concrete, implementable tasks.\n"
        "- Each task must describe one specific piece of the implementation "
        "(e.g. 'define the function signature with type hints', 'add retry loop with "
        "exponential backoff', 'handle timeout errors').\n"
        "- Do NOT include tasks about testing, deployment, or documentation unless the "
        "user explicitly asked for them.\n"
        "- Number tasks sequentially starting at 1, all with status 'pending'.\n"
        "- Set 'language' to the programming language the snippet should be written in "
        "(infer it from the request; default to python if unclear)."
    ),
)

implementer_agent = Agent[PipelineContext](
    name="Implementer",
    model=IMPLEMENTER_MODEL,
    output_type=ImplementationResult,
    tools=[get_checklist, mark_task_done],
    instructions=(
        "You are an implementation agent working through a checklist one task at a time. "
        "Each turn you are given: the user's original request, the FULL checklist (for "
        "context, so the code stays consistent with what's still to come), the code "
        "written so far (may be empty on the first task), and exactly ONE task to "
        "implement right now.\n"
        "Work like this:\n"
        "1. Extend the existing code to satisfy ONLY that one task. Keep everything "
        "already written intact unless it must change for consistency.\n"
        "2. Call mark_task_done with a one-line summary of how the code satisfies the "
        "task — only after the code actually covers it.\n"
        "3. Return the COMPLETE, up-to-date code (not just the new part) as your output.\n"
        "Do not implement other tasks yet, even if it seems convenient — they'll come in "
        "later turns. The code must be self-contained and runnable as-is."
    ),
)