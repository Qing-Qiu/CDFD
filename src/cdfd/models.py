from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    type: str = "process"
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    id: str
    source: str
    target: str
    kind: str = "flow"
    condition: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CDFDGraph(BaseModel):
    nodes: dict[str, Node]
    edges: list[Edge]
    start: str
    ends: set[str]
    metadata: dict[str, Any] = Field(default_factory=dict)

    def outgoing_edges(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.source == node_id]


class PathResult(BaseModel):
    nodes: list[str]
    edges: list[str]
    conditions: list[str] = Field(default_factory=list)


def model_dump(value: BaseModel) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
