from __future__ import annotations

import csv
import html
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from io import StringIO
from typing import Iterable

from cdfd.models import CDFDGraph, CDFDProject, FunctionalScenario, PathRelation, PathResult, model_dump

NODE_WIDTH = 150
NODE_HEIGHT = 48
X_GAP = 220
Y_GAP = 125
LEFT_PAD = 80
TOP_PAD = 120
CONTROL_GAP = 78
MIN_NODE_WIDTH = 110
MIN_NODE_HEIGHT = 34
EXTERNAL_NODE_WIDTH = 120
EXTERNAL_NODE_HEIGHT = 40
EDGE_LANE_GAP = 18


@dataclass(frozen=True)
class LayoutContext:
    positions: dict[str, tuple[int, int]]
    sizes: dict[str, tuple[int, int]]
    source_layout: bool = False
    shift: tuple[int, int] = (0, 0)


def export_paths(paths: list[PathResult], output_format: str) -> str:
    fmt = output_format.lower()
    if fmt == "text":
        return _export_text(paths)
    if fmt == "json":
        return json.dumps(paths_to_dicts(paths), indent=2)
    if fmt == "csv":
        return _export_csv(paths)
    if fmt == "markdown":
        return _export_markdown(paths)
    raise ValueError(f"Unsupported output format: {output_format}")


def export_analysis(
    paths: list[PathResult],
    path_relations: list[PathRelation],
    output_format: str,
    functional_scenarios: list[FunctionalScenario] | None = None,
) -> str:
    fmt = output_format.lower()
    if fmt == "json":
        payload = {
            "paths": paths_to_dicts(paths),
            "path_relations": [model_dump(relation) for relation in path_relations],
        }
        if functional_scenarios is not None:
            payload["functional_scenarios"] = scenarios_to_dicts(functional_scenarios)
        return json.dumps(payload, indent=2)
    if fmt == "text":
        text = _append_text_relations(_export_text(paths), path_relations)
        return _append_text_scenarios(text, functional_scenarios or [])
    if fmt == "markdown":
        markdown = _append_markdown_relations(_export_markdown(paths), path_relations)
        return _append_markdown_scenarios(markdown, functional_scenarios or [])
    if fmt == "csv":
        return _export_csv(paths)
    raise ValueError(f"Unsupported output format: {output_format}")


def paths_to_dicts(paths: list[PathResult]) -> list[dict[str, object]]:
    return [_path_to_dict(path, index) for index, path in enumerate(paths, start=1)]


def scenarios_to_dicts(scenarios: list[FunctionalScenario]) -> list[dict[str, object]]:
    return [model_dump(scenario) for scenario in scenarios]


def _path_to_dict(path: PathResult, index: int) -> dict[str, object]:
    raw = model_dump(path)
    return {
        **raw,
        "id": f"P{index}",
        "source": path.nodes[0] if path.nodes else None,
        "sink": path.nodes[-1] if path.nodes else None,
        "route": _path_route(path),
    }


def graph_to_dict(graph: CDFDGraph) -> dict[str, object]:
    return {
        "start": graph.start,
        "starts": sorted(graph.starts),
        "ends": sorted(graph.ends),
        "nodes": [model_dump(node) for node in graph.nodes.values()],
        "edges": [model_dump(edge) for edge in graph.edges],
        "structures": [model_dump(structure) for structure in graph.structures],
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
    layout = _layout_context(graph)
    positions = layout.positions
    sizes = layout.sizes

    width = (
        max(
            (x + sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))[0] for node_id, (x, _) in positions.items()),
            default=LEFT_PAD,
        )
        + LEFT_PAD
    )
    height = (
        max(
            (y + sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))[1] for node_id, (_, y) in positions.items()),
            default=TOP_PAD,
        )
        + TOP_PAD
    )
    highlighted_edges = _highlighted_edges(paths[0].edges if paths else [], graph_name)
    edge_offsets = _edge_offsets(graph)

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

    for edge_index, edge in enumerate(graph.edges, start=1):
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1, x2, y2 = _edge_endpoints(edge, layout, edge_offsets.get(edge.id, 0))
        label = _edge_label(edge)
        color = "#b45309" if edge.id in highlighted_edges else "#4b5563"
        marker = "arrow-highlight" if edge.id in highlighted_edges else "arrow"
        stroke_width = "3" if edge.id in highlighted_edges else "2"
        dash = ' stroke-dasharray="6 5"' if edge.kind == "control" else ""
        if layout.source_layout:
            path_d = _source_layout_path(edge, x1, y1, x2, y2, edge_index)
        elif edge.kind == "control":
            path_d = _control_edge_path(x1, y1, x2, y2, edge_index)
        else:
            path_d = _data_edge_path(x1, y1, x2, y2, edge_offsets.get(edge.id, 0))
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{stroke_width}"{dash} marker-end="url(#{marker})" />'
        )
        if label:
            lx, ly = _edge_label_position(path_d, x1, y1, x2, y2)
            escaped_label = html.escape(label)
            label_width = max(28, min(180, len(label) * 8 + 16))
            parts.append(
                f'<rect x="{lx - label_width / 2:.1f}" y="{ly - 15:.1f}" width="{label_width}" height="18" rx="3" fill="#ffffff" opacity="0.9" />'
            )
            parts.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="12" fill="#374151">{escaped_label}</text>')

    for node_id, node in graph.nodes.items():
        x, y = positions[node_id]
        width, height = sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))
        fill = _node_fill(graph, node_id, node.type)
        label = node.label or node.id
        font_size = 12 if height < 42 else 14
        text_y = y + height / 2 + font_size / 3
        radius = 5 if node.type == "data_store" else 8
        parts.append(
            f'<rect data-node-id="{html.escape(node_id)}" x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="#2f6f73" stroke-width="1.5" />'
        )
        parts.append(
            f'<text x="{x + width / 2}" y="{text_y}" text-anchor="middle" font-size="{font_size}" font-family="Arial, sans-serif" fill="#111827">{html.escape(label)}</text>'
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
        if path.preconditions:
            lines.append(f"  Preconditions: {'; '.join(path.preconditions)}")
        if path.conditions:
            lines.append(f"  Conditions: {', '.join(path.conditions)}")
    return "\n".join(lines)


def _export_csv(paths: list[PathResult]) -> str:
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "nodes", "edges", "data", "preconditions", "conditions"])
    for index, path in enumerate(paths, start=1):
        writer.writerow(
            [
                f"P{index}",
                " -> ".join(path.nodes),
                " -> ".join(path.edges),
                " ; ".join(path.data),
                " ; ".join(path.preconditions),
                " ; ".join(path.conditions),
            ]
        )
    return stream.getvalue().strip()


def _export_markdown(paths: list[PathResult]) -> str:
    if not paths:
        return "No paths found."
    lines = ["| ID | Nodes | Data | Preconditions | Conditions |", "| --- | --- | --- | --- | --- |"]
    for index, path in enumerate(paths, start=1):
        data = ", ".join(path.data) if path.data else "-"
        preconditions = "; ".join(path.preconditions) if path.preconditions else "-"
        conditions = ", ".join(path.conditions) if path.conditions else "-"
        lines.append(f"| P{index} | {' -> '.join(path.nodes)} | {data} | {preconditions} | {conditions} |")
    return "\n".join(lines)


def _append_text_relations(text: str, path_relations: list[PathRelation]) -> str:
    if not path_relations:
        return f"{text}\n\nPath Relations: none detected."

    lines = [text, "", "Path Relations:"]
    for relation in path_relations:
        connector = _relation_connector(relation.kind)
        lines.append(f"{relation.id} ({relation.kind}): {connector.join(relation.path_ids)}")
        if relation.title:
            lines.append(f"  {relation.title}")
        if relation.outputs:
            lines.append(f"  Outputs: {', '.join(relation.outputs)}")
        if relation.shared_prefix:
            lines.append(f"  Shared prefix: {' -> '.join(relation.shared_prefix)}")
    return "\n".join(lines)


def _append_markdown_relations(markdown: str, path_relations: list[PathRelation]) -> str:
    if not path_relations:
        return f"{markdown}\n\nNo path relations detected."

    lines = [
        markdown,
        "",
        "| Relation | Kind | Paths | Outputs | Shared Prefix |",
        "| --- | --- | --- | --- | --- |",
    ]
    for relation in path_relations:
        outputs = ", ".join(relation.outputs) if relation.outputs else "-"
        shared_prefix = " -> ".join(relation.shared_prefix) if relation.shared_prefix else "-"
        connector = _relation_connector(relation.kind)
        lines.append(
            f"| {relation.id} | {relation.kind} | {connector.join(relation.path_ids)} | {outputs} | {shared_prefix} |"
        )
    return "\n".join(lines)


def _append_text_scenarios(text: str, scenarios: list[FunctionalScenario]) -> str:
    if not scenarios:
        return text

    lines = [text, "", "Functional Scenarios:"]
    for scenario in scenarios:
        path_text = ", ".join(scenario.path_ids)
        input_text = ", ".join(scenario.input_data) if scenario.input_data else "-"
        output_text = ", ".join(scenario.output_data) if scenario.output_data else "-"
        lines.append(f"{scenario.id}: {path_text} | {input_text} => {output_text}")
        if scenario.description:
            lines.append(f"  {scenario.description}")
        if scenario.postconditions:
            lines.append(f"  Postconditions: {'; '.join(scenario.postconditions)}")
    return "\n".join(lines)


def _append_markdown_scenarios(markdown: str, scenarios: list[FunctionalScenario]) -> str:
    if not scenarios:
        return markdown

    lines = [
        markdown,
        "",
        "| Scenario | Paths | Input Data | Output Data | Operations |",
        "| --- | --- | --- | --- | --- |",
    ]
    for scenario in scenarios:
        inputs = ", ".join(scenario.input_data) if scenario.input_data else "-"
        outputs = ", ".join(scenario.output_data) if scenario.output_data else "-"
        operations = " -> ".join(operation.process for operation in scenario.operations) or "-"
        lines.append(
            f"| {scenario.id} | {', '.join(scenario.path_ids)} | {inputs} | {outputs} | {operations} |"
        )
    return "\n".join(lines)


def _relation_connector(kind: str) -> str:
    if kind == "parallel":
        return " || "
    if kind == "exclusive":
        return " XOR "
    return " + "


def _layout_context(graph: CDFDGraph) -> LayoutContext:
    source_layout = _source_layout_context(graph)
    if source_layout:
        return source_layout

    positions = _layout_positions(graph)
    sizes = {node_id: _default_node_size(graph.nodes[node_id].type) for node_id in graph.nodes}
    return LayoutContext(positions=positions, sizes=sizes)


def _source_layout_context(graph: CDFDGraph) -> LayoutContext | None:
    raw_positions: dict[str, tuple[int, int]] = {}
    sizes: dict[str, tuple[int, int]] = {}

    for node_id, node in graph.nodes.items():
        layout = _node_layout(node)
        if layout is None:
            continue
        x, y, width, height = layout
        raw_positions[node_id] = (x, y)
        sizes[node_id] = (width, height)

    if not raw_positions:
        return None

    positions = dict(raw_positions)
    _place_unpositioned_nodes(graph, positions, sizes)
    positions, shift = _normalize_source_layout(positions)
    for node_id, node in graph.nodes.items():
        sizes.setdefault(node_id, _default_node_size(node.type))

    return LayoutContext(positions=positions, sizes=sizes, source_layout=True, shift=shift)


def _layout_positions(graph: CDFDGraph) -> dict[str, tuple[int, int]]:
    levels = _assign_levels(graph)
    ordered_levels: dict[int, list[str]] = defaultdict(list)
    for node_id, level in levels.items():
        ordered_levels[level].append(node_id)

    _order_levels_by_neighbors(graph, ordered_levels)

    positions: dict[str, tuple[int, int]] = {}
    for level, node_ids in sorted(ordered_levels.items()):
        for row, node_id in enumerate(node_ids):
            positions[node_id] = (LEFT_PAD + level * X_GAP, TOP_PAD + row * Y_GAP)

    _place_control_nodes(graph, positions)
    _place_unpositioned_nodes(graph, positions)
    return _shift_into_view(positions)


def _assign_levels(graph: CDFDGraph) -> dict[str, int]:
    roots = sorted(graph.starts or {graph.start})
    levels: dict[str, int] = {root: 0 for root in roots}
    queue: deque[str] = deque(roots)

    while queue:
        node_id = queue.popleft()
        current_level = levels[node_id]
        for edge in graph.outgoing_edges(node_id):
            if edge.kind == "control":
                continue
            next_level = current_level + 1
            if edge.target not in levels or next_level < levels[edge.target]:
                levels[edge.target] = next_level
                queue.append(edge.target)

    next_level = max(levels.values(), default=0) + 1
    for node_id in graph.nodes:
        if node_id not in levels:
            if graph.nodes[node_id].type == "state":
                continue
            levels[node_id] = next_level
            next_level += 1

    return levels


def _order_levels_by_neighbors(graph: CDFDGraph, ordered_levels: dict[int, list[str]]) -> None:
    for level_nodes in ordered_levels.values():
        level_nodes.sort()

    previous_order: dict[str, int] = {}
    for level in sorted(ordered_levels):
        nodes = ordered_levels[level]
        if not previous_order:
            previous_order = {node_id: index for index, node_id in enumerate(nodes)}
            continue

        def score(node_id: str) -> tuple[float, str]:
            predecessors = [
                edge.source
                for edge in graph.incoming_edges(node_id)
                if edge.kind != "control" and edge.source in previous_order
            ]
            if not predecessors:
                return (float(len(previous_order) + len(nodes)), node_id)
            return (sum(previous_order[source] for source in predecessors) / len(predecessors), node_id)

        nodes.sort(key=score)
        previous_order = {node_id: index for index, node_id in enumerate(nodes)}


def _place_control_nodes(graph: CDFDGraph, positions: dict[str, tuple[int, int]]) -> None:
    by_target: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.kind != "control" or edge.target not in positions:
            continue
        by_target[edge.target].append(edge.source)

    for target_id, source_ids in by_target.items():
        tx, ty = positions[target_id]
        unique_sources = sorted(set(source_ids))
        for index, source_id in enumerate(unique_sources):
            if source_id in positions:
                continue
            offset = (index - (len(unique_sources) - 1) / 2) * (NODE_WIDTH + 24)
            positions[source_id] = (int(tx + offset), int(ty - CONTROL_GAP))


def _place_unpositioned_nodes(
    graph: CDFDGraph,
    positions: dict[str, tuple[int, int]],
    sizes: dict[str, tuple[int, int]] | None = None,
) -> None:
    if not graph.nodes:
        return
    sizes = sizes or {}
    next_x = (
        max(
            (x + sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))[0] for node_id, (x, _) in positions.items()),
            default=LEFT_PAD - X_GAP,
        )
        + X_GAP
    )
    next_y = TOP_PAD
    for node_id in graph.nodes:
        if node_id not in positions:
            positions[node_id] = (next_x, next_y)
            sizes.setdefault(node_id, _default_node_size(graph.nodes[node_id].type))
            next_y += Y_GAP


def _shift_into_view(positions: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    shifted, _ = _shift_into_view_with_delta(positions)
    return shifted


def _shift_into_view_with_delta(positions: dict[str, tuple[int, int]]) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    if not positions:
        return positions, (0, 0)
    min_x = min(x for x, _ in positions.values())
    min_y = min(y for _, y in positions.values())
    dx = max(0, LEFT_PAD - min_x)
    dy = max(0, TOP_PAD / 2 - min_y)
    if not dx and not dy:
        return positions, (0, 0)
    return {node_id: (int(x + dx), int(y + dy)) for node_id, (x, y) in positions.items()}, (int(dx), int(dy))


def _normalize_source_layout(positions: dict[str, tuple[int, int]]) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    if not positions:
        return positions, (0, 0)
    min_x = min(x for x, _ in positions.values())
    min_y = min(y for _, y in positions.values())
    dx = int(LEFT_PAD - min_x)
    dy = int(TOP_PAD / 2 - min_y)
    if not dx and not dy:
        return positions, (0, 0)
    return {node_id: (int(x + dx), int(y + dy)) for node_id, (x, y) in positions.items()}, (dx, dy)


def _node_layout(node) -> tuple[int, int, int, int] | None:
    raw_layout = node.metadata.get("layout")
    if not isinstance(raw_layout, dict):
        return None
    x = _optional_number(raw_layout.get("x"))
    y = _optional_number(raw_layout.get("y"))
    if x is None or y is None:
        return None
    default_width, default_height = _default_node_size(node.type)
    width = max(MIN_NODE_WIDTH, int(_optional_number(raw_layout.get("width")) or default_width))
    height = max(MIN_NODE_HEIGHT, int(_optional_number(raw_layout.get("height")) or default_height))
    return int(x), int(y), width, height


def _default_node_size(node_type: str) -> tuple[int, int]:
    if node_type == "external":
        return EXTERNAL_NODE_WIDTH, EXTERNAL_NODE_HEIGHT
    if node_type == "data_store":
        return 130, 34
    if node_type.endswith("_condition") or node_type in {"broadcasting", "separating", "merging", "connecting"}:
        return 132, 54
    return NODE_WIDTH, NODE_HEIGHT


def _edge_offsets(graph: CDFDGraph) -> dict[str, int]:
    by_pair: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for edge in graph.edges:
        by_pair[(edge.source, edge.target, edge.kind)].append(edge.id)

    offsets: dict[str, int] = {}
    for edge_ids in by_pair.values():
        if len(edge_ids) == 1:
            offsets[edge_ids[0]] = 0
            continue
        for index, edge_id in enumerate(edge_ids):
            offsets[edge_id] = int((index - (len(edge_ids) - 1) / 2) * EDGE_LANE_GAP)
    return offsets


def _edge_endpoints(edge, layout: LayoutContext, offset: int) -> tuple[int, int, int, int]:
    if layout.source_layout:
        raw = _raw_edge_points(edge)
        if raw:
            x1, y1, x2, y2 = raw
            dx, dy = layout.shift
            return int(x1 + dx), int(y1 + dy), int(x2 + dx), int(y2 + dy)

    sx, sy = layout.positions[edge.source]
    tx, ty = layout.positions[edge.target]
    sw, sh = layout.sizes.get(edge.source, (NODE_WIDTH, NODE_HEIGHT))
    tw, th = layout.sizes.get(edge.target, (NODE_WIDTH, NODE_HEIGHT))

    if edge.kind == "control":
        return (
            int(sx + sw / 2 + offset),
            int(sy + sh),
            int(tx + tw / 2 + offset),
            int(ty),
        )

    source_center = (sx + sw / 2, sy + sh / 2)
    target_center = (tx + tw / 2, ty + th / 2)
    dx = target_center[0] - source_center[0]
    dy = target_center[1] - source_center[1]

    if abs(dx) >= abs(dy):
        if dx >= 0:
            return int(sx + sw), int(sy + sh / 2 + offset), int(tx), int(ty + th / 2 + offset)
        return int(sx), int(sy + sh / 2 + offset), int(tx + tw), int(ty + th / 2 + offset)

    if dy >= 0:
        return int(sx + sw / 2 + offset), int(sy + sh), int(tx + tw / 2 + offset), int(ty)
    return int(sx + sw / 2 + offset), int(sy), int(tx + tw / 2 + offset), int(ty + th)


def _raw_edge_points(edge) -> tuple[int, int, int, int] | None:
    raw_layout = edge.metadata.get("layout")
    if not isinstance(raw_layout, dict):
        return None
    from_x = _optional_number(raw_layout.get("fromX"))
    from_y = _optional_number(raw_layout.get("fromY"))
    to_x = _optional_number(raw_layout.get("toX"))
    to_y = _optional_number(raw_layout.get("toY"))
    if None in (from_x, from_y, to_x, to_y):
        return None
    return int(from_x), int(from_y), int(to_x), int(to_y)


def _source_layout_path(edge, x1: int, y1: int, x2: int, y2: int, edge_index: int) -> str:
    if edge.kind == "control":
        return _control_edge_path(x1, y1, x2, y2, edge_index)
    return f"M{x1},{y1} L{x2},{y2}"


def _control_edge_path(x1: int, y1: int, x2: int, y2: int, edge_index: int) -> str:
    lane = min(y1, y2) - CONTROL_GAP - (edge_index % 3) * 12
    if lane > min(y1, y2) - 24:
        lane = min(y1, y2) - 24
    return f"M{x1},{y1} L{x1},{lane} L{x2},{lane} L{x2},{y2}"


def _data_edge_path(x1: int, y1: int, x2: int, y2: int, offset: int) -> str:
    if abs(y1 - y2) <= 8:
        return f"M{x1},{y1} L{x2},{y2}"
    if abs(x2 - x1) >= 64:
        mid_x = int((x1 + x2) / 2 + offset)
        return f"M{x1},{y1} L{mid_x},{y1} L{mid_x},{y2} L{x2},{y2}"
    lane_y = min(y1, y2) - 36 - abs(offset)
    return f"M{x1},{y1} L{x1},{lane_y} L{x2},{lane_y} L{x2},{y2}"


def _edge_label_position(path_d: str, x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
    points = [(int(x), int(y)) for x, y in re.findall(r"(-?\d+),(-?\d+)", path_d)]
    if len(points) >= 4:
        return points[len(points) // 2]
    return int((x1 + x2) / 2), int((y1 + y2) / 2 - 8)


def _optional_number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _node_fill(graph: CDFDGraph, node_id: str, node_type: str) -> str:
    if node_id in (graph.starts or {graph.start}):
        return "#d8f3dc"
    if node_id in graph.ends:
        return "#ffe8cc"
    if node_type in {"decision", "single_condition", "multiple_condition", "binary_condition", "nondeterministic"}:
        return "#e0e7ff"
    if node_type in {"data", "data_store"}:
        return "#fef9c3"
    if node_type in {"broadcasting", "separating", "merging", "connecting", "renaming"}:
        return "#dcfce7"
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
