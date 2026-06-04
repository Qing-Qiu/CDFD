# CDFD Path Generator

A Python tool for generating paths from a CDFD JSON file.

CDFD means **Condition Data Flow Diagram**. In this project, a CDFD file contains the module, processes, graph layers, data/control flows, and explicit structures needed to generate paths automatically.

## Current Scope

- JSON input as the project format
- CLI path generation
- FastAPI web UI
- simple-path cycle handling
- max-depth cycle handling
- multi-level process decomposition
- data-flow labels such as `x1`, `x6`, `y1`, and state/precondition labels such as `s1`
- path relations for parallel, exclusive, and joined-output paths
- text, JSON, CSV, and Markdown outputs

YAML and CSV parser helpers still exist for older examples, but the project format for the assignment is JSON. See [docs/cdfd-json-format.md](docs/cdfd-json-format.md).

The machine-readable schema is [docs/cdfd-json-schema.json](docs/cdfd-json-schema.json). JSON project input is validated against this schema before path generation.

Research notes and SOFL/CDFD alignment decisions are in [docs/cdfd-research-notes.md](docs/cdfd-research-notes.md).

## Install

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

## CLI

Generate paths from the canonical JSON example:

```bash
python -m cdfd.cli examples/cdfd_v1.json
```

Other JSON examples:

```bash
python -m cdfd.cli examples/choice.json
python -m cdfd.cli examples/join.json
python -m cdfd.cli examples/data_store.json
python -m cdfd.cli examples/multilevel.json
```

Generate expanded paths from a multi-level CDFD:

```bash
python -m cdfd.cli examples/multilevel.json
```

Output JSON analysis:

```bash
python -m cdfd.cli examples/cdfd_v1.json --output-format json
```

JSON output gives each path a display id and endpoints:

```json
{
  "id": "P1",
  "source": "IN",
  "sink": "OUT_X6",
  "route": "IN --[x1]--> A --[x6]--> OUT_X6"
}
```

For graphs with cycles, use bounded traversal:

```bash
python -m cdfd.cli examples/loop.csv --start A --end C --strategy max-depth --max-depth 4
```

## Web UI

```bash
python -m cdfd.web
```

Then open:

```text
http://127.0.0.1:8000
```

The web UI accepts JSON files and shows:

- linear paths
- path relations
- CDFD-module consistency warnings
- graph layer visualization

## Path Definition

A **path** is a directed trace from a CDFD input/source node to an output/sink node through data/control-flow edges.

Example:

```text
IN --[x1]--> A --[x2]--> B --[x4]--> OUT_X4
```

Parallel paths are still separate paths. The relation between them is reported separately:

```text
R1 (parallel): P1 || P2
```

This keeps `paths` and functional scenarios separate. The tool currently generates atomic paths plus path relations, not full functional scenarios.

## JSON Format

Minimal project shape:

```json
{
  "schema_version": "cdfd-json-v1",
  "module": {
    "name": "ExampleModule",
    "behav": "Top"
  },
  "processes": [
    {
      "id": "A",
      "inputs": ["x1"],
      "outputs": ["x2", "x3"],
      "pre": "x1 is available",
      "post": "x2 and x3 are derived from x1"
    }
  ],
  "graphs": {
    "Top": {
      "starts": ["IN"],
      "ends": ["OUT_X4", "OUT_X5"],
      "nodes": [
        { "id": "IN", "type": "external" },
        { "id": "A", "type": "process" },
        { "id": "B", "type": "process" },
        { "id": "C", "type": "process" },
        { "id": "OUT_X4", "type": "external" },
        { "id": "OUT_X5", "type": "external" }
      ],
      "edges": [
        { "id": "e1", "from": "IN", "to": "A", "data": ["x1"] },
        { "id": "e2", "from": "A", "to": "B", "data": ["x2"] },
        { "id": "e3", "from": "A", "to": "C", "data": ["x3"] },
        { "id": "e4", "from": "B", "to": "OUT_X4", "data": ["x4"] },
        { "id": "e5", "from": "C", "to": "OUT_X5", "data": ["x5"] }
      ],
      "structures": [
        {
          "id": "par_A",
          "kind": "parallel",
          "source": "A",
          "branches": [
            { "id": "x4_branch", "edges": ["e2", "e4"] },
            { "id": "x5_branch", "edges": ["e3", "e5"] }
          ]
        }
      ]
    }
  }
}
```

Use `structures` to distinguish branches that cannot be safely inferred from topology:

- `parallel`: paths can be related as independent/parallel.
- `choice`: paths are alternatives, not parallel.
- `join`: paths feed the same output or downstream process.

Use `starts` instead of `start` when the graph has multiple sources, such as an external input and a data store.

## Consistency Warnings

Schema validation checks whether the file has the right JSON shape. Consistency warnings check whether the CDFD and module agree with each other: process specs should match graph input/output flows, data flows should be declared in `module.var`, process nodes should have process specs, and data stores should be connected.

## Multi-Level CDFD

Each `process.decom` points to another graph:

```json
{
  "processes": [
    { "id": "A1", "decom": "A1_detail" }
  ],
  "graphs": {
    "Top": {},
    "A1_detail": {}
  }
}
```

By default, the generator recursively replaces decomposed processes with child CDFD paths.

When a decomposed process has multiple child exits, graph metadata can map child end nodes to parent output data:

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

## Verification

```bash
python -m pytest
```
