import asyncio
import os

import streamlit as st
from dotenv import load_dotenv

from src.models import Checklist
from src.pipeline import (
    ImplementationDone,
    SaveApprovalRequired,
    generate_checklist,
    resume_after_save_decision,
    revise_checklist,
    run_implementation,
)

load_dotenv()

st.set_page_config(page_title="Code Snippet Generator", page_icon="✅", layout="wide")
st.title("✅ Multi-Agent Code Snippet Generator")
st.caption(
    "Planner drafts a checklist you can review and edit any number of times → once "
    "approved, the Implementer writes the code, ticking items off live."
)

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is not set. Add it to the .env file in the project root and reload.")
    st.stop()

if "phase" not in st.session_state:
    st.session_state.phase = "input"

status_box = st.empty()
left, right = st.columns([1, 2])
checklist_box = left.empty()
output_box = right.container()


def render_checklist(checklist: Checklist) -> None:
    lines = [f"#### Checklist ({checklist.language})"]
    for item in checklist.items:
        if item.status == "done":
            lines.append(f"- ✅ ~~{item.title}~~  \n  {item.done_summary or ''}")
        elif item.status == "in_progress":
            lines.append(f"- 🔄 **{item.title}** _(in progress)_  \n  {item.description}")
        else:
            lines.append(f"- ⬜ **{item.title}**  \n  {item.description}")
    checklist_box.markdown("\n".join(lines))


def show_stage(message: str) -> None:
    status_box.info(message)


def reset() -> None:
    for key in ("phase", "request", "save_dir", "checklist", "pending", "final"):
        st.session_state.pop(key, None)


phase = st.session_state.phase

if phase == "input":
    request = st.text_area(
        "What code snippet do you need?",
        placeholder="e.g. a python function that fetches a URL with retries and exponential backoff",
        height=100,
    )
    save_dir = st.text_input(
        "Save to folder (optional)",
        placeholder=r"e.g. C:\Users\you\snippets — the implementer decides whether to use it",
    )
    if st.button("Draft checklist", type="primary", disabled=not request.strip()):
        try:
            with st.spinner("Planner is breaking the request into a checklist…"):
                checklist = asyncio.run(generate_checklist(request))
            st.session_state.request = request
            st.session_state.save_dir = save_dir.strip() or None
            st.session_state.checklist = checklist
            st.session_state.phase = "reviewing"
            st.rerun()
        except Exception as exc:
            st.error(f"Planning failed: {exc}")

elif phase == "reviewing":
    render_checklist(st.session_state.checklist)
    st.markdown(
        "Review the checklist above. Approve it, or describe changes and resubmit — "
        "you can revise as many times as you like."
    )
    feedback = st.text_area("Suggested changes (leave blank if none)")
    col1, col2, col3 = st.columns(3)
    if col1.button("Submit changes", disabled=not feedback.strip()):
        try:
            with st.spinner("Planner is revising the checklist…"):
                revised = asyncio.run(
                    revise_checklist(st.session_state.request, st.session_state.checklist, feedback)
                )
            st.session_state.checklist = revised
            st.rerun()
        except Exception as exc:
            st.error(f"Revision failed: {exc}")
    if col2.button("Approve checklist", type="primary"):
        st.session_state.phase = "implementing"
        st.rerun()
    if col3.button("Start over"):
        reset()
        st.rerun()

elif phase == "implementing":
    try:
        with st.spinner("Running the implementer…"):
            outcome = asyncio.run(
                run_implementation(
                    st.session_state.request,
                    st.session_state.checklist,
                    save_dir=st.session_state.save_dir,
                    on_update=render_checklist,
                    on_stage=show_stage,
                )
            )
        if isinstance(outcome, SaveApprovalRequired):
            st.session_state.pending = outcome
            st.session_state.phase = "awaiting_approval"
        else:
            st.session_state.final = outcome
            st.session_state.phase = "done"
        st.rerun()
    except Exception as exc:
        status_box.error(f"Implementation failed: {exc}")
        if st.button("Back to checklist"):
            st.session_state.phase = "reviewing"
            st.rerun()

elif phase == "awaiting_approval":
    pending: SaveApprovalRequired = st.session_state.pending
    render_checklist(pending.checklist)
    st.warning("The implementer wants to save this code to disk. Review before deciding:")
    st.code(pending.code, language=pending.checklist.language)
    st.caption(f"Target folder: {st.session_state.save_dir}")
    col1, col2 = st.columns(2)
    if col1.button("Approve save", type="primary"):
        try:
            with st.spinner("Saving…"):
                final = asyncio.run(
                    resume_after_save_decision(pending, approve=True, on_stage=show_stage)
                )
            st.session_state.final = final
            st.session_state.phase = "done"
            st.rerun()
        except Exception as exc:
            st.error(f"Could not complete the save: {exc}")
    if col2.button("Reject save"):
        try:
            with st.spinner("Finishing without saving…"):
                final = asyncio.run(
                    resume_after_save_decision(pending, approve=False, on_stage=show_stage)
                )
            st.session_state.final = final
            st.session_state.phase = "done"
            st.rerun()
        except Exception as exc:
            st.error(f"Could not finish the run: {exc}")

elif phase == "done":
    final: ImplementationDone = st.session_state.final
    render_checklist(final.checklist)
    status_box.success("All done!")
    with output_box:
        st.subheader("Generated code")
        st.code(final.result.code, language=final.checklist.language)
        st.markdown(final.summary)
        if final.saved_path:
            st.success(f"Saved to {final.saved_path}")
    if st.button("Start a new request"):
        reset()
        st.rerun()