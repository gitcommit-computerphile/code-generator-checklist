from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    id: int = Field(description="Sequential task id starting at 1")
    title: str = Field(description="Short name of the task")
    description: str = Field(description="What exactly needs to be implemented")
    status: Literal["pending", "in_progress", "done"] = "pending"
    done_summary: Optional[str] = Field(
        default=None, description="One-line summary of how the task was completed"
    )


class Checklist(BaseModel):
    language: str = Field(description="Programming language of the snippet, lowercase, e.g. 'python'")
    items: list[ChecklistItem]


class ImplementationResult(BaseModel):
    code: str = Field(
        description="The complete, up-to-date code snippet, including every task done so far"
    )