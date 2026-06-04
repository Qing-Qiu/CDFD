# CDFD Path Generator

A small Python tool for generating all paths for a given CDFD.

The project supports:

- JSON, YAML, and CSV inputs
- CLI path generation
- FastAPI web UI
- simple-path cycle handling
- max-depth cycle handling
- multi-level CDFD process decomposition
- data-flow labels such as `x1`, `x6`, `y1`, and state/precondition labels such as `s1`
- path groups for joined outputs and parallel independent flows
- text, JSON, CSV, and Markdown outputs

## Install

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

## CLI

Generate paths from JSON:

```bash
cdfd-paths examples/simple.json
```

If console scripts are not on your PATH, use:

```bash
python -m cdfd.cli examples/simple.json
```

Generate paths from YAML:

```bash
cdfd-paths examples/branch.yaml --output-format markdown
```

Generate bounded cyclic paths from CSV:

```bash
cdfd-paths examples/loop.csv --start A --end C --strategy max-depth --max-depth 4
```

For acyclic graphs, start and end nodes can be auto-detected:

```bash
cdfd-paths examples/linear.csv
```

Provide `--start` or `--end` when the graph has cycles, multiple possible starts, or a non-standard entry/exit.

Generate expanded paths from a multi-level CDFD project:

```bash
cdfd-paths examples/multilevel.json
```

Keep only the top-level CDFD path:

```bash
cdfd-paths examples/multilevel.json --no-expand
```

## Web UI

```bash
cdfd-web
```

Or:

```bash
python -m cdfd.web
```

Then open:

```text
http://127.0.0.1:8000
```

## Input Model

JSON and YAML inputs use this structure:

```json
{
  "start": "A",
  "ends": ["D"],
  "nodes": [
    { "id": "A", "type": "start" },
    { "id": "B", "type": "process" },
    { "id": "D", "type": "end" }
  ],
  "edges": [
    { "id": "e1", "from": "A", "to": "B", "data": ["x1"] },
    { "id": "e2", "from": "B", "to": "D", "data": ["x2"], "condition": "ok" }
  ]
}
```

CSV inputs are edge lists. `start` and `ends` are auto-detected when the graph has one source-only node and at least one sink node:

```csv
from,to,data,condition
A,B,x1,
B,D,x2,ok
```

Use `data` for CDFD data-flow labels (`x1`, `x6`, `y1`, `z2`). Use `condition` for guards or control conditions. Process-level `pre` and `post` describe preconditions and input/output relationships, such as `s1 == 1`.

State/control labels such as `s1` and `s2` can be shown in the graph as `state` nodes connected by `control` edges:

```json
{
  "nodes": [
    { "id": "S1", "type": "state", "label": "1 s1" },
    { "id": "A1", "type": "process" }
  ],
  "edges": [
    { "from": "S1", "to": "A1", "kind": "control", "condition": "s1 == 1" }
  ]
}
```

The Web visualization draws `control` edges as dashed arrows.

Text output renders paths as data-flow transitions when every edge has one data label:

```text
IN --[x1]--> A1 --[x2]--> A2 --[x4]--> A4 --[x6]--> OUT_X6
```

For expanded multi-level paths, process preconditions are shown separately:

```text
Preconditions: A1: s1 == 1; A33: s2 == 2
```

## Path Semantics

The tool reports two related result types:

- **Linear paths** are single source-to-sink traces through the CDFD graph. They are useful for checking every reachable data-flow route.
- **Path groups** are semantic bundles of linear paths. A `joined-output` group means several compatible branches feed the same output slice. A `parallel` group means two paths share a prefix and then continue through disjoint downstream nodes/data without conflicting conditions.

This distinction matters because CDFD branches are not always choices. For example, if two branches both feed process `A4` before output `x6`, those branches are part of one output computation, not two mutually exclusive executions.

## Cycle Strategies

- `simple`: a path may not visit the same node twice.
- `max-depth`: a path may revisit nodes, but the number of traversed edges is capped by `--max-depth`.

## Multi-Level CDFD

JSON and YAML can also describe a full CDFD project:

```json
{
  "module": {
    "name": "ExampleModule",
    "behav": "Top"
  },
  "processes": [
    { "id": "A1", "pre": "s1 == 1", "post": "x2 is derived from x1", "decom": "A1_detail" }
  ],
  "graphs": {
    "Top": {
      "start": "A1",
      "ends": ["A2"],
      "nodes": ["A1", "A2"],
      "edges": [{ "from": "A1", "to": "A2", "data": ["x2"] }]
    },
    "A1_detail": {
      "start": "A11",
      "ends": ["A12"],
      "nodes": ["A11", "A12"],
      "edges": [{ "from": "A11", "to": "A12", "data": ["y1"] }]
    }
  }
}
```

`module.behav` selects the top-level CDFD. Each `process.decom` points to another graph. By default, the generator recursively replaces decomposed processes with paths from their child CDFD.

The Web UI includes a graph-layer selector so each CDFD layer can be inspected separately.

When a decomposed process has multiple child exits, graph metadata can map child end nodes to parent-level output data. This prevents invalid combinations such as using an `x7` child exit on an `x5` parent edge:

```json
{
  "metadata": {
    "outputs": {
      "A32": ["x5"],
      "A33": ["x7"]
    }
  }
}
```

## Project File Checklist

For a complete CDFD project file, include:

- `module`: constants, types, variables, and `behav` entry graph when known.
- `processes`: each process id, optional `pre`/`post`, and optional `decom` target graph.
- `graphs`: every CDFD layer, including the top layer and decomposed process layers.
- graph `nodes`: process, external, state, or other node types needed for display and analysis.
- graph `edges`: `from`, `to`, optional `data`, optional `condition`, and `kind: "control"` for state/precondition arrows.
- graph `metadata.outputs`: child end-node to parent output-data mapping when a decomposed process has multiple exits.

Unknown extra fields are preserved in metadata, so the format can be extended later with stricter branch semantics when the course examples need them.
