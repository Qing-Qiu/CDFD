from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from cdfd.models import CDFDGraph, Edge, Node


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

    if not nodes:
        for edge in edges:
            nodes.setdefault(edge.source, Node(id=edge.source))
            nodes.setdefault(edge.target, Node(id=edge.target))

    start = start_override or data.get("start")
    raw_ends = ends_override if ends_override is not None else data.get("ends", data.get("end"))
    ends = set(_coerce_id_list(raw_ends, "ends"))

    metadata = _coerce_metadata(data.get("metadata"))
    return _build_graph(nodes=nodes, edges=edges, start=start, ends=ends, metadata=metadata)


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
                condition=_optional_str(raw_edge.get("condition")),
                label=_optional_str(raw_edge.get("label")),
                metadata=metadata,
            )
        )

    return edges


def _graph_from_csv(
    content: str,
    *,
    start: str | None,
    ends: str | list[str] | None,
) -> CDFDGraph:
    if not start:
        raise ParseError("CSV input requires a start node.")
    coerced_ends = set(_coerce_id_list(ends, "ends"))
    if not coerced_ends:
        raise ParseError("CSV input requires at least one end node.")

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

        known = {"id", "from", "to", "kind", "condition", "label"}
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
                condition=_optional_str(row.get("condition")),
                label=_optional_str(row.get("label")),
                metadata=metadata,
            )
        )

    for node_id in [start, *coerced_ends]:
        nodes.setdefault(node_id, Node(id=node_id))

    return _build_graph(nodes=nodes, edges=edges, start=start, ends=coerced_ends, metadata={})


def _build_graph(
    *,
    nodes: dict[str, Node],
    edges: list[Edge],
    start: str | None,
    ends: set[str],
    metadata: dict[str, Any],
) -> CDFDGraph:
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

    return CDFDGraph(nodes=nodes, edges=edges, start=start, ends=ends, metadata=metadata)


def _coerce_id_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    raise ParseError(f"'{field_name}' must be a string or list.")


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
