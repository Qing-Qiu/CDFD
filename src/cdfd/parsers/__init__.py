from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from cdfd.models import (
    CDFDGraph,
    CDFDProject,
    Edge,
    GraphStructure,
    ModuleInfo,
    Node,
    ProcessSpec,
    StructureBranch,
)


class ParseError(ValueError):
    """Raised when CDFD input cannot be parsed into the common model."""


SUPPORTED_FORMATS = {"json", "yaml", "yml", "csv"}


def infer_format(path: str | Path) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in SUPPORTED_FORMATS:
        return "yaml" if suffix == "yml" else suffix
    raise ParseError(f"Cannot infer input format from extension '.{suffix}'.")


def parse_cdfd(
    content: str,
    input_format: str,
    *,
    start: str | None = None,
    ends: str | list[str] | None = None,
) -> CDFDGraph:
    fmt = input_format.lower()
    if fmt == "yml":
        fmt = "yaml"

    if fmt == "json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON: {exc}") from exc
        return _graph_from_mapping(data, start_override=start, ends_override=ends)

    if fmt == "yaml":
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ParseError(f"Invalid YAML: {exc}") from exc
        return _graph_from_mapping(data, start_override=start, ends_override=ends)

    if fmt == "csv":
        return _graph_from_csv(content, start=start, ends=ends)

    raise ParseError(f"Unsupported input format: {input_format}")


def parse_project(
    content: str,
    input_format: str,
    *,
    start: str | None = None,
    ends: str | list[str] | None = None,
) -> CDFDProject:
    fmt = input_format.lower()
    if fmt == "yml":
        fmt = "yaml"

    if fmt == "csv":
        graph = _graph_from_csv(content, start=start, ends=ends)
        return CDFDProject(graphs={"main": graph}, entry_graph="main")

    if fmt == "json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON: {exc}") from exc
        return _project_from_mapping(data, start_override=start, ends_override=ends)

    if fmt == "yaml":
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ParseError(f"Invalid YAML: {exc}") from exc
        return _project_from_mapping(data, start_override=start, ends_override=ends)

    raise ParseError(f"Unsupported input format: {input_format}")


def _project_from_mapping(
    data: Any,
    *,
    start_override: str | None,
    ends_override: str | list[str] | None,
) -> CDFDProject:
    if not isinstance(data, dict):
        raise ParseError("Top-level CDFD project input must be an object.")

    raw_graphs = data.get("graphs", data.get("cdfds"))
    has_project_shape = raw_graphs is not None or "module" in data or "processes" in data

    if not has_project_shape:
        graph = _graph_from_mapping(data, start_override=start_override, ends_override=ends_override)
        return CDFDProject(graphs={"main": graph}, entry_graph="main", metadata={})

    module = _parse_module(data.get("module"))
    processes = _parse_processes(data.get("processes", {}))
    graphs = _parse_graphs(raw_graphs)
    entry_graph = _select_entry_graph(data, module, graphs)
    metadata = _coerce_metadata(data.get("metadata"))

    for process in processes.values():
        if process.decom and process.decom not in graphs:
            raise ParseError(f"Process '{process.id}' decomposes to missing graph '{process.decom}'.")

    return CDFDProject(
        graphs=graphs,
        entry_graph=entry_graph,
        module=module,
        processes=processes,
        metadata=metadata,
    )


def _parse_module(raw_module: Any) -> ModuleInfo | None:
    if raw_module is None:
        return None
    if not isinstance(raw_module, dict):
        raise ParseError("'module' must be an object.")

    known = {"name", "const", "type", "types", "var", "behav", "metadata"}
    metadata = _metadata_with_unknown_fields(raw_module, known)
    return ModuleInfo(
        name=_optional_str(raw_module.get("name")),
        const=_coerce_any_list(raw_module.get("const")),
        types=_coerce_any_list(raw_module.get("type", raw_module.get("types"))),
        var=_coerce_any_list(raw_module.get("var")),
        behav=_optional_str(raw_module.get("behav")),
        metadata=metadata,
    )


def _parse_processes(raw_processes: Any) -> dict[str, ProcessSpec]:
    if raw_processes in (None, ""):
        return {}

    if isinstance(raw_processes, dict):
        iterable = []
        for process_id, process_value in raw_processes.items():
            if isinstance(process_value, dict):
                iterable.append({"id": process_id, **process_value})
            else:
                iterable.append({"id": process_id, "label": str(process_value)})
    elif isinstance(raw_processes, list):
        iterable = raw_processes
    else:
        raise ParseError("'processes' must be a list or object.")

    processes: dict[str, ProcessSpec] = {}
    for raw_process in iterable:
        if isinstance(raw_process, str):
            process = ProcessSpec(id=raw_process)
        elif isinstance(raw_process, dict):
            process_id = raw_process.get("id")
            if not process_id:
                raise ParseError("Each process object must contain an 'id'.")
            known = {
                "id",
                "label",
                "inputs",
                "outputs",
                "pre",
                "post",
                "decom",
                "decomposition",
                "metadata",
            }
            metadata = _metadata_with_unknown_fields(raw_process, known)
            process = ProcessSpec(
                id=str(process_id),
                label=_optional_str(raw_process.get("label")),
                inputs=_coerce_id_list(raw_process.get("inputs"), "inputs"),
                outputs=_coerce_id_list(raw_process.get("outputs"), "outputs"),
                pre=_optional_str(raw_process.get("pre")),
                post=_optional_str(raw_process.get("post")),
                decom=_optional_str(raw_process.get("decom", raw_process.get("decomposition"))),
                metadata=metadata,
            )
        else:
            raise ParseError("Each process must be either a string or an object.")

        if process.id in processes:
            raise ParseError(f"Duplicate process id: {process.id}")
        processes[process.id] = process

    return processes


def _parse_graphs(raw_graphs: Any) -> dict[str, CDFDGraph]:
    if not isinstance(raw_graphs, dict) or not raw_graphs:
        raise ParseError("Project input must contain a non-empty 'graphs' object.")

    graphs: dict[str, CDFDGraph] = {}
    for graph_name, raw_graph in raw_graphs.items():
        if not isinstance(raw_graph, dict):
            raise ParseError(f"Graph '{graph_name}' must be an object.")
        graph = _graph_from_mapping(raw_graph, start_override=None, ends_override=None)
        graphs[str(graph_name)] = graph
    return graphs


def _select_entry_graph(
    data: dict[str, Any],
    module: ModuleInfo | None,
    graphs: dict[str, CDFDGraph],
) -> str:
    entry_graph = _optional_str(data.get("entry_graph")) or _optional_str(data.get("behav"))
    if not entry_graph and module and module.behav:
        entry_graph = module.behav
    if not entry_graph:
        entry_graph = next(iter(graphs))
    if entry_graph not in graphs:
        raise ParseError(f"Entry graph '{entry_graph}' is not defined in graphs.")
    return entry_graph


def _graph_from_mapping(
    data: Any,
    *,
    start_override: str | None,
    ends_override: str | list[str] | None,
) -> CDFDGraph:
    if not isinstance(data, dict):
        raise ParseError("Top-level CDFD input must be an object.")

    raw_edges = data.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        raise ParseError("CDFD input must contain a non-empty 'edges' list.")

    nodes = _parse_nodes(data.get("nodes", []))
    edges = _parse_edges(raw_edges)
    structures = _parse_structures(data.get("structures", []))

    if not nodes:
        for edge in edges:
            nodes.setdefault(edge.source, Node(id=edge.source))
            nodes.setdefault(edge.target, Node(id=edge.target))

    start = start_override or data.get("start")
    raw_ends = ends_override if ends_override is not None else data.get("ends", data.get("end"))
    ends = set(_coerce_id_list(raw_ends, "ends"))

    metadata = _coerce_metadata(data.get("metadata"))
    return _build_graph(
        nodes=nodes,
        edges=edges,
        start=start,
        ends=ends,
        structures=structures,
        metadata=metadata,
    )


def _parse_nodes(raw_nodes: Any) -> dict[str, Node]:
    nodes: dict[str, Node] = {}

    if raw_nodes is None:
        return nodes

    if isinstance(raw_nodes, dict):
        iterable = []
        for node_id, node_value in raw_nodes.items():
            if isinstance(node_value, dict):
                item = {"id": node_id, **node_value}
            else:
                item = {"id": node_id, "label": str(node_value)}
            iterable.append(item)
    elif isinstance(raw_nodes, list):
        iterable = raw_nodes
    else:
        raise ParseError("'nodes' must be a list or object.")

    for raw_node in iterable:
        if isinstance(raw_node, str):
            node = Node(id=raw_node)
        elif isinstance(raw_node, dict):
            node_id = raw_node.get("id")
            if not node_id:
                raise ParseError("Each node object must contain an 'id'.")
            known = {"id", "type", "label", "metadata"}
            metadata = _metadata_with_unknown_fields(raw_node, known)
            node = Node(
                id=str(node_id),
                type=str(raw_node.get("type", "process")),
                label=_optional_str(raw_node.get("label")),
                metadata=metadata,
            )
        else:
            raise ParseError("Each node must be either a string or an object.")

        if node.id in nodes:
            raise ParseError(f"Duplicate node id: {node.id}")
        nodes[node.id] = node

    return nodes


def _parse_edges(raw_edges: list[Any]) -> list[Edge]:
    edges: list[Edge] = []
    seen_ids: set[str] = set()

    for index, raw_edge in enumerate(raw_edges, start=1):
        if not isinstance(raw_edge, dict):
            raise ParseError("Each edge must be an object.")

        source = raw_edge.get("source", raw_edge.get("from"))
        target = raw_edge.get("target", raw_edge.get("to"))
        if not source or not target:
            raise ParseError("Each edge must contain 'from'/'to' or 'source'/'target'.")

        edge_id = str(raw_edge.get("id") or f"e{index}")
        if edge_id in seen_ids:
            raise ParseError(f"Duplicate edge id: {edge_id}")
        seen_ids.add(edge_id)

        known = {
            "id",
            "source",
            "target",
            "from",
            "to",
            "kind",
            "data",
            "condition",
            "label",
            "metadata",
        }
        metadata = _metadata_with_unknown_fields(raw_edge, known)
        edges.append(
            Edge(
                id=edge_id,
                source=str(source),
                target=str(target),
                kind=str(raw_edge.get("kind", "flow")),
                data=_coerce_id_list(raw_edge.get("data"), "data"),
                condition=_optional_str(raw_edge.get("condition")),
                label=_optional_str(raw_edge.get("label")),
                metadata=metadata,
            )
        )

    return edges


def _parse_structures(raw_structures: Any) -> list[GraphStructure]:
    if raw_structures in (None, ""):
        return []
    if isinstance(raw_structures, dict):
        iterable = []
        for structure_id, structure_value in raw_structures.items():
            if isinstance(structure_value, dict):
                iterable.append({"id": structure_id, **structure_value})
            else:
                iterable.append({"id": structure_id, "kind": str(structure_value)})
    elif isinstance(raw_structures, list):
        iterable = raw_structures
    else:
        raise ParseError("'structures' must be a list or object.")

    structures: list[GraphStructure] = []
    seen_ids: set[str] = set()
    for index, raw_structure in enumerate(iterable, start=1):
        if not isinstance(raw_structure, dict):
            raise ParseError("Each structure must be an object.")

        structure_id = _optional_str(raw_structure.get("id")) or f"s{index}"
        if structure_id in seen_ids:
            raise ParseError(f"Duplicate structure id: {structure_id}")
        seen_ids.add(structure_id)

        kind = _optional_str(raw_structure.get("kind", raw_structure.get("type")))
        if not kind:
            raise ParseError(f"Structure '{structure_id}' must contain a kind.")

        known = {
            "id",
            "kind",
            "type",
            "source",
            "target",
            "branches",
            "edges",
            "nodes",
            "data",
            "condition",
            "label",
            "metadata",
        }
        metadata = _metadata_with_unknown_fields(raw_structure, known)
        structures.append(
            GraphStructure(
                id=structure_id,
                kind=kind.lower().replace("_", "-"),
                source=_optional_str(raw_structure.get("source")),
                target=_optional_str(raw_structure.get("target")),
                branches=_parse_structure_branches(raw_structure.get("branches", []), structure_id),
                edges=_coerce_id_list(raw_structure.get("edges"), "edges"),
                nodes=_coerce_id_list(raw_structure.get("nodes"), "nodes"),
                data=_coerce_id_list(raw_structure.get("data"), "data"),
                condition=_optional_str(raw_structure.get("condition")),
                label=_optional_str(raw_structure.get("label")),
                metadata=metadata,
            )
        )

    return structures


def _parse_structure_branches(raw_branches: Any, structure_id: str) -> list[StructureBranch]:
    if raw_branches in (None, ""):
        return []
    if not isinstance(raw_branches, list):
        raise ParseError(f"Structure '{structure_id}' branches must be a list.")

    branches: list[StructureBranch] = []
    seen_ids: set[str] = set()
    for index, raw_branch in enumerate(raw_branches, start=1):
        if isinstance(raw_branch, str):
            raw_branch = {"id": raw_branch, "nodes": [raw_branch]}
        if not isinstance(raw_branch, dict):
            raise ParseError(f"Each branch in structure '{structure_id}' must be an object.")

        branch_id = _optional_str(raw_branch.get("id")) or f"b{index}"
        if branch_id in seen_ids:
            raise ParseError(f"Duplicate branch id '{branch_id}' in structure '{structure_id}'.")
        seen_ids.add(branch_id)

        known = {
            "id",
            "source",
            "target",
            "edges",
            "nodes",
            "data",
            "condition",
            "label",
            "metadata",
        }
        metadata = _metadata_with_unknown_fields(raw_branch, known)
        branches.append(
            StructureBranch(
                id=branch_id,
                source=_optional_str(raw_branch.get("source")),
                target=_optional_str(raw_branch.get("target")),
                edges=_coerce_id_list(raw_branch.get("edges"), "edges"),
                nodes=_coerce_id_list(raw_branch.get("nodes"), "nodes"),
                data=_coerce_id_list(raw_branch.get("data"), "data"),
                condition=_optional_str(raw_branch.get("condition")),
                label=_optional_str(raw_branch.get("label")),
                metadata=metadata,
            )
        )

    return branches


def _graph_from_csv(
    content: str,
    *,
    start: str | None,
    ends: str | list[str] | None,
) -> CDFDGraph:
    coerced_ends = set(_coerce_id_list(ends, "ends"))

    reader = csv.DictReader(StringIO(content))
    if reader.fieldnames is None:
        raise ParseError("CSV input must include a header row.")

    normalized_headers = {name.lower().strip(): name for name in reader.fieldnames}
    if "from" not in normalized_headers or "to" not in normalized_headers:
        raise ParseError("CSV input must contain 'from' and 'to' columns.")

    edges: list[Edge] = []
    nodes: dict[str, Node] = {}
    seen_ids: set[str] = set()

    for index, row in enumerate(reader, start=1):
        row = {key.lower().strip(): value for key, value in row.items() if key}
        source = _optional_str(row.get("from"))
        target = _optional_str(row.get("to"))
        if not source or not target:
            raise ParseError(f"CSV row {index} must include from and to values.")

        nodes.setdefault(source, Node(id=source))
        nodes.setdefault(target, Node(id=target))

        edge_id = _optional_str(row.get("id")) or f"e{index}"
        if edge_id in seen_ids:
            raise ParseError(f"Duplicate edge id: {edge_id}")
        seen_ids.add(edge_id)

        known = {"id", "from", "to", "kind", "data", "condition", "label"}
        metadata = {
            key: value
            for key, value in row.items()
            if key not in known and value not in (None, "")
        }
        edges.append(
            Edge(
                id=edge_id,
                source=source,
                target=target,
                kind=_optional_str(row.get("kind")) or "flow",
                data=_coerce_id_list(row.get("data"), "data"),
                condition=_optional_str(row.get("condition")),
                label=_optional_str(row.get("label")),
                metadata=metadata,
            )
        )

    for node_id in [node_id for node_id in [start, *coerced_ends] if node_id]:
        nodes.setdefault(node_id, Node(id=node_id))

    return _build_graph(nodes=nodes, edges=edges, start=start, ends=coerced_ends, structures=[], metadata={})


def _build_graph(
    *,
    nodes: dict[str, Node],
    edges: list[Edge],
    start: str | None,
    ends: set[str],
    structures: list[GraphStructure],
    metadata: dict[str, Any],
) -> CDFDGraph:
    if not start:
        start = _infer_start(nodes, edges)
    if not ends:
        ends = set(_infer_ends(nodes, edges))

    if not start:
        raise ParseError("CDFD input must define a start node.")
    if not ends:
        raise ParseError("CDFD input must define at least one end node.")
    if start not in nodes:
        raise ParseError(f"Start node '{start}' is not defined in nodes.")

    missing_ends = sorted(end for end in ends if end not in nodes)
    if missing_ends:
        raise ParseError(f"End node(s) not defined in nodes: {', '.join(missing_ends)}")

    for edge in edges:
        if edge.source not in nodes:
            raise ParseError(f"Edge '{edge.id}' references missing source '{edge.source}'.")
        if edge.target not in nodes:
            raise ParseError(f"Edge '{edge.id}' references missing target '{edge.target}'.")

    _validate_structures(structures, nodes, edges)

    return CDFDGraph(nodes=nodes, edges=edges, start=start, ends=ends, structures=structures, metadata=metadata)


def _validate_structures(
    structures: list[GraphStructure],
    nodes: dict[str, Node],
    edges: list[Edge],
) -> None:
    edge_ids = {edge.id for edge in edges}
    node_ids = set(nodes)

    for structure in structures:
        for node_id in [structure.source, structure.target, *structure.nodes]:
            if node_id and node_id not in node_ids:
                raise ParseError(f"Structure '{structure.id}' references missing node '{node_id}'.")
        for edge_id in structure.edges:
            if edge_id not in edge_ids:
                raise ParseError(f"Structure '{structure.id}' references missing edge '{edge_id}'.")
        for branch in structure.branches:
            branch_label = branch.id or "branch"
            for node_id in [branch.source, branch.target, *branch.nodes]:
                if node_id and node_id not in node_ids:
                    raise ParseError(
                        f"Branch '{branch_label}' in structure '{structure.id}' references missing node '{node_id}'."
                    )
            for edge_id in branch.edges:
                if edge_id not in edge_ids:
                    raise ParseError(
                        f"Branch '{branch_label}' in structure '{structure.id}' references missing edge '{edge_id}'."
                    )


def _infer_start(nodes: dict[str, Node], edges: list[Edge]) -> str:
    incoming, outgoing = _degree_maps(nodes, edges)
    candidates = sorted(node_id for node_id in nodes if incoming[node_id] == 0 and outgoing[node_id] > 0)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ParseError("CDFD input must define a start node; automatic detection found no source-only node.")
    raise ParseError(
        "CDFD input must define a start node; automatic detection found multiple candidates: "
        + ", ".join(candidates)
    )


def _infer_ends(nodes: dict[str, Node], edges: list[Edge]) -> list[str]:
    incoming, outgoing = _degree_maps(nodes, edges)
    candidates = sorted(node_id for node_id in nodes if outgoing[node_id] == 0 and incoming[node_id] > 0)
    if candidates:
        return candidates
    raise ParseError("CDFD input must define end node(s); automatic detection found no sink node.")


def _degree_maps(nodes: dict[str, Node], edges: list[Edge]) -> tuple[dict[str, int], dict[str, int]]:
    incoming = {node_id: 0 for node_id in nodes}
    outgoing = {node_id: 0 for node_id in nodes}
    for edge in edges:
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1
        incoming[edge.target] = incoming.get(edge.target, 0) + 1
    return incoming, outgoing


def _coerce_id_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    raise ParseError(f"'{field_name}' must be a string or list.")


def _coerce_any_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ParseError("'metadata' must be an object when provided.")


def _metadata_with_unknown_fields(raw: dict[str, Any], known: set[str]) -> dict[str, Any]:
    metadata = _coerce_metadata(raw.get("metadata"))
    for key, value in raw.items():
        if key not in known:
            metadata[key] = value
    return metadata


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
