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

    def incoming_edges(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.target == node_id]

    def get_input_port_count(
        self,
        node_id: str,
        processes: dict[str, ProcessSpec] | None = None,
    ) -> int:
        if processes and node_id in processes:
            port_count = processes[node_id].metadata.get("input_port_count")
            if port_count is not None:
                try:
                    return max(1, int(port_count))
                except (TypeError, ValueError):
                    pass
        return 1

    def uses_or_input_ports(
        self,
        node_id: str,
        processes: dict[str, ProcessSpec] | None = None,
    ) -> bool:
        """Return True when side input ports are combined with OR semantics."""
        if processes and node_id in processes and processes[node_id].inputs:
            return False
        return self.get_input_port_count(node_id, processes) > 1

    def get_node_input_port_groups(
        self,
        node_id: str,
        processes: dict[str, ProcessSpec] | None = None,
    ) -> tuple[list[list[Edge]], list[Edge]]:
        """Return side input port groups (OR) and top/bottom data-store edges."""
        incoming = [
            edge
            for edge in self.incoming_edges(node_id)
            if edge.kind.lower().replace("_", "-") != "control"
        ]
        datastore_edges: list[Edge] = []
        side_edges: list[Edge] = []
        for edge in incoming:
            if _edge_is_datastore_connection(edge):
                datastore_edges.append(edge)
            else:
                side_edges.append(edge)

        if not self.uses_or_input_ports(node_id, processes):
            return ([side_edges] if side_edges else []), datastore_edges

        port_count = self.get_input_port_count(node_id, processes)
        grouped: dict[int, list[Edge]] = {index: [] for index in range(port_count)}
        for edge in side_edges:
            port = _edge_input_port(edge, port_count)
            grouped.setdefault(port, []).append(edge)
        return [grouped[index] for index in sorted(grouped) if grouped[index]], datastore_edges

    def get_node_required_inputs(
        self,
        node_id: str,
        processes: dict[str, ProcessSpec] | None = None,
    ) -> set[str]:
        """Return data inputs required before a node can be activated (AND semantics)."""
        if processes and node_id in processes and processes[node_id].inputs:
            return set(processes[node_id].inputs)
        required: set[str] = set()
        for edge in self.incoming_edges(node_id):
            if edge.kind.lower().replace("_", "-") != "control":
                required.update(edge.data)
        return required


class ConcurrentPathNode(BaseModel):
    """Tree node for nested sequential / parallel path structure."""

    kind: str  # "node", "sequential", "parallel"
    node_id: str | None = None
    children: list[ConcurrentPathNode] = Field(default_factory=list)
    label: str | None = None


class ConcurrentPathResult(BaseModel):
    """A functional scenario path that may contain parallel branches."""

    root: ConcurrentPathNode
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    notation: str | None = None


class PathResult(BaseModel):
    nodes: list[str]
    edges: list[str]
    data: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    concurrent: ConcurrentPathNode | None = None


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


class ScenarioOperation(BaseModel):
    process: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    pre: str | None = None
    post: str | None = None


class FunctionalScenario(BaseModel):
    id: str
    kind: str = "single-path"
    path_ids: list[str] = Field(default_factory=list)
    concurrent_path: ConcurrentPathNode | None = None
    notation: str | None = None
    source: str | None = None
    sink: str | None = None
    input_data: list[str] = Field(default_factory=list)
    output_data: list[str] = Field(default_factory=list)
    operations: list[ScenarioOperation] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    description: str | None = None


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


def _edge_is_datastore_connection(edge: Edge) -> bool:
    to_meta = edge.metadata.get("to", {})
    belong_to_type = str(to_meta.get("belongToType", "")).lower().replace("_", "")
    return belong_to_type in {"processtopbottom", "processtop", "processbottom"}


def _edge_input_port(edge: Edge, port_count: int) -> int:
    raw_port = edge.metadata.get("input_port")
    if raw_port is not None:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            port = 0
    else:
        to_meta = edge.metadata.get("to", {})
        connector = to_meta.get("belongToConnector") or to_meta.get("connectorIndex")
        if connector is not None and str(connector).strip() not in {"", "-1"}:
            try:
                port = int(str(connector).strip())
            except ValueError:
                port = 0
        else:
            port = 0
    if port_count <= 0:
        return 0
    return max(0, min(port, port_count - 1))
