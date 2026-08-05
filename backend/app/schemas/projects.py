"""Research project request schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


ProjectStatus = Literal["draft", "active", "completed", "archived", "frozen"]
ProjectRole = Literal["owner", "editor", "runner", "viewer"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str | None = Field(default=None, max_length=20_000)
    model_policy: dict = Field(default_factory=dict)
    data_policy: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    goal: str | None = Field(default=None, max_length=20_000)
    status: ProjectStatus | None = None
    model_policy: dict | None = None
    data_policy: dict | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one project field is required")
        return self


class ProjectMemberCreate(BaseModel):
    email: EmailStr
    role: Literal["editor", "runner", "viewer"]

    model_config = ConfigDict(extra="forbid")


class ProjectMemberUpdate(BaseModel):
    role: Literal["editor", "runner", "viewer"]

    model_config = ConfigDict(extra="forbid")
