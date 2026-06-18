from __future__ import annotations

from cdfd.models import ConcurrentPathNode, ConcurrentPathResult, PathRelation, PathResult


def node_element(node_id: str, label: str | None = None) -> ConcurrentPathNode:
    return ConcurrentPathNode(kind="node", node_id=node_id, label=label)


def sequential_element(children: list[ConcurrentPathNode]) -> ConcurrentPathNode:
    return ConcurrentPathNode(kind="sequential", children=children)


def parallel_element(branches: list[ConcurrentPathNode]) -> ConcurrentPathNode:
    return ConcurrentPathNode(kind="parallel", children=branches)


def normalize_concurrent_tree(root: ConcurrentPathNode) -> ConcurrentPathNode:
    """Flatten nested structure and remove presentation-level duplicates."""
    if root.kind == "node":
        return root

    normalized_children = [normalize_concurrent_tree(child) for child in root.children]
    normalized_children = [
        child for child in normalized_children if not (child.kind != "node" and not child.children)
    ]

    if root.kind == "sequential":
        flattened: list[ConcurrentPathNode] = []
        for child in normalized_children:
            if child.kind == "sequential":
                flattened.extend(child.children)
            else:
                flattened.append(child)

        collapsed: list[ConcurrentPathNode] = []
        for child in flattened:
            if collapsed and _same_atomic_node(collapsed[-1], child):
                continue
            collapsed.append(child)
        if len(collapsed) == 1:
            return collapsed[0]
        return sequential_element(collapsed)

    if root.kind == "parallel":
        branches: list[ConcurrentPathNode] = []
        seen: set[str] = set()
        for child in normalized_children:
            key = format_notation(child)
            if key in seen:
                continue
            seen.add(key)
            branches.append(child)
        if len(branches) == 1:
            return branches[0]
        return parallel_element(branches)

    return root


def normalize_parallel_end_nodes(root: ConcurrentPathNode, ends: set[str]) -> ConcurrentPathNode:
    """Wrap trailing sequential sink nodes as a parallel group."""
    if root.kind != "sequential" or len(root.children) < 2:
        return root

    children = list(root.children)
    trailing: list[ConcurrentPathNode] = []
    while children and children[-1].kind == "node" and children[-1].node_id in ends:
        trailing.insert(0, children.pop())

    if len(trailing) >= 2:
        children.append(parallel_element(trailing))
    elif trailing:
        children.extend(trailing)

    if not children:
        return root
    if len(children) == 1:
        return children[0]
    return sequential_element(children)


def flatten_nodes(root: ConcurrentPathNode) -> list[str]:
    if root.kind == "node" and root.node_id:
        return [root.node_id]
    if root.kind == "sequential":
        nodes: list[str] = []
        for child in root.children:
            nodes.extend(flatten_nodes(child))
        return nodes
    if root.kind == "parallel":
        nodes: list[str] = []
        for child in root.children:
            nodes.extend(flatten_nodes(child))
        return nodes
    return []


def format_notation(root: ConcurrentPathNode) -> str:
    if root.kind == "node" and root.node_id:
        return root.label or root.node_id
    if root.kind == "sequential":
        parts = [format_notation(child) for child in root.children]
        return " -> ".join(parts)
    if root.kind == "parallel":
        branches = [format_notation(child) for child in root.children]
        return f"[ {' || '.join(branches) } ]"
    return ""


def build_concurrent_tree_from_paths(
    paths: list[PathResult],
    relation: PathRelation,
) -> ConcurrentPathNode:
    """Build a nested concurrent tree from linear paths sharing a parallel relation."""
    prefix = relation.shared_prefix
    if not paths:
        return sequential_element([])

    prefix_nodes = [node_element(node_id) for node_id in prefix]
    branches: list[ConcurrentPathNode] = []

    for path in paths:
        suffix = path.nodes[len(prefix):]
        if not suffix:
            continue
        branch_children = [node_element(node_id) for node_id in suffix]
        branches.append(sequential_element(branch_children))

    if len(branches) == 1:
        children = [*prefix_nodes, branches[0]]
    elif branches:
        children = [*prefix_nodes, parallel_element(branches)]
    else:
        children = prefix_nodes

    return normalize_concurrent_tree(sequential_element(children))


def build_concurrent_results_from_relations(
    paths: list[PathResult],
    relations: list[PathRelation],
) -> list[ConcurrentPathResult]:
    """Derive concurrent path results from detected parallel relations."""
    parallel_relations = [relation for relation in relations if relation.kind == "parallel"]
    if not parallel_relations:
        return []

    path_by_id = {f"P{index}": path for index, path in enumerate(paths, start=1)}
    results: list[ConcurrentPathResult] = []
    covered_path_ids: set[str] = set()

    for relation in parallel_relations:
        relation_paths = [path_by_id[path_id] for path_id in relation.path_ids if path_id in path_by_id]
        if len(relation_paths) < 2:
            continue
        root = normalize_concurrent_tree(build_concurrent_tree_from_paths(relation_paths, relation))
        notation = format_notation(root)
        flat_nodes = flatten_nodes(root)
        results.append(
            ConcurrentPathResult(
                root=root,
                nodes=flat_nodes,
                edges=list(relation.edges),
                data=list(relation.data),
                outputs=list(relation.outputs),
                preconditions=list(relation.preconditions),
                conditions=list(relation.conditions),
                notation=notation,
            )
        )
        covered_path_ids.update(relation.path_ids)

    return results


def format_tree_lines(
    root: ConcurrentPathNode,
    *,
    title: str | None = None,
    indent: str = "",
) -> list[str]:
    """Render a concurrent path as a collapsible tree for the UI."""
    lines: list[str] = []
    header = title or "Concurrent Path"
    lines.append(f"{indent}▼ {header}")

    if root.kind == "sequential":
        for index, child in enumerate(root.children):
            is_last = index == len(root.children) - 1
            lines.extend(_format_tree_child(child, indent + "  ", is_last))
    elif root.kind == "parallel":
        lines.extend(_format_tree_child(root, indent + "  ", True))
    elif root.kind == "node":
        lines.append(f"{indent}  └── {root.label or root.node_id}")

    return lines


def _format_tree_child(child: ConcurrentPathNode, indent: str, is_last: bool) -> list[str]:
    branch = "└──" if is_last else "├──"
    lines: list[str] = []

    if child.kind == "node" and child.node_id:
        lines.append(f"{indent}{branch} {child.label or child.node_id}")
        return lines

    if child.kind == "parallel":
        lines.append(f"{indent}{branch}══▼ PARALLEL BRANCHES")
        parallel_indent = indent + ("    " if is_last else "│   ")
        for branch_index, branch_child in enumerate(child.children):
            branch_is_last = branch_index == len(child.children) - 1
            branch_prefix = "└──" if branch_is_last else "├──"
            if branch_child.kind == "sequential":
                branch_label = _branch_label(branch_child, branch_index)
                lines.append(f"{parallel_indent}{branch_prefix} Branch {branch_label}")
                seq_indent = parallel_indent + ("    " if branch_is_last else "│   ")
                for node_index, node_child in enumerate(branch_child.children):
                    node_is_last = node_index == len(branch_child.children) - 1
                    node_prefix = "└──" if node_is_last else "├──"
                    if node_child.kind == "node" and node_child.node_id:
                        lines.append(f"{seq_indent}{node_prefix} {node_child.label or node_child.node_id}")
            elif branch_child.kind == "node" and branch_child.node_id:
                lines.append(f"{parallel_indent}{branch_prefix} {branch_child.label or branch_child.node_id}")
        return lines

    if child.kind == "sequential":
        for index, grandchild in enumerate(child.children):
            grand_is_last = index == len(child.children) - 1
            lines.extend(_format_tree_child(grandchild, indent, grand_is_last if is_last else False))
        return lines

    return lines


def _branch_label(branch: ConcurrentPathNode, index: int) -> str:
    labels = ["A", "B", "C", "D", "E", "F"]
    letter = labels[index] if index < len(labels) else str(index + 1)
    if branch.children and branch.children[0].kind == "node" and branch.children[0].node_id:
        return f"{letter}: {branch.children[0].node_id}"
    return letter


def _same_atomic_node(left: ConcurrentPathNode, right: ConcurrentPathNode) -> bool:
    return (
        left.kind == "node"
        and right.kind == "node"
        and left.node_id is not None
        and left.node_id == right.node_id
        and left.label == right.label
    )
