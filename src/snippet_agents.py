from agents import Agent

from src.context import PipelineContext, get_checklist, mark_task_done, save_code_to_file
from src.models import Checklist, ImplementationResult

PLANNER_MODEL = "gpt-5.4-mini"
IMPLEMENTER_MODEL = "gpt-5.4-mini"

planner_agent = Agent(
    name="Planner",
    model=PLANNER_MODEL,
    output_type=Checklist,
    instructions=(
        "You are a planning agent, called in two different modes depending on the "
        "input you receive:\n"
        "\n"
        "MODE A — initial draft: the user wants a code snippet. Break their request "
        "into a checklist of 3 to 7 concrete, implementable tasks.\n"
        "- Each task must describe one specific piece of the implementation "
        "(e.g. 'define the function signature with type hints', 'add retry loop with "
        "exponential backoff', 'handle timeout errors').\n"
        "- Do NOT include tasks about testing, deployment, or documentation unless the "
        "user explicitly asked for them.\n"
        "- Number tasks sequentially starting at 1, all with status 'pending'.\n"
        "\n"
        "MODE B — revise: you're given the original request, the CURRENT checklist, and "
        "human feedback about it. Produce a revised checklist that addresses the "
        "feedback exactly. Keep anything the feedback didn't mention unchanged where "
        "reasonable. Renumber tasks sequentially and reset every status to 'pending' — "
        "nothing has been implemented yet.\n"
        "\n"
        "In both modes, set 'language' to the programming language the snippet should "
        "be written in (infer it from the request; default to python if unclear)."
    ),
)

implementer_agent = Agent[PipelineContext](
    name="Implementer",
    model=IMPLEMENTER_MODEL,
    output_type=ImplementationResult,
    tools=[get_checklist, mark_task_done, save_code_to_file],
    instructions=(
        "You are an implementation agent. You are called in two different modes "
        "depending on the input you receive:\n"
        "\n"
        "MODE A — implementing one task: you're given the user's original request, the "
        "FULL checklist (for context, so the code stays consistent with what's still to "
        "come), the code written so far (may be empty on the first task), and exactly "
        "ONE task to implement right now. Extend the existing code to satisfy ONLY that "
        "task — keep everything already written intact unless it must change for "
        "consistency. Call mark_task_done with a one-line summary of how the code "
        "satisfies it, only after the code actually covers it. Do not implement other "
        "tasks yet, even if it seems convenient — they'll come in later turns.\n"
        "\n"
        "MODE B — final save check: you're given the user's original request and the "
        "fully finished code, with no task left to implement. Read the user's request "
        "text carefully and look for explicit language asking to save/write the code to "
        "a file, folder, or disk (e.g. 'save it', 'write this to a file', 'save to disk'). "
        "The mere existence of a configured save directory is NOT itself a reason to "
        "save — a directory can be configured without the user wanting this particular "
        "snippet saved. Only if the request text itself explicitly asks for saving should "
        "you call save_code_to_file with the exact final code. Otherwise call nothing and "
        "just return the code unchanged — 'no explicit request' always means don't save.\n"
        "\n"
        "In both modes, return the COMPLETE, up-to-date code (not just the new part) as "
        "your output. The code must be self-contained and runnable as-is."
    ),
)