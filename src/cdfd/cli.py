from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cdfd.exporters import export_paths
from cdfd.parsers import ParseError, infer_format, parse_cdfd
from cdfd.path_finder import PathFindingOptions, PathLimitExceeded, detect_cycles, find_paths


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        input_path = Path(args.input)
        input_format = infer_format(input_path) if args.format == "auto" else args.format
        content = input_path.read_text(encoding="utf-8")
        graph = parse_cdfd(content, input_format, start=args.start, ends=args.ends)
        cycles = detect_cycles(graph)
        paths = find_paths(
            graph,
            PathFindingOptions(
                strategy=args.strategy,
                max_depth=args.max_depth,
                max_paths=args.max_paths,
            ),
        )
        if cycles:
            _print_cycles(cycles)
        print(export_paths(paths, args.output_format))
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
        choices=["auto", "json", "yaml", "yml", "csv"],
        help="Input format. Defaults to auto by file extension.",
    )
    parser.add_argument("--start", help="Start node override. Required for CSV.")
    parser.add_argument(
        "--end",
        dest="ends",
        action="append",
        help="End node. Can be repeated. Required for CSV.",
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
        "--output-format",
        choices=["text", "json", "csv", "markdown"],
        default="text",
        help="Output format.",
    )
    return parser


def _print_cycles(cycles: list[list[str]]) -> None:
    print(f"Warning: {len(cycles)} cycle(s) detected.", file=sys.stderr)
    for cycle in cycles:
        print(f"  {' -> '.join(cycle)}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
