from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    data: list[str] = Field(default_factory=list)
    condition: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructureBranch(BaseModel):
    id: str | None = None
    source: str | None = None
    target: str | None = None
    edges: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    condition: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphStructure(BaseModel):
    id: str
    kind: str
    source: str | None = None
    target: str | None = None
    branches: list[StructureBranch] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    condition: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CDFDGraph(BaseModel):
    nodes: dict[str, Node]
    edges: list[Edge]
    start: str
    starts: set[str] = Field(default_factory=set)
    ends: set[str]
    structures: list[GraphStructure] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def outgoing_edges(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.source == node_id]


class PathResult(BaseModel):
    nodes: list[str]
    edges: list[str]
    data: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class PathRelation(BaseModel):
    id: str
    kind: str
    path_ids: list[str]
    title: str | None = None
    structure_id: str | None = None
    branch_ids: list[str] = Field(default_factory=list)
    shared_prefix: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    reason: str | None = None


class ConsistencyIssue(BaseModel):
    id: str
    severity: str = "warning"
    rule: str
    message: str
    graph: str | None = None
    node: str | None = None
    edge: str | None = None
    process: str | None = None
    data: list[str] = Field(default_factory=list)


class PathGroup(PathRelation):
    """Backward-compatible name for older callers."""


class ModuleInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    const: list[Any] = Field(default_factory=list)
    types: list[Any] = Field(default_factory=list, alias="type")
    var: list[Any] = Field(default_factory=list)
    behav: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessSpec(BaseModel):
    id: str
    label: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    pre: str | None = None
    post: str | None = None
    decom: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CDFDProject(BaseModel):
    graphs: dict[str, CDFDGraph]
    entry_graph: str
    module: ModuleInfo | None = None
    processes: dict[str, ProcessSpec] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def entry(self) -> CDFDGraph:
        return self.graphs[self.entry_graph]


def model_dump(value: BaseModel) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
