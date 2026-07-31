"""科研白板接口模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BoardPosition(BaseModel):
    x: float = Field(..., ge=-100_000, le=100_000)
    y: float = Field(..., ge=-100_000, le=100_000)


class BoardViewport(BoardPosition):
    zoom: float = Field(default=1, ge=0.5, le=1.6)


class BoardNode(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(..., min_length=1, max_length=120, pattern=r'^[A-Za-z0-9._:-]+$')
    type: Literal['note', 'file', 'image', 'tool']
    position: BoardPosition
    content: str | None = Field(default=None, max_length=20_000)
    file_id: str | None = Field(default=None, min_length=1, max_length=36)
    tool_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode='after')
    def validate_reference(self):
        if self.type == 'note' and self.content is None:
            self.content = ''
        if self.type in {'file', 'image'} and not self.file_id:
            raise ValueError(f'{self.type} node requires file_id')
        if self.type == 'tool' and not self.tool_id:
            raise ValueError('tool node requires tool_id')
        return self


class BoardEdge(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(..., min_length=1, max_length=120)
    source: str = Field(..., min_length=1, max_length=120)
    target: str = Field(..., min_length=1, max_length=120)
    label: str | None = Field(default=None, max_length=160)


class BoardContent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    nodes: list[BoardNode] = Field(default_factory=list, max_length=500)
    edges: list[BoardEdge] = Field(default_factory=list, max_length=1_000)
    viewport: BoardViewport = Field(default_factory=lambda: BoardViewport(x=0, y=0, zoom=1))

    @model_validator(mode='after')
    def validate_graph(self):
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError('board node ids must be unique')
        node_id_set = set(node_ids)
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError('board edge ids must be unique')
        if any(edge.source not in node_id_set or edge.target not in node_id_set for edge in self.edges):
            raise ValueError('board edge references unknown node')
        return self


def empty_board_content() -> BoardContent:
    return BoardContent(nodes=[], edges=[], viewport=BoardViewport(x=0, y=0, zoom=1))


class ResearchBoardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    content: BoardContent = Field(default_factory=empty_board_content)


class ResearchBoardUpdate(BaseModel):
    version: int = Field(..., ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    content: BoardContent | None = None
