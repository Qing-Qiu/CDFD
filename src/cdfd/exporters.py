from __future__ import annotations

import csv
import html
import json
from collections import defaultdict, deque
from io import StringIO
from typing import Iterable

from cdfd.models import CDFDGraph, CDFDProject, PathResult, model_dump


def export_paths(paths: list[PathResult], output_format: str) -> str:
    fmt = output_format.lower()
    if fmt == "text":
        return _export_text(paths)
    if fmt == "json":
        return json.dumps([model_dump(path) for path in paths], indent=2)
    if fmt == "csv":
        return _export_csv(paths)
    if fmt == "markdown":
        return _export_markdown(paths)
    raise ValueError(f"Unsupported output format: {output_format}")


def graph_to_dict(graph: CDFDGraph) -> dict[str, object]:
    return {
        "start": graph.start,
        "ends": sorted(graph.ends),
        "nodes": [model_dump(node) for node in graph.nodes.values()],
        "edges": [model_dump(edge) for edge in graph.edges],
        "metadata": graph.metadata,
    }


def project_to_dict(project: CDFDProject) -> dict[str, object]:
    graphs = {name: graph_to_dict(graph) for name, graph in project.graphs.items()}
    return {
        "entry_graph": project.entry_graph,
        "module": model_dump(project.module) if project.module else None,
        "processes": [model_dump(process) for process in project.processes.values()],
        "graphs": graphs,
        "graph_count": len(project.graphs),
        "process_count": len(project.processes),
        "total_nodes": sum(len(graph.nodes) for graph in project.graphs.values()),
        "total_edges": sum(len(graph.edges) for graph in project.graphs.values()),
        "metadata": project.metadata,
    }


def render_svg(graph: CDFDGraph, paths: list[PathResult] | None = None, graph_name: str | None = None) -> str:
    levels = _assign_levels(graph)
    ordered_levels: dict[int, list[str]] = defaultdict(list)
    for node_id, level in levels.items():
        ordered_levels[level].append(node_id)

    for level_nodes in ordered_levels.values():
        level_nodes.sort()

    positions: dict[str, tuple[int, int]] = {}
    for level, node_ids in sorted(ordered_levels.items()):
        for row, node_id in enumerate(node_ids):
            positions[node_id] = (80 + level * 220, 70 + row * 110)

    width = max((x for x, _ in positions.values()), default=80) + 180
    height = max((y for _, y in positions.values()), default=70) + 100
    highlighted_edges = _highlighted_edges(paths[0].edges if paths else [], graph_name)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="CDFD graph" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#4b5563" />',
        "</marker>",
        '<marker id="arrow-highlight" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#b45309" />',
        "</marker>",
        "</defs>",
    ]

    for edge in graph.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        sx, sy = positions[edge.source]
        tx, ty = positions[edge.target]
        x1, y1 = sx + 150, sy + 24
        x2, y2 = tx, ty + 24
        label = _edge_label(edge)
        color = "#b45309" if edge.id in highlighted_edges else "#4b5563"
        marker = "arrow-highlight" if edge.id in highlighted_edges else "arrow"
        stroke_width = "3" if edge.id in highlighted_edges else "2"
        if x2 <= x1:
            mid_y = min(y1, y2) - 34
            path_d = f"M{x1},{y1} C{x1 + 50},{mid_y} {x2 - 50},{mid_y} {x2},{y2}"
        else:
            mid_x = (x1 + x2) // 2
            path_d = f"M{x1},{y1} C{mid_x},{y1} {mid_x},{y2} {x2},{y2}"
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{stroke_width}" marker-end="url(#{marker})" />'
        )
        if label:
            lx, ly = (x1 + x2) // 2, (y1 + y2) // 2 - 8
            parts.append(
                f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="12" fill="#374151">{html.escape(label)}</text>'
            )

    for node_id, node in graph.nodes.items():
        x, y = positions[node_id]
        fill = _node_fill(graph, node_id, node.type)
        label = node.label or node.id
        parts.append(
            f'<rect x="{x}" y="{y}" width="150" height="48" rx="8" fill="{fill}" stroke="#2f6f73" stroke-width="1.5" />'
        )
        parts.append(
            f'<text x="{x + 75}" y="{y + 29}" text-anchor="middle" font-size="14" font-family="Arial, sans-serif" fill="#111827">{html.escape(label)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _export_text(paths: list[PathResult]) -> str:
    if not paths:
        return "No paths found."
    lines: list[str] = []
    for index, path in enumerate(paths, start=1):
        lines.append(f"Path {index}: {_path_route(path)}")
        if path.data:
            lines.append(f"  Data: {', '.join(path.data)}")
        if path.conditions:
            lines.append(f"  Conditions: {', '.join(path.conditions)}")
    return "\n".join(lines)


def _export_csv(paths: list[PathResult]) -> str:
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "nodes", "edges", "data", "conditions"])
    for index, path in enumerate(paths, start=1):
        writer.writerow(
            [
                f"P{index}",
                " -> ".join(path.nodes),
                " -> ".join(path.edges),
                " ; ".join(path.data),
                " ; ".join(path.conditions),
            ]
        )
    return stream.getvalue().strip()


def _export_markdown(paths: list[PathResult]) -> str:
    if not paths:
        return "No paths found."
    lines = ["| ID | Nodes | Data | Conditions |", "| --- | --- | --- | --- |"]
    for index, path in enumerate(paths, start=1):
        data = ", ".join(path.data) if path.data else "-"
        conditions = ", ".join(path.conditions) if path.conditions else "-"
        lines.append(f"| P{index} | {' -> '.join(path.nodes)} | {data} | {conditions} |")
    return "\n".join(lines)


def _assign_levels(graph: CDFDGraph) -> dict[str, int]:
    levels: dict[str, int] = {graph.start: 0}
    queue: deque[str] = deque([graph.start])

    while queue:
        node_id = queue.popleft()
        current_level = levels[node_id]
        for edge in graph.outgoing_edges(node_id):
            next_level = current_level + 1
            if edge.target not in levels or next_level < levels[edge.target]:
                levels[edge.target] = next_level
                queue.append(edge.target)

    next_level = max(levels.values(), default=0) + 1
    for node_id in graph.nodes:
        if node_id not in levels:
            levels[node_id] = next_level
            next_level += 1

    return levels


def _node_fill(graph: CDFDGraph, node_id: str, node_type: str) -> str:
    if node_id == graph.start:
        return "#d8f3dc"
    if node_id in graph.ends:
        return "#ffe8cc"
    if node_type == "decision":
        return "#e0e7ff"
    if node_type == "data":
        return "#fef9c3"
    if node_type == "external":
        return "#e5e7eb"
    if node_type == "state":
        return "#fce7f3"
    return "#f8fafc"


def _edge_label(edge) -> str:
    if edge.data:
        return ", ".join(edge.data)
    return edge.condition or edge.label or ""


def _path_route(path: PathResult) -> str:
    if len(path.data) == len(path.nodes) - 1:
        route = path.nodes[0]
        for index, data in enumerate(path.data, start=1):
            route += f" --[{data}]--> {path.nodes[index]}"
        return route
    return " -> ".join(path.nodes)


def _highlighted_edges(edge_ids: Iterable[str], graph_name: str | None) -> set[str]:
    highlighted: set[str] = set()
    prefix = f"{graph_name}:" if graph_name else None
    for edge_id in edge_ids:
        if prefix and edge_id.startswith(prefix):
            highlighted.add(edge_id[len(prefix) :])
        elif ":" not in edge_id:
            highlighted.add(edge_id)
    return highlighted
