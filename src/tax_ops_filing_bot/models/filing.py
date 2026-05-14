"""Pydantic models for FILING Jira issue drafts."""

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
    BUG = "Bug"
    TASK = "Task"
    STORY = "Story"


class ThreadMessage(BaseModel):
    """A single message from a Slack thread."""

    author: str
    timestamp: str
    text: str


class FilingIssueDraft(BaseModel):
    """Structured draft for a FILING Jira issue, inferred from a Slack thread."""

    summary: str = Field(
        ...,
        description="Concise one-line summary for the Jira issue title",
        max_length=255,
    )
    description: str = Field(
        ...,
        description="Full issue description with context from the thread",
    )
    issue_type: IssueType = Field(
        default=IssueType.TASK,
        description="Jira issue type",
    )
    priority: IssuePriority = Field(
        default=IssuePriority.MEDIUM,
        description="Issue priority",
    )
    labels: list[str] = Field(
        default_factory=list,
        description="Jira labels (e.g. jurisdiction, tax type)",
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Tax jurisdiction (city, state, county) if identifiable",
    )
    tax_type: Optional[str] = Field(
        default=None,
        description="Tax type (e.g. EIT, LST, BIRT, payroll-expense)",
    )
    tax_period: Optional[str] = Field(
        default=None,
        description="Tax period or year if mentioned (e.g. 1Q2026, 2025)",
    )
    client_or_entity: Optional[str] = Field(
        default=None,
        description="Client or entity name if mentioned",
    )
    source_channel: Optional[str] = Field(
        default=None,
        description="Slack channel where the thread originated",
    )
    source_thread_ts: Optional[str] = Field(
        default=None,
        description="Slack thread timestamp for linking back",
    )
    reporter: Optional[str] = Field(
        default=None,
        description="Slack user who initiated the thread",
    )
