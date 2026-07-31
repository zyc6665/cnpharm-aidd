"""Conversation and plan decision request schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    model_config = ConfigDict(extra="forbid")


class MessageCreate(BaseModel):
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: list[dict[str, Any]] = Field(min_length=1)
    branch_id: str | None = None
    model_config = ConfigDict(extra="forbid")


class MessageBranchCreate(BaseModel):
    content: list[dict[str, Any]] = Field(min_length=1)
    title: str | None = Field(default=None, max_length=200)
    model_config = ConfigDict(extra="forbid")


class PlanDecisionCreate(BaseModel):
    comment: str | None = Field(default=None, max_length=4_000)
    model_config = ConfigDict(extra="forbid")
