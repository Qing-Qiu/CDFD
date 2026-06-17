from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

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
from cdfd.parsers.errors import ParseError


NODE_TYPE_BY_TAG = {
    "process": "process",
    "datastore": "data_store",
    "singlecondition": "single_condition",
    "multiplecondition": "multiple_condition",
    "binarycondition": "binary_condition",
    "broadcasting": "broadcasting",
    "broadcasing": "broadcasting",
    "boradcasting": "broadcasting",
    "separating": "separating",
    "merging": "merging",
    "connecting": "connecting",
    "nondeterministic": "nondeterministic",
    "renaming": "renaming",
}

STRUCTURE_KIND_BY_NODE_TYPE = {
    "single_condition": "condition",
    "multiple_condition": "condition",
    "binary_condition": "condition",
    "nondeterministic": "nondeterminism",
    "broadcasting": "broadcast",
    "separating": "separate",
}

MERGE_NODE_TYPES = {"merging", "connecting"}
COORDINATE_TOLERANCE = 36.0
EXTERNAL_WIDTH = 120
EXTERNAL_HEIGHT = 40


@dataclass(frozen=True)
class Component:
    id: str
    tag: str
    node_type: str
    label: str | None
    shape_index: str | None
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    condition: str | None
    attrs: dict[str, str]


def parse_sofl_cdfd_graph(
    content: str,
    *,
    start: str | None = None,
    ends: str | list[str] | None = None,
) -> CDFDGraph:
    return parse_sofl_cdfd_project(content, start=start, ends=ends).entry()


def parse_sofl_cdfd_project(
    content: str,
    *,
    start: str | None = None,
    ends: str | list[str] | None = None,
) -> CDFDProject:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ParseError(f"Invalid SOFL CDFD XML: {exc}") from exc

    if _local_name(root.tag).lower() != "cdfd":
        raise ParseError("SOFL CDFD XML must have a <CDFD> root element.")

    module_name = _optional_str(root.attrib.get("module"))
    components = _parse_components(root)
    nodes = {component.id: _node_from_component(component) for component in components}
    processes = _process_specs_from_components(components)
    edges = _parse_connections(root, components, nodes)
    structures = _structures_from_components(components, edges)
    starts = set(_coerce_id_list(start))
    end_set = set(_coerce_id_list(ends))

    graph = _build_graph(
        nodes=nodes,
        edges=edges,
        start=next(iter(starts), None),
        starts=starts,
        ends=end_set,
        structures=structures,
        metadata={
            "source_format": "sofl-cdfd",
            "module": module_name,
            "layout": {
                component.id: {
                    "x": component.x,
                    "y": component.y,
                    "width": component.width,
                    "height": component.height,
                }
                for component in components
            },
        },
    )

    graph_name = module_name or "main"
    return CDFDProject(
        graphs={graph_name: graph},
        entry_graph=graph_name,
        module=ModuleInfo(name=module_name, behav=graph_name, metadata={"source_format": "sofl-cdfd"}),
        processes=processes,
        metadata={"source_format": "sofl-cdfd"},
    )


def _parse_components(root: ET.Element) -> list[Component]:
    component_list = root.find("./componentList")
    if component_list is None:
        raise ParseError("SOFL CDFD XML must contain a <componentList> element.")

    components: list[Component] = []
    used_ids: set[str] = set()
    for index, element in enumerate(list(component_list), start=1):
        tag = _local_name(element.tag)
        normalized_tag = tag.lower()
        node_type = NODE_TYPE_BY_TAG.get(normalized_tag, _camel_to_snake(tag))
        label = _optional_str(element.attrib.get("name")) or _optional_str(element.attrib.get("condition"))
        shape_index = _optional_str(element.attrib.get("shapeIndex"))
        base_id = label if node_type in {"process", "data_store"} and label else f"{node_type}_{shape_index or index}"
        component_id = _unique_id(base_id, used_ids)
        used_ids.add(component_id)
        attrs = {key: str(value) for key, value in element.attrib.items()}
        components.append(
            Component(
                id=component_id,
                tag=tag,
                node_type=node_type,
                label=label,
                shape_index=shape_index,
                x=_optional_float(element.attrib.get("x")),
                y=_optional_float(element.attrib.get("y")),
                width=_optional_float(element.attrib.get("width")),
                height=_optional_float(element.attrib.get("height")),
                condition=_optional_str(element.attrib.get("condition")),
                attrs=attrs,
            )
        )

    if not components:
        raise ParseError("SOFL CDFD XML must contain at least one component.")
    return components


def _node_from_component(component: Component) -> Node:
    metadata = {
        "source_format": "sofl-cdfd",
        "sofl_type": component.tag,
        "shape_index": component.shape_index,
        "attributes": component.attrs,
        "layout": {
            "x": component.x,
            "y": component.y,
            "width": component.width,
            "height": component.height,
        },
    }
    if component.condition:
        metadata["condition"] = component.condition
    return Node(id=component.id, type=component.node_type, label=component.label, metadata=metadata)


def _process_specs_from_components(components: list[Component]) -> dict[str, ProcessSpec]:
    processes: dict[str, ProcessSpec] = {}
    for component in components:
        if component.node_type != "process":
            continue
        input_count = _optional_int(component.attrs.get("inputPorts"))
        output_count = _optional_int(component.attrs.get("outputPorts"))
        processes[component.id] = ProcessSpec(
            id=component.id,
            label=component.label,
            metadata={
                "source_format": "sofl-cdfd",
                "input_port_count": input_count,
                "output_port_count": output_count,
                "sofl_type": component.tag,
            },
        )
    return processes


def _parse_connections(root: ET.Element, components: list[Component], nodes: dict[str, Node]) -> list[Edge]:
    connection_list = root.find("./connectionList")
    if connection_list is None:
        raise ParseError("SOFL CDFD XML must contain a <connectionList> element.")

    by_shape = {component.shape_index: component for component in components if component.shape_index is not None}
    by_name = {component.label: component for component in components if component.label}
    edges: list[Edge] = []
    used_edge_ids: set[str] = set()

    for index, element in enumerate(list(connection_list), start=1):
        tag = _local_name(element.tag)
        kind = _edge_kind(tag)
        target = _resolve_endpoint(element, "to", components, by_shape, by_name, nodes, index)
        source = _resolve_endpoint(
            element,
            "from",
            components,
            by_shape,
            by_name,
            nodes,
            index,
            target_node=nodes.get(target),
        )
        label = _optional_str(element.attrib.get("name")) or _optional_str(element.attrib.get("type"))
        edge_id = _unique_id(f"{_camel_to_snake(tag)}_{index}", used_edge_ids)
        used_edge_ids.add(edge_id)
        source_condition = nodes.get(source)
        condition = None
        if source_condition and source_condition.type.endswith("_condition"):
            condition = _optional_str(source_condition.metadata.get("condition"))

        to_endpoint = element.find("./to")
        to_meta = _endpoint_metadata(to_endpoint)
        target_component = by_name.get(nodes[target].label) if nodes[target].label in by_name else None
        if target_component is None:
            target_component = next(
                (component for component in components if component.id == target),
                None,
            )
        input_port = _resolve_input_port(
            to_meta,
            _optional_float(element.attrib.get("toY")),
            target_component,
        )

        edges.append(
            Edge(
                id=edge_id,
                source=source,
                target=target,
                kind=kind,
                data=[label] if label and kind != "control" else [],
                condition=condition,
                label=label,
                metadata={
                    "source_format": "sofl-cdfd",
                    "sofl_type": tag,
                    "input_port": input_port,
                    "attributes": {key: str(value) for key, value in element.attrib.items()},
                    "from": _endpoint_metadata(element.find("./from")),
                    "to": to_meta,
                    "layout": {
                        "fromX": _optional_float(element.attrib.get("fromX")),
                        "fromY": _optional_float(element.attrib.get("fromY")),
                        "toX": _optional_float(element.attrib.get("toX")),
                        "toY": _optional_float(element.attrib.get("toY")),
                    },
                },
            )
        )

    if not edges:
        raise ParseError("SOFL CDFD XML must contain at least one connection.")
    return edges


def _resolve_endpoint(
    connection: ET.Element,
    role: str,
    components: list[Component],
    by_shape: dict[str | None, Component],
    by_name: dict[str | None, Component],
    nodes: dict[str, Node],
    connection_index: int,
    target_node: Node | None = None,
) -> str:
    endpoint = connection.find(f"./{role}")
    belong_to_type = _optional_str(endpoint.attrib.get("belongToType")) if endpoint is not None else None

    if endpoint is not None:
        name = _optional_str(endpoint.attrib.get("belongToName"))
        if name and name in by_name:
            return by_name[name].id

        belong_type = _optional_str(endpoint.attrib.get("belongToType"))
        if belong_type and belong_type.lower() not in {"outside", "processtopbottom", "processtop", "processbottom"}:
            type_match = _component_by_sofl_type(components, belong_type)
            if type_match is not None:
                return type_match.id

        shape_index = _optional_str(endpoint.attrib.get("shapeIndex"))
        x = _optional_float(connection.attrib.get(f"{role}X"))
        y = _optional_float(connection.attrib.get(f"{role}Y"))
        if shape_index and shape_index != "-1" and shape_index in by_shape:
            component = by_shape[shape_index]
            if x is None or y is None or _point_near_component(component, x, y):
                return component.id

    if _is_outside_endpoint(belong_to_type) and role == "from":
        x = _optional_float(connection.attrib.get("fromX"))
        y = _optional_float(connection.attrib.get("fromY"))
        inferred = _component_at_point(components, x, y)
        if inferred is not None and inferred.node_type == "process" and _point_on_process_output_side(
            inferred, x, y
        ):
            if target_node is not None and target_node.type == "process":
                return _create_external_endpoint(connection, role, nodes, connection_index)
            return inferred.id
        if inferred is not None:
            return inferred.id
        return _create_external_endpoint(connection, role, nodes, connection_index)

    x = _optional_float(connection.attrib.get(f"{role}X"))
    y = _optional_float(connection.attrib.get(f"{role}Y"))
    inferred = _component_at_point(components, x, y)
    if inferred is not None:
        return inferred.id

    if _is_outside_endpoint(belong_to_type):
        return _create_external_endpoint(connection, role, nodes, connection_index)

    return _create_external_endpoint(connection, role, nodes, connection_index)


def _create_external_endpoint(
    connection: ET.Element,
    role: str,
    nodes: dict[str, Node],
    connection_index: int,
) -> str:
    x = _optional_float(connection.attrib.get(f"{role}X"))
    y = _optional_float(connection.attrib.get(f"{role}Y"))
    label = _optional_str(connection.attrib.get("name"))
    prefix = "IN" if role == "from" else "OUT"
    external_id = _unique_id(f"{prefix}_{label or connection_index}", set(nodes))
    layout = _external_endpoint_layout(x, y, role)
    nodes[external_id] = Node(
        id=external_id,
        type="external",
        label=label or ("External input" if role == "from" else "External output"),
        metadata={
            "source_format": "sofl-cdfd",
            "inferred_from": "outside-endpoint",
            "connection_index": connection_index,
            "role": role,
            "layout": layout,
        },
    )
    return external_id


def _component_at_point(components: list[Component], x: float | None, y: float | None) -> Component | None:
    if x is None or y is None:
        return None

    candidates: list[tuple[float, Component]] = []
    for component in components:
        if None in (component.x, component.y, component.width, component.height):
            continue
        left = component.x
        top = component.y
        right = component.x + component.width
        bottom = component.y + component.height
        assert left is not None and top is not None and right is not None and bottom is not None

        if not (left - COORDINATE_TOLERANCE <= x <= right + COORDINATE_TOLERANCE):
            continue
        if not (top - COORDINATE_TOLERANCE <= y <= bottom + COORDINATE_TOLERANCE):
            continue

        outside_dx = max(left - x, 0, x - right)
        outside_dy = max(top - y, 0, y - bottom)
        if outside_dx or outside_dy:
            distance = math.hypot(outside_dx, outside_dy)
        else:
            distance = min(abs(x - left), abs(x - right), abs(y - top), abs(y - bottom))
        candidates.append((distance, component))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1].id))
    if candidates[0][0] <= COORDINATE_TOLERANCE:
        return candidates[0][1]
    return None


def _point_on_process_output_side(component: Component, x: float, y: float) -> bool:
    if None in (component.x, component.y, component.width, component.height):
        return False
    assert component.x is not None and component.y is not None
    assert component.width is not None and component.height is not None
    right = component.x + component.width
    vertical_on_box = component.y - COORDINATE_TOLERANCE <= y <= component.y + component.height + COORDINATE_TOLERANCE
    return vertical_on_box and x >= right - COORDINATE_TOLERANCE


def _point_near_component(component: Component, x: float, y: float) -> bool:
    if None in (component.x, component.y, component.width, component.height):
        return False
    left = component.x - COORDINATE_TOLERANCE
    top = component.y - COORDINATE_TOLERANCE
    right = component.x + component.width + COORDINATE_TOLERANCE
    bottom = component.y + component.height + COORDINATE_TOLERANCE
    assert component.x is not None and component.y is not None
    assert component.width is not None and component.height is not None
    return left <= x <= right and top <= y <= bottom


def _component_by_sofl_type(components: list[Component], belong_type: str) -> Component | None:
    normalized = belong_type.strip().lower().replace("_", "")
    aliases = {
        "process": {"process"},
        "datastore": {"datastore"},
        "singlecondition": {"singlecondition"},
        "multiplecondition": {"multiplecondition"},
        "binarycondition": {"binarycondition"},
        "separating": {"separating"},
        "merging": {"merging", "connecting"},
        "connecting": {"merging", "connecting"},
        "broadcasting": {"broadcasting", "broadcasing", "boradcasting"},
        "nondeterministic": {"nondeterministic"},
        "renaming": {"renaming"},
    }
    accepted = aliases.get(normalized, {normalized})
    matches = [component for component in components if component.tag.lower() in accepted]
    if len(matches) == 1:
        return matches[0]
    return None


def _external_endpoint_layout(x: float | None, y: float | None, role: str) -> dict[str, float] | None:
    if x is None or y is None:
        return None
    box_x = x - EXTERNAL_WIDTH if role == "from" else x
    return {
        "x": box_x,
        "y": y - EXTERNAL_HEIGHT / 2,
        "width": EXTERNAL_WIDTH,
        "height": EXTERNAL_HEIGHT,
    }
    return None


def _structures_from_components(components: list[Component], edges: list[Edge]) -> list[GraphStructure]:
    structures: list[GraphStructure] = []
    for component in components:
        if component.node_type in STRUCTURE_KIND_BY_NODE_TYPE:
            outgoing = [edge for edge in edges if edge.source == component.id and edge.kind != "control"]
            if len(outgoing) < 2:
                continue
            structures.append(
                GraphStructure(
                    id=f"{STRUCTURE_KIND_BY_NODE_TYPE[component.node_type]}_{component.id}",
                    kind=STRUCTURE_KIND_BY_NODE_TYPE[component.node_type],
                    source=component.id,
                    condition=component.condition,
                    label=component.label,
                    branches=[
                        StructureBranch(
                            id=f"b{index}",
                            target=edge.target,
                            edges=[edge.id],
                            data=edge.data,
                            condition=edge.condition,
                        )
                        for index, edge in enumerate(outgoing, start=1)
                    ],
                    metadata={"source_format": "sofl-cdfd", "sofl_type": component.tag},
                )
            )
        elif component.node_type in MERGE_NODE_TYPES:
            incoming = [edge for edge in edges if edge.target == component.id and edge.kind != "control"]
            if len(incoming) < 2:
                continue
            structures.append(
                GraphStructure(
                    id=f"merge_{component.id}",
                    kind="merge",
                    target=component.id,
                    label=component.label,
                    branches=[
                        StructureBranch(id=f"b{index}", source=edge.source, edges=[edge.id], data=edge.data)
                        for index, edge in enumerate(incoming, start=1)
                    ],
                    metadata={"source_format": "sofl-cdfd", "sofl_type": component.tag},
                )
            )
    return structures


def _build_graph(
    *,
    nodes: dict[str, Node],
    edges: list[Edge],
    start: str | None,
    starts: set[str],
    ends: set[str],
    structures: list[GraphStructure],
    metadata: dict[str, Any],
) -> CDFDGraph:
    if start:
        starts.add(start)
    if not starts:
        starts = _infer_starts(nodes, edges)
    if not start and starts:
        start = sorted(starts)[0]
    if not ends:
        ends = _infer_ends(nodes, edges)

    missing_starts = sorted(node_id for node_id in starts if node_id not in nodes)
    if missing_starts:
        raise ParseError(f"Start node(s) not defined in SOFL CDFD nodes: {', '.join(missing_starts)}")
    missing_ends = sorted(node_id for node_id in ends if node_id not in nodes)
    if missing_ends:
        raise ParseError(f"End node(s) not defined in SOFL CDFD nodes: {', '.join(missing_ends)}")
    if not start or not starts:
        raise ParseError("SOFL CDFD input must define or infer at least one start node.")
    if not ends:
        raise ParseError("SOFL CDFD input must define or infer at least one end node.")

    return CDFDGraph(
        nodes=nodes,
        edges=edges,
        start=start,
        starts=starts,
        ends=ends,
        structures=structures,
        metadata=metadata,
    )


def _infer_starts(nodes: dict[str, Node], edges: list[Edge]) -> set[str]:
    incoming, outgoing = _degree_maps(nodes, edges)
    starts = {node_id for node_id in nodes if incoming[node_id] == 0 and outgoing[node_id] > 0}
    starts = {
        node_id
        for node_id in starts
        if not _is_control_only_external(node_id, nodes, edges)
    }
    if starts:
        return starts
    raise ParseError("SOFL CDFD input must define start node(s); automatic detection found no source-only node.")


def _infer_ends(nodes: dict[str, Node], edges: list[Edge]) -> set[str]:
    incoming, outgoing = _degree_maps(nodes, edges)
    ends = {node_id for node_id in nodes if outgoing[node_id] == 0 and incoming[node_id] > 0}
    if ends:
        return ends
    raise ParseError("SOFL CDFD input must define end node(s); automatic detection found no sink node.")


def _degree_maps(nodes: dict[str, Node], edges: list[Edge]) -> tuple[dict[str, int], dict[str, int]]:
    incoming = {node_id: 0 for node_id in nodes}
    outgoing = {node_id: 0 for node_id in nodes}
    for edge in edges:
        if edge.kind == "control":
            continue
        outgoing[edge.source] = outgoing.get(edge.source, 0) + 1
        incoming[edge.target] = incoming.get(edge.target, 0) + 1
    return incoming, outgoing


def _is_control_only_external(node_id: str, nodes: dict[str, Node], edges: list[Edge]) -> bool:
    node = nodes.get(node_id)
    if node is None or node.type != "external":
        return False
    if node.metadata.get("inferred_from") != "outside-endpoint":
        return False
    outgoing = [edge for edge in edges if edge.source == node_id]
    return bool(outgoing) and all(edge.kind == "control" for edge in outgoing)


def _edge_kind(tag: str) -> str:
    normalized = tag.lower()
    if normalized == "controldataflow":
        return "control"
    if normalized == "activedataflow":
        return "active-flow"
    return "flow"


def _endpoint_metadata(endpoint: ET.Element | None) -> dict[str, str]:
    if endpoint is None:
        return {}
    return {key: str(value) for key, value in endpoint.attrib.items()}


def _is_outside_endpoint(belong_to_type: str | None) -> bool:
    if not belong_to_type:
        return False
    return belong_to_type.strip().lower().replace("_", "") == "outside"


def _resolve_input_port(
    to_meta: dict[str, str],
    to_y: float | None,
    target_component: Component | None,
) -> int | None:
    """Resolve the side input port index for an edge targeting a process."""
    belong_to_type = to_meta.get("belongToType", "").lower().replace("_", "")
    if belong_to_type in {"processtopbottom", "processtop", "processbottom"}:
        return None

    connector = to_meta.get("belongToConnector") or to_meta.get("connectorIndex")
    if connector is not None and str(connector).strip() not in {"", "-1"}:
        try:
            return int(str(connector).strip())
        except ValueError:
            pass

    if target_component is None or to_y is None:
        return 0

    input_count = _optional_int(target_component.attrs.get("inputPorts")) or 1
    if input_count <= 1:
        return 0

    layout_y = target_component.y
    layout_height = target_component.height
    if layout_y is None or layout_height is None:
        return 0

    step = layout_height / (input_count + 1)
    best_port = 0
    best_distance = float("inf")
    for port in range(input_count):
        port_y = layout_y + step * (port + 1)
        distance = abs(to_y - port_y)
        if distance < best_distance:
            best_distance = distance
            best_port = port
    return best_port


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _unique_id(base: str, used: set[str]) -> str:
    normalized = str(base).strip() or "node"
    if normalized not in used:
        return normalized
    index = 2
    while f"{normalized}_{index}" in used:
        index += 1
    return f"{normalized}_{index}"


def _coerce_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    raise ParseError("SOFL CDFD start/end override must be a string or list.")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    text = _optional_str(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    text = _optional_str(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None
