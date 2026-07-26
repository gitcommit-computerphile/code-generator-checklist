import asyncio
import os

import streamlit as st
from dotenv import load_dotenv

from src.models import Checklist
from src.pipeline import run_pipeline

load_dotenv()

st.set_page_config(page_title="Code Snippet Generator", page_icon="✅", layout="wide")
st.title("✅ Multi-Agent Code Snippet Generator")
st.caption(
    "Planner breaks your request into a checklist → Implementer writes the code "
    "and ticks items off live."
)

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is not set. Add it to the .env file in the project root and reload.")
    st.stop()

request = st.text_area(
    "What code snippet do you need?",
    placeholder="e.g. a python function that fetches a URL with retries and exponential backoff",
    height=100,
)
generate = st.button("Generate", type="primary", disabled=not request.strip())

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


if generate:
    try:
        with st.spinner("Running agents…"):
            checklist, result, summary = asyncio.run(
                run_pipeline(request, on_update=render_checklist, on_stage=show_stage)
            )
        status_box.success("All done!")
        with output_box:
            st.subheader("Generated code")
            st.code(result.code, language=checklist.language)
            st.markdown(summary)
    except Exception as exc:  # surface API/agent errors in the UI instead of a stack trace
        status_box.error(f"Pipeline failed: {exc}")