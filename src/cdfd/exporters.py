from __future__ import annotations

import csv
import html
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from io import StringIO

from cdfd.models import CDFDGraph, CDFDProject, ConcurrentPathResult, FunctionalScenario, PathRelation, PathResult, model_dump

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
    concurrent_paths: list[ConcurrentPathResult] | None = None,
) -> str:
    fmt = output_format.lower()
    if fmt == "json":
        payload = {
            "paths": paths_to_dicts(paths),
            "path_relations": [model_dump(relation) for relation in path_relations],
        }
        if concurrent_paths is not None:
            payload["concurrent_paths"] = concurrent_paths_to_dicts(concurrent_paths)
        if functional_scenarios is not None:
            payload["functional_scenarios"] = scenarios_to_dicts(functional_scenarios)
        return json.dumps(payload, indent=2)
    if fmt == "text":
        text = _append_text_concurrent_paths(_export_text(paths), concurrent_paths or [])
        text = _append_text_relations(text, path_relations)
        return _append_text_scenarios(text, functional_scenarios or [])
    if fmt == "markdown":
        markdown = _append_markdown_concurrent_paths(_export_markdown(paths), concurrent_paths or [])
        markdown = _append_markdown_relations(markdown, path_relations)
        return _append_markdown_scenarios(markdown, functional_scenarios or [])
    if fmt == "csv":
        return _export_csv(paths)
    raise ValueError(f"Unsupported output format: {output_format}")


def paths_to_dicts(paths: list[PathResult]) -> list[dict[str, object]]:
    return [_path_to_dict(path, index) for index, path in enumerate(paths, start=1)]


def concurrent_paths_to_dicts(
    concurrent_paths: list[ConcurrentPathResult],
    *,
    tree_lines: list[list[str]] | None = None,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for index, concurrent in enumerate(concurrent_paths, start=1):
        lines = tree_lines[index - 1] if tree_lines and index - 1 < len(tree_lines) else []
        raw = model_dump(concurrent)
        items.append(
            {
                **raw,
                "id": f"CP{index}",
                "source": concurrent.nodes[0] if concurrent.nodes else None,
                "sink": concurrent.nodes[-1] if concurrent.nodes else None,
                "tree_lines": lines,
            }
        )
    return items


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
    edge_offsets = _edge_offsets(graph)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="CDFD graph" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        '<pattern id="sofl-grid" width="10" height="10" patternUnits="userSpaceOnUse">',
        '<circle cx="1" cy="1" r="0.65" fill="#c7cdd3" />',
        "</pattern>",
        '<marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">',
        '<path d="M0,0 L0,6 L8,3 z" fill="#111827" />',
        "</marker>",
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="#ffffff" />',
        f'<rect width="{width}" height="{height}" fill="url(#sofl-grid)" />',
    ]

    for node_id, node in graph.nodes.items():
        if _should_skip_rendered_node(layout, node):
            continue
        if not _draw_node_before_edges(node):
            continue
        x, y = positions[node_id]
        width, height = sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))
        parts.extend(_render_sofl_node(graph, node_id, node, x, y, width, height))

    for edge_index, edge in enumerate(graph.edges, start=1):
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1, x2, y2 = _edge_endpoints(edge, layout, edge_offsets.get(edge.id, 0))
        label = _edge_label(graph, edge)
        edge_class = "control-flow" if edge.kind == "control" else "data-flow"
        dash = ' stroke-dasharray="1 5" stroke-linecap="round"' if edge.kind == "control" else ""
        if layout.source_layout:
            path_d = _source_layout_path(x1, y1, x2, y2)
        elif edge.kind == "control":
            path_d = _control_edge_path(x1, y1, x2, y2, edge_index)
        else:
            path_d = _data_edge_path(x1, y1, x2, y2, edge_offsets.get(edge.id, 0))
        parts.append(
            f'<path class="{edge_class}" data-edge-id="{html.escape(edge.id)}" d="{path_d}" '
            f'fill="none" stroke="#111827" stroke-width="1.35"{dash} marker-end="url(#arrow)" />'
        )
        if label:
            lx, ly = _edge_label_position(path_d, x1, y1, x2, y2)
            escaped_label = html.escape(label)
            parts.append(
                f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="12" '
                'font-family="Arial, sans-serif" fill="#111827" '
                'style="paint-order:stroke;stroke:#ffffff;stroke-width:4px;stroke-linejoin:round">'
                f"{escaped_label}</text>"
            )

    for node_id, node in graph.nodes.items():
        if _should_skip_rendered_node(layout, node):
            continue
        if _draw_node_before_edges(node):
            continue
        x, y = positions[node_id]
        width, height = sizes.get(node_id, (NODE_WIDTH, NODE_HEIGHT))
        parts.extend(_render_sofl_node(graph, node_id, node, x, y, width, height))

    parts.append("</svg>")
    return "".join(parts)


def _render_sofl_node(graph: CDFDGraph, node_id: str, node, x: int, y: int, width: int, height: int) -> list[str]:
    node_type = node.type.lower()
    escaped_id = html.escape(node_id)
    label = html.escape(node.label or node.id)
    common = f'data-node-id="{escaped_id}"'
    type_attr = f'data-node-type="{html.escape(node_type)}"'
    stroke = "#111827"
    fill = "#ffffff"
    text = _svg_text(x + width / 2, y + height / 2, label, width, height)

    if node_type == "process":
        inset = max(7, min(10, int(min(width, height) * 0.16)))
        top = y + inset
        bottom = y + height - inset
        left = x + inset
        right = x + width - inset
        parts = [
            f'<g class="sofl-node sofl-process" data-node-shape="process">',
            f'<rect class="sofl-process-boundary" {common} x="{x}" y="{y}" width="{width}" height="{height}" {type_attr} '
            f'fill="{fill}" stroke="{stroke}" />',
            f'<line class="sofl-process-band" x1="{x}" y1="{top}" x2="{x + width}" y2="{top}" stroke="{stroke}" />',
            f'<line class="sofl-process-band" x1="{x}" y1="{bottom}" x2="{x + width}" y2="{bottom}" stroke="{stroke}" />',
            f'<line class="sofl-process-port-rail" x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="{stroke}" />',
            f'<line class="sofl-process-port-rail" x1="{right}" y1="{top}" x2="{right}" y2="{bottom}" stroke="{stroke}" />',
        ]
        parts.extend(
            _process_port_dividers(
                x,
                left,
                top,
                bottom,
                _sofl_process_port_count(node, "inputPorts"),
                "input",
                stroke,
            )
        )
        parts.extend(
            _process_port_dividers(
                right,
                x + width,
                top,
                bottom,
                _sofl_process_port_count(node, "outputPorts"),
                "output",
                stroke,
            )
        )
        parts.extend([text, "</g>"])
        return parts

    if node_type in {"data", "data_store"}:
        divider = max(18, min(30, int(width * 0.2)))
        number = _sofl_data_store_number(node)
        label_x = x + divider + (width - divider) / 2
        return [
            f'<g class="sofl-node sofl-data-store" data-node-shape="data-store">',
            f'<rect {common} x="{x}" y="{y}" width="{width}" height="{height}" {type_attr} '
            f'fill="{fill}" stroke="{stroke}" />',
            f'<line x1="{x + divider}" y1="{y}" x2="{x + divider}" y2="{y + height}" stroke="{stroke}" />',
            _svg_text(x + divider / 2, y + height / 2, html.escape(number), divider, height, preferred_size=11),
            _svg_text(label_x, y + height / 2, label, width - divider, height, preferred_size=12),
            "</g>",
        ]

    if node_type in {"decision", "single_condition", "multiple_condition", "binary_condition"}:
        points = f"{x + width / 2},{y} {x + width},{y + height / 2} {x + width / 2},{y + height} {x},{y + height / 2}"
        parts = [
            f'<g class="sofl-node sofl-condition" data-node-shape="condition">',
            f'<polygon {common} {type_attr} points="{points}" fill="{fill}" stroke="{stroke}" />',
            text,
        ]
        if node_type == "binary_condition":
            parts.append(f'<circle cx="{x + width / 2}" cy="{y + height}" r="4.5" fill="{stroke}" />')
        parts.append("</g>")
        return parts

    if node_type == "broadcasting":
        return [
            f'<g class="sofl-node sofl-broadcasting" data-node-shape="broadcasting">',
            f'<ellipse {common} {type_attr} cx="{x + width / 2}" cy="{y + height / 2}" rx="{width / 2}" ry="{height / 2}" '
            f'fill="{fill}" stroke="{stroke}" />',
            f'<circle cx="{x + width / 2}" cy="{y + height / 2}" r="4.5" fill="{stroke}" />',
            "</g>",
        ]

    if node_type in {"separating", "merging"}:
        neck = int(width * 0.68)
        flare = int(height * 0.2)
        if node_type == "separating":
            points = (
                f"{x},{y + flare} {x + neck},{y + flare} {x + width},{y} "
                f"{x + width},{y + height} {x + neck},{y + height - flare} {x},{y + height - flare}"
            )
        else:
            points = (
                f"{x},{y} {x + width - neck},{y + flare} {x + width},{y + flare} "
                f"{x + width},{y + height - flare} {x + width - neck},{y + height - flare} {x},{y + height}"
            )
        return [
            f'<g class="sofl-node sofl-{node_type}" data-node-shape="{node_type}">',
            f'<polygon {common} {type_attr} points="{points}" fill="{fill}" stroke="{stroke}" />',
            "</g>",
        ]

    if node_type == "connecting":
        return [
            f'<g class="sofl-node sofl-connecting" data-node-shape="connecting">',
            f'<ellipse {common} {type_attr} cx="{x + width / 2}" cy="{y + height / 2}" rx="{width / 2}" ry="{height / 2}" '
            f'fill="{fill}" stroke="{stroke}" />',
            text,
            "</g>",
        ]

    if node_type == "nondeterministic":
        return [
            f'<g class="sofl-node sofl-nondeterministic" data-node-shape="nondeterministic">',
            f'<ellipse {common} {type_attr} cx="{x + width / 2}" cy="{y + height / 2}" rx="{width / 2}" ry="{height / 2}" '
            f'fill="{fill}" stroke="{stroke}" />',
            f'<line x1="{x}" y1="{y + height / 2}" x2="{x + width}" y2="{y + height / 2}" stroke="{stroke}" />',
            f'<line x1="{x + width / 2}" y1="{y}" x2="{x + width / 2}" y2="{y + height}" stroke="{stroke}" />',
            "</g>",
        ]

    if node_type == "renaming":
        row_height = height / 3
        return [
            f'<g class="sofl-node sofl-renaming" data-node-shape="renaming">',
            f'<rect {common} x="{x}" y="{y}" width="{width}" height="{height}" {type_attr} '
            f'fill="{fill}" stroke="{stroke}" />',
            f'<line x1="{x}" y1="{y + row_height:.1f}" x2="{x + width}" y2="{y + row_height:.1f}" stroke="{stroke}" />',
            f'<line x1="{x}" y1="{y + row_height * 2:.1f}" x2="{x + width}" y2="{y + row_height * 2:.1f}" stroke="{stroke}" />',
            "</g>",
        ]

    if node_type == "state":
        left_text, right_text = _split_state_label(node.label or node.id)
        divider = max(22, min(38, int(width * 0.28)))
        return [
            f'<g class="sofl-node sofl-state" data-node-shape="state">',
            f'<rect {common} x="{x}" y="{y}" width="{width}" height="{height}" {type_attr} '
            f'fill="#fff7fb" stroke="{stroke}" />',
            f'<line x1="{x + divider}" y1="{y}" x2="{x + divider}" y2="{y + height}" stroke="{stroke}" />',
            _svg_text(x + divider / 2, y + height / 2, html.escape(left_text), divider, height, preferred_size=11),
            _svg_text(
                x + divider + (width - divider) / 2,
                y + height / 2,
                html.escape(right_text),
                width - divider,
                height,
                preferred_size=12,
            ),
            "</g>",
        ]

    fill = _node_fill(graph, node_id, node_type)
    return [
        f'<g class="sofl-node sofl-generic" data-node-shape="generic">',
        f'<rect {common} x="{x}" y="{y}" width="{width}" height="{height}" {type_attr} '
        f'fill="{fill}" stroke="{stroke}" />',
        text,
        "</g>",
    ]


def _svg_text(
    center_x: float,
    center_y: float,
    escaped_label: str,
    width: float,
    height: float,
    *,
    preferred_size: int = 13,
) -> str:
    available_chars = max(1, int((width - 12) / max(preferred_size * 0.58, 1)))
    font_size = preferred_size
    if len(html.unescape(escaped_label)) > available_chars:
        font_size = max(9, int(preferred_size * available_chars / len(html.unescape(escaped_label))))
    text_y = center_y + font_size * 0.34
    return (
        f'<text x="{center_x:.1f}" y="{text_y:.1f}" text-anchor="middle" font-size="{font_size}" '
        f'font-family="Arial, sans-serif" fill="#111827">{escaped_label}</text>'
    )


def _process_port_dividers(
    x1: int,
    x2: int,
    top: int,
    bottom: int,
    port_count: int,
    role: str,
    stroke: str,
) -> list[str]:
    if port_count <= 1 or bottom <= top:
        return []
    height = bottom - top
    return [
        f'<line class="sofl-process-{role}-port-divider" x1="{x1}" y1="{top + height * index / port_count:.1f}" '
        f'x2="{x2}" y2="{top + height * index / port_count:.1f}" stroke="{stroke}" />'
        for index in range(1, port_count)
    ]


def _sofl_process_port_count(node, attribute_name: str) -> int:
    attributes = node.metadata.get("attributes", {})
    value = attributes.get(attribute_name) if isinstance(attributes, dict) else None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _sofl_data_store_number(node) -> str:
    attributes = node.metadata.get("attributes", {})
    if isinstance(attributes, dict):
        number = attributes.get("no")
        if number is not None:
            return str(number)
    return ""


def _split_state_label(label: str) -> tuple[str, str]:
    parts = label.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].replace(".", "", 1).isdigit():
        return parts[0], parts[1]
    return "", label


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


def _append_text_concurrent_paths(text: str, concurrent_paths: list[ConcurrentPathResult]) -> str:
    if not concurrent_paths:
        return f"{text}\n\nConcurrent Paths: none detected."

    lines = [text, "", "Concurrent Paths:"]
    for index, concurrent in enumerate(concurrent_paths, start=1):
        notation = concurrent.notation or ""
        lines.append(f"CP{index}: {notation}")
        if concurrent.preconditions:
            lines.append(f"  Preconditions: {'; '.join(concurrent.preconditions)}")
        if concurrent.conditions:
            lines.append(f"  Conditions: {', '.join(concurrent.conditions)}")
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


def _append_markdown_concurrent_paths(
    markdown: str,
    concurrent_paths: list[ConcurrentPathResult],
) -> str:
    if not concurrent_paths:
        return f"{markdown}\n\nNo concurrent paths detected."

    lines = [
        markdown,
        "",
        "| Concurrent Path | Notation | Conditions |",
        "| --- | --- | --- |",
    ]
    for index, concurrent in enumerate(concurrent_paths, start=1):
        conditions = ", ".join(concurrent.conditions) if concurrent.conditions else "-"
        lines.append(f"| CP{index} | {concurrent.notation or '-'} | {conditions} |")
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
    raw_width = _optional_number(raw_layout.get("width"))
    raw_height = _optional_number(raw_layout.get("height"))
    width = int(raw_width) if raw_width and raw_width > 0 else default_width
    height = int(raw_height) if raw_height and raw_height > 0 else default_height
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


def _source_layout_path(x1: int, y1: int, x2: int, y2: int) -> str:
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


def _edge_label(graph: CDFDGraph, edge) -> str:
    if edge.data:
        return ", ".join(edge.data)
    if edge.condition and edge.kind == "control":
        return edge.condition
    if edge.condition and not _edge_starts_at_sofl_condition(graph, edge):
        return edge.condition
    return edge.label or ""


def _edge_starts_at_sofl_condition(graph: CDFDGraph, edge) -> bool:
    source = graph.nodes.get(edge.source)
    if source is None:
        return False
    return (
        source.type.lower().endswith("_condition")
        and edge.metadata.get("source_format") == "sofl-cdfd"
    )


def _is_inferred_sofl_external(node) -> bool:
    return (
        node.type == "external"
        and node.metadata.get("source_format") == "sofl-cdfd"
        and node.metadata.get("inferred_from") == "outside-endpoint"
    )


def _should_skip_rendered_node(layout: LayoutContext, node) -> bool:
    return layout.source_layout and _is_inferred_sofl_external(node)


def _draw_node_before_edges(node) -> bool:
    return node.type.lower() in {"separating", "merging", "connecting", "broadcasting"}


def _path_route(path: PathResult) -> str:
    if (
        path.edge_sources
        and path.edge_targets
        and path.edge_data
        and len(path.edge_sources) == len(path.edge_targets) == len(path.edge_data)
    ):
        return _path_route_from_segments(path)
    if len(path.data) == len(path.nodes) - 1:
        route = path.nodes[0]
        for index, data in enumerate(path.data, start=1):
            route += f" --[{data}]--> {path.nodes[index]}"
        return route
    return " -> ".join(path.nodes)


def _path_route_from_segments(path: PathResult) -> str:
    if not any(path.edge_data):
        return " -> ".join(path.nodes)

    route = path.edge_sources[0]
    current = path.edge_sources[0]
    join_targets = {
        target
        for target in path.edge_targets
        if path.edge_targets.count(target) > 1
    }
    for source, target, data_items in zip(path.edge_sources, path.edge_targets, path.edge_data):
        if source != current or (source in join_targets and route != source):
            route += f" | {source}"
        data_label = ", ".join(data_items)
        if data_label:
            route += f" --[{data_label}]--> {target}"
        else:
            route += f" -> {target}"
        current = target
    return route
