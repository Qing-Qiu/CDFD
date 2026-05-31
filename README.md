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
