"""Filing issue draft model — the structured output from LLM inference."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IssuePriority(str, Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"


class IssueType(str, Enum):
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    SUB_TASK = "Sub-task"


class FilingIssueDraft(BaseModel):
    """LLM-inferred Jira issue fields for the FILING project."""

    summary: str = Field(max_length=255, description="Jira issue summary / title")
    description: str = Field(description="Jira issue description (markdown)")
    issue_type: IssueType = Field(default=IssueType.TASK)
    priority: IssuePriority = Field(default=IssuePriority.MEDIUM)
    labels: list[str] = Field(default_factory=list)
    parent_key: Optional[str] = Field(
        default=None,
        description="Epic key if the issue should be a child (e.g. 'FILING-100')",
    )
    assignee_hint: Optional[str] = Field(
        default=None,
        description="Slack username or display name the LLM thinks should own this",
    )
