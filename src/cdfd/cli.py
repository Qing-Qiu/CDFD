from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cdfd.consistency import inspect_project_consistency
from cdfd.concurrent_paths import build_concurrent_results_from_relations
from cdfd.exporters import export_analysis
from cdfd.multilevel import detect_project_cycles, find_project_paths
from cdfd.parsers import ParseError, infer_format, parse_project
from cdfd.path_groups import build_path_relations
from cdfd.path_finder import PathFindingOptions, PathLimitExceeded, find_concurrent_paths
from cdfd.scenarios import build_functional_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        input_path = Path(args.input)
        input_format = infer_format(input_path) if args.format == "auto" else args.format
        content = input_path.read_text(encoding="utf-8")
        project = parse_project(content, input_format, start=args.start, ends=args.ends)
        consistency_issues = inspect_project_consistency(project)
        cycles = detect_project_cycles(project)
        paths = find_project_paths(
            project,
            PathFindingOptions(
                strategy=args.strategy,
                max_depth=args.max_depth,
                max_paths=args.max_paths,
            ),
            expand=not args.no_expand,
        )
        path_relations = build_path_relations(
            paths,
            project=project if not args.no_expand else None,
            graph=project.entry() if args.no_expand else None,
            graph_name=project.entry_graph if not args.no_expand else None,
        )
        concurrent_paths = find_concurrent_paths(
            project.entry(),
            PathFindingOptions(
                strategy=args.strategy,
                max_depth=args.max_depth,
                max_paths=args.max_paths,
            ),
            project=project,
        )
        if not concurrent_paths:
            concurrent_paths = build_concurrent_results_from_relations(paths, path_relations)
        functional_scenarios = build_functional_scenarios(
            paths,
            project=project,
            concurrent_paths=concurrent_paths,
            path_relations=path_relations,
        )
        if consistency_issues:
            _print_consistency_issues(consistency_issues)
        if cycles:
            _print_cycles(cycles)
        print(
            export_analysis(
                paths,
                path_relations,
                args.output_format,
                functional_scenarios,
                concurrent_paths,
            )
        )
        return 0
    except (OSError, ParseError, ValueError, PathLimitExceeded) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate all paths for a CDFD graph.")
    parser.add_argument("input", help="Input CDFD file.")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "json", "cdfd"],
        help="Input format. Defaults to auto by file extension.",
    )
    parser.add_argument("--start", help="Optional start node override.")
    parser.add_argument(
        "--end",
        dest="ends",
        action="append",
        help="Optional end node override. Can be repeated.",
    )
    parser.add_argument(
        "--strategy",
        choices=["simple", "max-depth"],
        default="simple",
        help="Cycle handling strategy.",
    )
    parser.add_argument("--max-depth", type=int, default=20, help="Maximum edge depth for max-depth strategy.")
    parser.add_argument("--max-paths", type=int, default=10000, help="Safety limit for generated paths.")
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="For project inputs, keep decomposable processes as top-level nodes.",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "csv", "markdown"],
        default="text",
        help="Output format.",
    )
    return parser


def _print_cycles(cycles: dict[str, list[list[str]]]) -> None:
    total = sum(len(graph_cycles) for graph_cycles in cycles.values())
    print(f"Warning: {total} cycle(s) detected.", file=sys.stderr)
    for graph_name, graph_cycles in cycles.items():
        for cycle in graph_cycles:
            print(f"  {graph_name}: {' -> '.join(cycle)}", file=sys.stderr)


def _print_consistency_issues(issues) -> None:
    print(f"Warning: {len(issues)} CDFD consistency issue(s) detected.", file=sys.stderr)
    for issue in issues:
        print(f"  {issue.id} [{issue.rule}]: {issue.message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
