# CDFD Path Generator

A small Python tool for generating all paths for a given CDFD.

The project supports:

- JSON, YAML, and CSV inputs
- CLI path generation
- FastAPI web UI
- simple-path cycle handling
- max-depth cycle handling
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
    { "id": "e1", "from": "A", "to": "B" },
    { "id": "e2", "from": "B", "to": "D", "condition": "ok" }
  ]
}
```

CSV inputs are edge lists and require `--start` and `--end`:

```csv
from,to,condition
A,B,
B,D,ok
```

## Cycle Strategies

- `simple`: a path may not visit the same node twice.
- `max-depth`: a path may revisit nodes, but the number of traversed edges is capped by `--max-depth`.
