from __future__ import annotations

from dataclasses import dataclass

from cdfd.concurrent_paths import (
    format_notation,
    flatten_nodes,
    node_element,
    normalize_concurrent_tree,
    normalize_parallel_end_nodes,
    parallel_element,
    sequential_element,
)
from cdfd.models import (
    CDFDGraph,
    CDFDProject,
    ConcurrentPathNode,
    ConcurrentPathResult,
    Edge,
    PathResult,
    ProcessSpec,
)

PARALLEL_KINDS = {"parallel", "broadcast", "separate", "fork"}
EXCLUSIVE_KINDS = {"choice", "select", "condition", "conditional", "non-determinism", "nondeterminism"}


class PathLimitExceeded(RuntimeError):
    """Raised when path generation exceeds the configured safety limit."""


@dataclass(frozen=True)
class PathFindingOptions:
    strategy: str = "simple"
    max_depth: int = 20
    max_paths: int = 10000
    sink_policy: str = "demand"


@dataclass(frozen=True)
class _TokenState:
    tokens: frozenset[str]
    available_data: frozenset[str]
    activated_nodes: frozenset[str]
    edges: tuple[str, ...]
    data: tuple[str, ...]
    conditions: tuple[str, ...]
    preconditions: tuple[str, ...]
    trace: tuple[ConcurrentPathNode, ...]


def can_activate_node(
    graph: CDFDGraph,
    node_id: str,
    available_data: set[str],
    processes: dict[str, ProcessSpec] | None = None,
    *,
    activated_nodes: set[str] | None = None,
) -> bool:
    """Check whether a node can fire given accumulated data and upstream activation."""
    activated = activated_nodes or set()
    process = processes.get(node_id) if processes else None

    if process and process.input_ports:
        port_groups, _ = graph.get_node_input_port_groups(node_id, processes)
        port_ready = [
            _explicit_port_ready(port, group, available_data, activated)
            for port, group in zip(process.input_ports, port_groups)
        ]
        if graph.uses_or_input_ports(node_id, processes):
            return any(port_ready)
        return all(port_ready) if port_ready else True

    if process and process.inputs:
        return set(process.inputs).issubset(available_data)

    port_groups, datastore_edges = graph.get_node_input_port_groups(node_id, processes)
    if not port_groups and not datastore_edges:
        return True

    if graph.uses_or_input_ports(node_id, processes):
        port_ready = any(
            _port_group_ready(group, available_data, activated) for group in port_groups
        )
    else:
        port_ready = all(
            _port_group_ready(group, available_data, activated) for group in port_groups
        ) if port_groups else True

    return port_ready


def _port_group_ready(
    edges: list[Edge],
    available_data: set[str],
    activated_nodes: set[str],
) -> bool:
    """AND semantics within one input port group."""
    if not edges:
        return False
    for edge in edges:
        if edge.data and not set(edge.data).issubset(available_data):
            return False
        if edge.source and edge.source not in activated_nodes:
            return False
    return True


def _explicit_port_ready(
    port,
    edges: list[Edge],
    available_data: set[str],
    activated_nodes: set[str],
) -> bool:
    """Check one explicit JSON port. Default mode is AND."""
    if not edges:
        return False
    edge_ready = [
        _single_edge_ready(edge, available_data, activated_nodes)
        for edge in edges
    ]
    if port.mode == "any":
        return any(edge_ready)
    return all(edge_ready)


def _single_edge_ready(
    edge: Edge,
    available_data: set[str],
    activated_nodes: set[str],
) -> bool:
    if edge.data and not set(edge.data).issubset(available_data):
        return False
    return not edge.source or edge.source in activated_nodes


def find_paths(
    graph: CDFDGraph,
    options: PathFindingOptions | None = None,
    project: CDFDProject | None = None,
) -> list[PathResult]:
    options = options or PathFindingOptions()
    strategy = _normalize_strategy(options.strategy)

    if options.max_depth < 1:
        raise ValueError("max_depth must be at least 1.")
    if options.max_paths < 1:
        raise ValueError("max_paths must be at least 1.")

    processes = project.processes if project else None
    paths: list[PathResult] = []

    def dfs(
        current: str,
        node_path: list[str],
        edge_path: list[str],
        edge_sources: list[str],
        edge_targets: list[str],
        edge_data_path: list[list[str]],
        data_path: list[str],
        conditions: list[str],
        preconditions: list[str],
        available_data: set[str],
        activated_nodes: set[str],
        depth: int,
    ) -> None:
        if current in graph.ends:
            paths.append(
                PathResult(
                    nodes=list(node_path),
                    edges=list(edge_path),
                    edge_sources=list(edge_sources),
                    edge_targets=list(edge_targets),
                    edge_data=[list(items) for items in edge_data_path],
                    data=list(data_path),
                    outputs=_node_outputs(graph, current),
                    preconditions=list(preconditions),
                    conditions=list(conditions),
                    sink=current,
                )
            )
            if len(paths) > options.max_paths:
                raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")
            return

        if strategy == "max-depth" and depth >= options.max_depth:
            return

        for edge in graph.outgoing_edges(current):
            if not _is_path_edge(graph, edge):
                continue
            if strategy == "simple" and edge.target in node_path:
                continue

            next_available = set(available_data)
            next_available.update(edge.data)
            next_activated = set(activated_nodes)
            next_activated.add(current)
            if _requires_activation_gate(graph, edge.target, processes) and not can_activate_node(
                graph,
                edge.target,
                next_available,
                processes,
                activated_nodes=next_activated,
            ):
                continue

            next_conditions = _extend_unique(
                conditions,
                [*_edge_conditions(edge), *_incoming_control_conditions(graph, edge.target)],
            )
            next_preconditions = _merge_preconditions(
                preconditions,
                _incoming_control_conditions(graph, edge.target),
            )
            dfs(
                edge.target,
                [*node_path, edge.target],
                [*edge_path, edge.id],
                [*edge_sources, edge.source],
                [*edge_targets, edge.target],
                [*edge_data_path, list(edge.data)],
                [*data_path, *edge.data],
                next_conditions,
                next_preconditions,
                next_available,
                next_activated,
                depth + 1,
            )

    port_and_groups = _find_port_and_groups(graph, processes)
    and_input_groups = _find_and_input_groups(graph, processes)
    starts = _effective_path_starts(graph)

    for start in sorted(starts):
        start_preconditions = _incoming_control_conditions(graph, start)
        dfs(
            start,
            [start],
            [],
            [],
            [],
            [],
            [],
            _incoming_control_conditions(graph, start),
            start_preconditions,
            set(),
            {start},
            0,
        )

    launched_groups: set[frozenset[str]] = set()
    for target_node, group_edges in port_and_groups:
        sources = {edge.source for edge in group_edges}
        start_sources = sources & starts
        if len(start_sources) < 2 or start_sources != sources:
            continue
        group_key = frozenset(start_sources)
        if group_key in launched_groups:
            continue
        available_data: set[str] = set()
        edge_ids: list[str] = []
        edge_sources: list[str] = []
        edge_targets: list[str] = []
        edge_data_path: list[list[str]] = []
        data_items: list[str] = []
        for edge in group_edges:
            available_data.update(edge.data)
            edge_ids.append(edge.id)
            edge_sources.append(edge.source)
            edge_targets.append(edge.target)
            edge_data_path.append(list(edge.data))
            data_items.extend(edge.data)
        if not can_activate_node(
            graph,
            target_node,
            available_data,
            processes,
            activated_nodes=set(start_sources),
        ):
            continue
        launched_groups.add(group_key)
        group_conditions: list[str] = []
        group_preconditions: list[str] = []
        for start in sorted(start_sources):
            start_conditions = _incoming_control_conditions(graph, start)
            group_conditions = _extend_unique(group_conditions, start_conditions)
            group_preconditions = _merge_preconditions(group_preconditions, start_conditions)
        ordered_sources = sorted(start_sources)
        dfs(
            target_node,
            [*ordered_sources, target_node],
            edge_ids,
            edge_sources,
            edge_targets,
            edge_data_path,
            data_items,
            group_conditions,
            group_preconditions,
            available_data,
            set(start_sources),
            0,
        )

    launched_and_groups: set[frozenset[str]] = set()
    for target_node, group_edges, start_sources in and_input_groups:
        group_key = frozenset(start_sources)
        if group_key in launched_and_groups:
            continue
        available_data = set()
        edge_ids = []
        edge_sources = []
        edge_targets = []
        edge_data_path = []
        data_items = []
        for edge in group_edges:
            if edge.source not in start_sources:
                continue
            available_data.update(edge.data)
            edge_ids.append(edge.id)
            edge_sources.append(edge.source)
            edge_targets.append(edge.target)
            edge_data_path.append(list(edge.data))
            data_items.extend(edge.data)
        if not can_activate_node(
            graph,
            target_node,
            available_data,
            processes,
            activated_nodes=set(start_sources),
        ):
            continue
        launched_and_groups.add(group_key)
        group_conditions = []
        group_preconditions = []
        for start in sorted(start_sources):
            start_conditions = _incoming_control_conditions(graph, start)
            group_conditions = _extend_unique(group_conditions, start_conditions)
            group_preconditions = _merge_preconditions(group_preconditions, start_conditions)
        ordered_sources = sorted(start_sources)
        dfs(
            target_node,
            [*ordered_sources, target_node],
            edge_ids,
            edge_sources,
            edge_targets,
            edge_data_path,
            data_items,
            group_conditions,
            group_preconditions,
            available_data,
            set(start_sources),
            0,
        )
    return _dedupe_paths(sorted(paths, key=lambda path: (len(path.nodes), path.nodes, path.edges)))


def find_concurrent_paths(
    graph: CDFDGraph,
    options: PathFindingOptions | None = None,
    project: CDFDProject | None = None,
) -> list[ConcurrentPathResult]:
    """Token-based exploration for parallel forks and AND multi-input joins."""
    options = options or PathFindingOptions()
    strategy = _normalize_strategy(options.strategy)
    processes = project.processes if project else None
    starts = sorted(_effective_path_starts(graph))
    results: list[ConcurrentPathResult] = []
    visited: set[tuple] = set()
    seen_results: set[tuple] = set()

    initial_states = _initial_token_states(graph, starts, processes)

    def explore(state: _TokenState, depth: int) -> None:
        if _is_concurrent_complete(graph, state):
            result_key = (tuple(sorted(state.edges)), frozenset(state.activated_nodes))
            if result_key not in seen_results:
                seen_results.add(result_key)
                results.append(_state_to_concurrent_result(state, graph, processes))
            if len(results) > options.max_paths:
                raise PathLimitExceeded(f"Concurrent path generation exceeded max_paths={options.max_paths}.")
            return

        if strategy == "max-depth" and depth >= options.max_depth:
            return

        state_key = (
            state.tokens,
            state.available_data,
            state.activated_nodes,
            state.edges,
        )
        if state_key in visited:
            return
        visited.add(state_key)

        if not state.tokens:
            return

        next_states = _expand_token_state(graph, state, processes)
        for next_state in next_states:
            explore(next_state, depth + 1)

    for initial_state in initial_states:
        explore(initial_state, 0)

    return sorted(results, key=lambda item: (len(item.nodes), item.nodes, item.edges))


def detect_cycles(graph: CDFDGraph) -> list[list[str]]:
    state: dict[str, str] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def visit(node_id: str) -> None:
        state[node_id] = "gray"
        stack.append(node_id)

        for edge in graph.outgoing_edges(node_id):
            if not _is_path_edge(graph, edge):
                continue
            target = edge.target
            if state.get(target) == "gray":
                start_index = stack.index(target)
                cycle = [*stack[start_index:], target]
                key = _canonical_cycle_key(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif state.get(target) is None:
                visit(target)

        stack.pop()
        state[node_id] = "black"

    for node_id in graph.nodes:
        if state.get(node_id) is None:
            visit(node_id)

    return cycles


def _initial_token_states(
    graph: CDFDGraph,
    starts: list[str],
    processes: dict[str, ProcessSpec] | None,
) -> list[_TokenState]:
    start_set = set(starts)
    states: list[_TokenState] = []

    if _requires_sync_start(graph, processes):
        all_conditions: list[str] = []
        all_preconditions: list[str] = []
        for start in starts:
            start_conditions = _incoming_control_conditions(graph, start)
            all_conditions = _extend_unique(all_conditions, start_conditions)
            all_preconditions = _merge_preconditions(all_preconditions, start_conditions)
        return [
            _TokenState(
                tokens=frozenset(starts),
                available_data=frozenset(),
                activated_nodes=frozenset(starts),
                edges=(),
                data=(),
                conditions=tuple(all_conditions),
                preconditions=tuple(all_preconditions),
                trace=(parallel_element([node_element(start) for start in starts]),),
            )
        ]

    for start in starts:
        start_conditions = _incoming_control_conditions(graph, start)
        states.append(
            _TokenState(
                tokens=frozenset({start}),
                available_data=frozenset(),
                activated_nodes=frozenset({start}),
                edges=(),
                data=(),
                conditions=tuple(start_conditions),
                preconditions=tuple(_merge_preconditions([], start_conditions)),
                trace=(node_element(start),),
            )
        )

    launched_groups: set[frozenset[str]] = set()
    for _, group_edges in _find_port_and_groups(graph, processes):
        sources = {edge.source for edge in group_edges}
        start_sources = sources & start_set
        if len(start_sources) < 2 or start_sources != sources:
            continue
        group_key = frozenset(start_sources)
        if group_key in launched_groups:
            continue
        launched_groups.add(group_key)
        all_conditions = []
        all_preconditions = []
        for start in sorted(start_sources):
            start_conditions = _incoming_control_conditions(graph, start)
            all_conditions = _extend_unique(all_conditions, start_conditions)
            all_preconditions = _merge_preconditions(all_preconditions, start_conditions)
        states.append(
            _TokenState(
                tokens=frozenset(start_sources),
                available_data=frozenset(),
                activated_nodes=frozenset(start_sources),
                edges=(),
                data=(),
                conditions=tuple(all_conditions),
                preconditions=tuple(all_preconditions),
                trace=(parallel_element([node_element(start) for start in sorted(start_sources)]),),
            )
        )

    return states


def _requires_sync_start(
    graph: CDFDGraph,
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    if graph.metadata.get("start_sync"):
        return True

    starts = graph.starts or {graph.start}
    if len(starts) <= 1:
        return False

    for node_id, process in (processes or {}).items():
        if len(process.inputs) < 2:
            continue
        incoming_sources = {
            edge.source
            for edge in graph.incoming_edges(node_id)
            if _is_path_edge(graph, edge) and edge.source in starts
        }
        if len(incoming_sources) >= 2:
            return True
    return False


def _expand_token_state(
    graph: CDFDGraph,
    state: _TokenState,
    processes: dict[str, ProcessSpec] | None,
) -> list[_TokenState]:
    if len(state.tokens) > 1:
        multi_state = _advance_all_tokens(graph, state, processes)
        if multi_state is not None:
            return [multi_state]

    next_states: list[_TokenState] = []
    movable_tokens = sorted(state.tokens)

    for token in movable_tokens:
        if token in graph.ends and token in state.activated_nodes:
            continue

        outgoing = [edge for edge in graph.outgoing_edges(token) if _is_path_edge(graph, edge)]
        if not outgoing:
            continue

        if _should_fork_parallel(graph, token, outgoing, processes):
            fork_state = _apply_parallel_fork(graph, state, token, outgoing, processes)
            if fork_state is not None:
                next_states.append(fork_state)
            continue

        for edge in outgoing:
            transition = _apply_edge_transition(graph, state, token, edge, processes)
            if transition is not None:
                next_states.append(transition)

    if not next_states:
        join_state = _activate_ready_join_nodes(graph, state, processes)
        if join_state is not None:
            next_states.append(join_state)

    return next_states


def _advance_all_tokens(
    graph: CDFDGraph,
    state: _TokenState,
    processes: dict[str, ProcessSpec] | None,
) -> _TokenState | None:
    """Advance every active token in one synchronized step."""
    moves: list[tuple[str, Edge | None]] = []
    for token in sorted(state.tokens):
        if token in graph.ends and token in state.activated_nodes:
            moves.append((token, None))
            continue

        outgoing = [edge for edge in graph.outgoing_edges(token) if _is_path_edge(graph, edge)]
        if not outgoing:
            continue
        if len(outgoing) != 1:
            return None
        moves.append((token, outgoing[0]))

    if not moves:
        return _activate_ready_join_nodes(graph, state, processes)

    next_state = state
    for token, edge in moves:
        if edge is None:
            continue
        next_state = _apply_edge_transition(graph, next_state, token, edge, processes)
        if next_state is None:
            return None

    join_state = _activate_ready_join_nodes(graph, next_state, processes)
    return join_state or next_state


def _activate_ready_join_nodes(
    graph: CDFDGraph,
    state: _TokenState,
    processes: dict[str, ProcessSpec] | None,
) -> _TokenState | None:
    """Activate join targets once all required inputs and upstream nodes are ready."""
    activated = set(state.activated_nodes)
    tokens = set(state.tokens)
    available = set(state.available_data)
    changed = False

    for node_id in sorted(graph.nodes):
        if node_id in activated:
            continue
        if not can_activate_node(
            graph,
            node_id,
            available,
            processes,
            activated_nodes=activated,
        ):
            continue
        incoming = [edge for edge in graph.incoming_edges(node_id) if _is_path_edge(graph, edge)]
        if not incoming:
            continue
        port_groups, _ = graph.get_node_input_port_groups(node_id, processes)
        if graph.uses_or_input_ports(node_id, processes):
            ready = any(
                all(edge.source in activated for edge in group) for group in port_groups
            )
        else:
            ready = all(edge.source in activated for edge in incoming)
        if not ready:
            continue
        activated.add(node_id)
        tokens.add(node_id)
        changed = True

    if not changed:
        return None

    trace = list(state.trace)
    for node_id in sorted(activated):
        if node_id in state.activated_nodes:
            continue
        trace = _append_trace(trace, node_element(node_id))

    return _TokenState(
        tokens=frozenset(tokens),
        available_data=state.available_data,
        activated_nodes=frozenset(activated),
        edges=state.edges,
        data=state.data,
        conditions=state.conditions,
        preconditions=state.preconditions,
        trace=tuple(trace),
    )


def _apply_parallel_fork(
    graph: CDFDGraph,
    state: _TokenState,
    token: str,
    edges: list[Edge],
    processes: dict[str, ProcessSpec] | None,
) -> _TokenState | None:
    activated = set(state.activated_nodes)
    activated.add(token)

    available_data = set(state.available_data)
    edge_ids = list(state.edges)
    data_items = list(state.data)
    conditions = list(state.conditions)
    preconditions = list(state.preconditions)
    branch_traces: list[ConcurrentPathNode] = []
    next_tokens = set(state.tokens)
    next_tokens.discard(token)
    progressed = False

    for edge in edges:
        available_data.update(edge.data)
        edge_ids.append(edge.id)
        data_items.extend(edge.data)
        conditions = _extend_unique(conditions, _edge_conditions(edge))
        conditions = _extend_unique(conditions, _incoming_control_conditions(graph, edge.target))
        preconditions = _merge_preconditions(
            preconditions,
            _incoming_control_conditions(graph, edge.target),
        )
        next_tokens.add(edge.target)
        activated.add(edge.target)
        branch_traces.append(sequential_element([node_element(edge.target)]))
        progressed = True

    if not progressed:
        return None

    parallel_trace = parallel_element(branch_traces)
    new_trace = _append_trace(state.trace, parallel_trace, replace_node=token)

    return _TokenState(
        tokens=frozenset(next_tokens),
        available_data=frozenset(available_data),
        activated_nodes=frozenset(activated),
        edges=tuple(edge_ids),
        data=tuple(data_items),
        conditions=tuple(conditions),
        preconditions=tuple(preconditions),
        trace=tuple(new_trace),
    )


def _apply_edge_transition(
    graph: CDFDGraph,
    state: _TokenState,
    token: str,
    edge: Edge,
    processes: dict[str, ProcessSpec] | None,
) -> _TokenState | None:
    available_data = set(state.available_data)
    available_data.update(edge.data)

    activated = set(state.activated_nodes)
    activated.add(token)

    edge_conditions = _edge_conditions(edge)
    incoming_conditions = _incoming_control_conditions(graph, edge.target)
    conditions = _extend_unique(list(state.conditions), [*edge_conditions, *incoming_conditions])
    preconditions = _merge_preconditions(list(state.preconditions), incoming_conditions)

    next_tokens = set(state.tokens)
    next_tokens.discard(token)

    target_ready = _edge_enables_target(
        graph,
        edge,
        available_data,
        activated,
        processes,
    )
    trace = list(state.trace)
    if target_ready:
        next_tokens.add(edge.target)
        activated.add(edge.target)
        trace = _append_trace(trace, node_element(edge.target), replace_node=token)
    else:
        trace = list(state.trace)

    return _TokenState(
        tokens=frozenset(next_tokens),
        available_data=frozenset(available_data),
        activated_nodes=frozenset(activated),
        edges=(*state.edges, edge.id),
        data=(*state.data, *edge.data),
        conditions=tuple(conditions),
        preconditions=tuple(preconditions),
        trace=tuple(trace),
    )


def _append_trace(
    trace: list[ConcurrentPathNode] | tuple[ConcurrentPathNode, ...],
    new_element: ConcurrentPathNode,
    *,
    replace_node: str | None = None,
) -> list[ConcurrentPathNode]:
    items = list(trace)
    if replace_node and items:
        last = items[-1]
        if last.kind == "node" and last.node_id == replace_node:
            items[-1] = sequential_element([last, new_element])
            return items
    items.append(new_element)
    return items


def _state_to_concurrent_result(
    state: _TokenState,
    graph: CDFDGraph,
    processes: dict[str, ProcessSpec] | None = None,
) -> ConcurrentPathResult:
    if state.trace:
        if len(state.trace) == 1:
            root = state.trace[0]
        else:
            root = sequential_element(list(state.trace))
    else:
        root = sequential_element([node_element(node_id) for node_id in sorted(state.activated_nodes)])

    root = normalize_concurrent_tree(root)
    root = normalize_parallel_end_nodes(root, graph.ends)
    notation = format_notation(root)
    flat_nodes = flatten_nodes(root)
    end_nodes = [node_id for node_id in flat_nodes if node_id in graph.ends]
    outputs = _unique(
        output
        for node_id in end_nodes
        for output in _collect_path_outputs(
            graph,
            node_id,
            node_path=flat_nodes,
            processes=processes,
        )
    )

    return ConcurrentPathResult(
        root=root,
        nodes=flat_nodes,
        edges=list(state.edges),
        data=list(state.data),
        outputs=outputs or list(state.data[-1:] if state.data else []),
        preconditions=list(state.preconditions),
        conditions=list(state.conditions),
        notation=notation,
    )


def _should_fork_parallel(
    graph: CDFDGraph,
    node_id: str,
    edges: list[Edge],
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    if len(edges) <= 1:
        return False
    if _has_structure_kind(graph, node_id, EXCLUSIVE_KINDS, role="source"):
        return False
    if _has_structure_kind(graph, node_id, PARALLEL_KINDS, role="source"):
        return True
    if _edges_span_alternative_output_ports(graph, node_id, edges, processes):
        return False
    conditions = [edge.condition for edge in edges if edge.condition]
    if len(conditions) >= 2:
        return False
    return True


def _edges_span_alternative_output_ports(
    graph: CDFDGraph,
    node_id: str,
    edges: list[Edge],
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    if not graph.uses_or_output_ports(node_id, processes):
        return False
    selected = {edge.id for edge in edges}
    explicit_ports = bool(processes and node_id in processes and processes[node_id].output_ports)
    if not explicit_ports and any(not _has_output_port_metadata(edge) for edge in edges):
        return True
    groups = graph.get_node_output_port_groups(node_id, processes)
    selected_groups = [group for group in groups if selected & {edge.id for edge in group}]
    if not selected_groups:
        return True
    return len(selected_groups) > 1


def _has_output_port_metadata(edge: Edge) -> bool:
    if edge.metadata.get("output_port") is not None:
        return True
    from_meta = edge.metadata.get("from", {})
    connector = from_meta.get("belongToConnector") or from_meta.get("connectorIndex")
    return connector is not None and str(connector).strip() not in {"", "-1"}


def _has_structure_kind(
    graph: CDFDGraph,
    node_id: str,
    kinds: set[str],
    *,
    role: str,
) -> bool:
    normalized_kinds = {kind.lower().replace("_", "-") for kind in kinds}
    for structure in graph.structures:
        normalized = structure.kind.lower().replace("_", "-")
        if normalized not in normalized_kinds:
            continue
        if role == "source" and structure.source == node_id:
            return True
        if role == "target" and structure.target == node_id:
            return True
    return False


def _canonical_cycle_key(cycle: list[str]) -> tuple[str, ...]:
    body = cycle[:-1]
    if not body:
        return tuple(cycle)
    rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
    return min(rotations)


def _is_concurrent_complete(graph: CDFDGraph, state: _TokenState) -> bool:
    """Complete when active tokens sit on terminal nodes, or all graph ends are reached."""
    if not graph.ends:
        return False
    if state.tokens and state.tokens <= graph.ends:
        return True
    return graph.ends <= state.activated_nodes


def _edge_enables_target(
    graph: CDFDGraph,
    edge: Edge,
    available_data: set[str],
    activated_nodes: set[str],
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    """Check whether traversing one edge may activate its target."""
    if edge.data and not set(edge.data).issubset(available_data):
        return False
    if edge.source and edge.source not in activated_nodes:
        return False
    if _requires_concurrent_activation_gate(graph, edge.target, processes):
        return can_activate_node(
            graph,
            edge.target,
            available_data,
            processes,
            activated_nodes=activated_nodes,
        )
    return True


def _requires_concurrent_activation_gate(
    graph: CDFDGraph,
    node_id: str,
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    if graph.uses_or_input_ports(node_id, processes):
        return True
    if processes and node_id in processes and processes[node_id].inputs:
        return True
    starts = graph.starts or {graph.start}
    incoming = [
        edge for edge in graph.incoming_edges(node_id) if _is_path_edge(graph, edge)
    ]
    if not incoming:
        return False
    return all(edge.source in starts for edge in incoming)


def _requires_activation_gate(
    graph: CDFDGraph,
    node_id: str,
    processes: dict[str, ProcessSpec] | None,
) -> bool:
    if graph.uses_or_input_ports(node_id, processes):
        return True
    if not processes or node_id not in processes or not processes[node_id].inputs:
        return False
    starts = graph.starts or {graph.start}
    incoming = [
        edge for edge in graph.incoming_edges(node_id) if _is_path_edge(graph, edge)
    ]
    if not incoming:
        return False
    return all(edge.source in starts for edge in incoming)


def _find_port_and_groups(
    graph: CDFDGraph,
    processes: dict[str, ProcessSpec] | None,
) -> list[tuple[str, list[Edge]]]:
    """Find OR-process port groups that require multiple independent starts (AND within port)."""
    groups: list[tuple[str, list[Edge]]] = []
    for node_id in graph.nodes:
        if not graph.uses_or_input_ports(node_id, processes):
            continue
        port_groups, _ = graph.get_node_input_port_groups(node_id, processes)
        for group in port_groups:
            if len(group) < 2:
                continue
            sources = {edge.source for edge in group}
            if len(sources) >= 2:
                groups.append((node_id, group))
    return groups


def _find_and_input_groups(
    graph: CDFDGraph,
    processes: dict[str, ProcessSpec] | None,
) -> list[tuple[str, list[Edge], set[str]]]:
    """Find ProcessSpec AND inputs that must arrive from multiple independent starts."""
    if not processes:
        return []

    starts = graph.starts or {graph.start}
    groups: list[tuple[str, list[Edge], set[str]]] = []
    for node_id, process in processes.items():
        if process.input_ports:
            for port in process.input_ports:
                if len(port.data) < 2 and len(port.edges) < 2:
                    continue
                incoming = _matching_port_edges(graph.incoming_edges(node_id), port)
                start_sources = {edge.source for edge in incoming if edge.source in starts}
                if len(start_sources) >= 2:
                    groups.append((node_id, incoming, start_sources))
            continue
        if len(process.inputs) < 2:
            continue
        incoming = [
            edge for edge in graph.incoming_edges(node_id) if _is_path_edge(graph, edge)
        ]
        start_sources = {edge.source for edge in incoming if edge.source in starts}
        if len(start_sources) >= 2:
            groups.append((node_id, incoming, start_sources))
    return groups


def _matching_port_edges(edges: list[Edge], port) -> list[Edge]:
    port_edges = set(port.edges)
    port_data = set(port.data)
    return [
        edge
        for edge in edges
        if not _is_control_edge(edge)
        and (
            (port_edges and edge.id in port_edges)
            or (port_data and bool(port_data & set(edge.data)))
        )
    ]


def _dedupe_paths(paths: list[PathResult]) -> list[PathResult]:
    unique_paths: list[PathResult] = []
    seen: set[tuple] = set()
    for path in paths:
        key = (
            tuple(path.nodes),
            tuple(path.edges),
            tuple(path.edge_sources),
            tuple(path.edge_targets),
            tuple(tuple(items) for items in path.edge_data),
            tuple(path.data),
            tuple(path.conditions),
            tuple(path.preconditions),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def _effective_path_starts(graph: CDFDGraph) -> set[str]:
    starts = set(graph.starts or {graph.start})
    if graph.metadata.get("source_format") != "sofl-cdfd":
        return starts
    if not any(not _is_sofl_support_start(graph, node_id) for node_id in starts):
        return starts

    removable = {
        node_id
        for node_id in starts
        if _is_auxiliary_sofl_start(graph, node_id, starts)
    }
    filtered = starts - removable
    return filtered or starts


def _is_auxiliary_sofl_start(graph: CDFDGraph, node_id: str, starts: set[str]) -> bool:
    if not _is_sofl_support_start(graph, node_id):
        return False

    outgoing = [
        edge for edge in graph.outgoing_edges(node_id) if _is_path_edge(graph, edge)
    ]
    if not outgoing:
        return False

    for edge in outgoing:
        target_incoming = [
            incoming
            for incoming in graph.incoming_edges(edge.target)
            if _is_path_edge(graph, incoming)
        ]
        if any(incoming.source not in starts for incoming in target_incoming):
            return True
    return False


def _is_sofl_support_start(graph: CDFDGraph, node_id: str) -> bool:
    node = graph.nodes.get(node_id)
    if node is None:
        return False
    if node.type == "data_store":
        return True
    return node.type == "external" and node.metadata.get("inferred_from") == "outside-endpoint"


def _normalize_strategy(strategy: str) -> str:
    normalized = strategy.replace("_", "-").lower()
    if normalized in {"simple", "simple-paths"}:
        return "simple"
    if normalized in {"max-depth", "depth"}:
        return "max-depth"
    raise ValueError("strategy must be either 'simple' or 'max-depth'.")


def _collect_path_outputs(
    graph: CDFDGraph,
    sink_node: str,
    *,
    node_path: list[str] | None = None,
    processes: dict[str, ProcessSpec] | None = None,
) -> list[str]:
    from cdfd.flow_decomposition import collect_path_outputs

    return collect_path_outputs(
        graph,
        sink_node,
        node_path=node_path,
        processes=processes,
    )


def _node_outputs(graph: CDFDGraph, node_id: str) -> list[str]:
    raw_outputs = graph.metadata.get("outputs", {})
    if isinstance(raw_outputs, dict):
        value = raw_outputs.get(node_id, [])
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _is_control_edge(edge: Edge) -> bool:
    return edge.kind.lower().replace("_", "-") == "control"


def _is_path_edge(graph: CDFDGraph, edge: Edge) -> bool:
    if not _is_control_edge(edge):
        return True
    source = graph.nodes.get(edge.source)
    return bool(source and source.type.lower().endswith("_condition"))


def _edge_conditions(edge: Edge) -> list[str]:
    return [edge.condition] if edge.condition else []


def _incoming_control_conditions(graph: CDFDGraph, node_id: str) -> list[str]:
    conditions: list[str] = []
    for edge in graph.incoming_edges(node_id):
        if not _is_control_edge(edge):
            continue
        if edge.condition:
            conditions.append(edge.condition)
        elif edge.label:
            conditions.append(edge.label)
        elif edge.data:
            conditions.append(", ".join(edge.data))
    return conditions


def _merge_preconditions(existing: list[str], additions: list[str]) -> list[str]:
    return _extend_unique(existing, additions)


def _extend_unique(existing: list[str], additions: list[str]) -> list[str]:
    values = list(existing)
    seen = set(values)
    for item in additions:
        if item not in seen:
            values.append(item)
            seen.add(item)
    return values


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values
