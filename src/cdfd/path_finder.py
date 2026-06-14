from __future__ import annotations

from dataclasses import dataclass

from cdfd.concurrent_paths import (
    format_notation,
    flatten_nodes,
    node_element,
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
) -> bool:
    """Check whether accumulated data satisfies all required inputs (AND semantics)."""
    required_inputs = graph.get_node_required_inputs(node_id, processes)
    if required_inputs:
        return required_inputs.issubset(available_data)

    non_control_incoming = [
        edge for edge in graph.incoming_edges(node_id) if not _is_control_edge(edge)
    ]
    if not non_control_incoming:
        return True

    required_edge_data: set[str] = set()
    for edge in non_control_incoming:
        required_edge_data.update(edge.data)
    if required_edge_data:
        return required_edge_data.issubset(available_data)

    required_sources = {edge.source for edge in non_control_incoming}
    return required_sources.issubset(available_data)


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
        data_path: list[str],
        conditions: list[str],
        preconditions: list[str],
        depth: int,
    ) -> None:
        if current in graph.ends:
            paths.append(
                PathResult(
                    nodes=list(node_path),
                    edges=list(edge_path),
                    data=list(data_path),
                    outputs=_node_outputs(graph, current),
                    preconditions=list(preconditions),
                    conditions=list(conditions),
                )
            )
            if len(paths) > options.max_paths:
                raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")
            return

        if strategy == "max-depth" and depth >= options.max_depth:
            return

        for edge in graph.outgoing_edges(current):
            if _is_control_edge(edge):
                continue
            if strategy == "simple" and edge.target in node_path:
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
                [*data_path, *edge.data],
                next_conditions,
                next_preconditions,
                depth + 1,
            )

    for start in sorted(graph.starts or {graph.start}):
        start_preconditions = _incoming_control_conditions(graph, start)
        dfs(
            start,
            [start],
            [],
            [],
            _incoming_control_conditions(graph, start),
            start_preconditions,
            0,
        )
    return sorted(paths, key=lambda path: (len(path.nodes), path.nodes, path.edges))


def find_concurrent_paths(
    graph: CDFDGraph,
    options: PathFindingOptions | None = None,
    project: CDFDProject | None = None,
) -> list[ConcurrentPathResult]:
    """Token-based exploration for parallel forks and AND multi-input joins."""
    options = options or PathFindingOptions()
    strategy = _normalize_strategy(options.strategy)
    processes = project.processes if project else None
    starts = sorted(graph.starts or {graph.start})
    results: list[ConcurrentPathResult] = []
    visited: set[tuple] = set()
    seen_results: set[tuple] = set()

    initial_states = _initial_token_states(graph, starts, processes)

    def explore(state: _TokenState, depth: int) -> None:
        if graph.ends and graph.ends <= state.activated_nodes:
            result_key = (tuple(sorted(state.edges)), frozenset(state.activated_nodes))
            if result_key not in seen_results:
                seen_results.add(result_key)
                results.append(_state_to_concurrent_result(state, graph))
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
            if _is_control_edge(edge):
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

    states: list[_TokenState] = []
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

    for node_id in graph.nodes:
        required = graph.get_node_required_inputs(node_id, processes)
        if len(required) < 2:
            continue
        incoming_sources = {
            edge.source
            for edge in graph.incoming_edges(node_id)
            if not _is_control_edge(edge) and edge.source in starts
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

        outgoing = [edge for edge in graph.outgoing_edges(token) if not _is_control_edge(edge)]
        if not outgoing:
            continue

        if _should_fork_parallel(graph, token, outgoing):
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

        outgoing = [edge for edge in graph.outgoing_edges(token) if not _is_control_edge(edge)]
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
        if not can_activate_node(graph, node_id, available, processes):
            continue
        incoming = [edge for edge in graph.incoming_edges(node_id) if not _is_control_edge(edge)]
        if not incoming:
            continue
        if all(edge.source in activated for edge in incoming):
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

    target_ready = can_activate_node(graph, edge.target, available_data, processes)
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


def _state_to_concurrent_result(state: _TokenState, graph: CDFDGraph) -> ConcurrentPathResult:
    if state.trace:
        if len(state.trace) == 1:
            root = state.trace[0]
        else:
            root = sequential_element(list(state.trace))
    else:
        root = sequential_element([node_element(node_id) for node_id in sorted(state.activated_nodes)])

    notation = format_notation(root)
    flat_nodes = flatten_nodes(root)
    end_nodes = [node_id for node_id in flat_nodes if node_id in graph.ends]
    outputs = _unique(
        output
        for node_id in end_nodes
        for output in _node_outputs(graph, node_id)
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


def _should_fork_parallel(graph: CDFDGraph, node_id: str, edges: list[Edge]) -> bool:
    if len(edges) <= 1:
        return False
    if _has_structure_kind(graph, node_id, EXCLUSIVE_KINDS, role="source"):
        return False
    if _has_structure_kind(graph, node_id, PARALLEL_KINDS, role="source"):
        return True
    conditions = [edge.condition for edge in edges if edge.condition]
    if len(conditions) >= 2:
        return False
    return True


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


def _normalize_strategy(strategy: str) -> str:
    normalized = strategy.replace("_", "-").lower()
    if normalized in {"simple", "simple-paths"}:
        return "simple"
    if normalized in {"max-depth", "depth"}:
        return "max-depth"
    raise ValueError("strategy must be either 'simple' or 'max-depth'.")


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
