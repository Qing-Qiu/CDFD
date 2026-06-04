# CDFD JSON Format v1

This project currently accepts CDFD input as JSON. A valid file describes one CDFD project: module data, process specifications, graph layers, data/control flows, and explicit CDFD structures.

The machine-readable schema is [cdfd-json-schema.json](cdfd-json-schema.json). JSON project input is validated against this schema before path generation. See [cdfd-research-notes.md](cdfd-research-notes.md) for the SOFL/CDFD references that guide this format.

## Path Definition

A path is a directed trace from a graph input/source node to an output/sink node through CDFD edges. It is an atomic data-flow trace, not a full functional scenario.

The generator reports:

- `paths`: individual source-to-sink traces.
- `path_relations`: relationships between paths, such as `parallel`, `exclusive`, or `joined-output`.

Parallel paths remain separate paths. The relation records that they can be considered independent or simultaneous. A future functional-scenario layer can combine paths and relations, but this JSON output keeps those concepts separate.

Each path in JSON output includes:

- `id`: stable display id such as `P1`.
- `source` and `sink`: the first and last node in the trace.
- `route`: human-readable route with data labels.
- `nodes`, `edges`, `data`, `outputs`, `preconditions`, and `conditions`: structured path details.

## Top-Level Object

```json
{
  "schema_version": "cdfd-json-v1",
  "module": {},
  "processes": [],
  "graphs": {}
}
```

Fields:

- `schema_version`: required value `cdfd-json-v1`.
- `module`: constants, types, variables, and entry CDFD.
- `processes`: formal process specifications.
- `graphs`: named CDFD layers.

## Module

```json
{
  "name": "ExampleModule",
  "const": ["s1 = 1"],
  "type": ["int", "real"],
  "var": ["x1", "x2"],
  "behav": "Top"
}
```

`behav` selects the top-level graph when `entry_graph` is not supplied.

## Process

```json
{
  "id": "A1",
  "inputs": ["x1"],
  "outputs": ["x2", "x3"],
  "pre": "s1 == 1",
  "post": "x2 and x3 are derived from x1",
  "decom": "A1_detail"
}
```

`decom` points to a graph that decomposes the process. When omitted, the process is treated as atomic.

## Graph

```json
{
  "starts": ["IN"],
  "ends": ["OUT_X6"],
  "nodes": [],
  "edges": [],
  "structures": []
}
```

Use `start` for a single source and `starts` for multiple sources. For example, a process may depend on both an external input and a data store. `start`/`starts` and `ends` can be inferred for simple acyclic graphs, but explicit values are preferred for CDFD project files.

## Node

```json
{ "id": "A1", "type": "process", "label": "A1" }
```

Common node types:

- `process`: a CDFD process.
- `external`: input/output environment.
- `data_store`: persistent data store.
- `state`: state or condition store such as `1 s1`.
- `connector`: control/data-flow helper node.

## Edge

```json
{
  "id": "e1",
  "from": "A1",
  "to": "A2",
  "kind": "flow",
  "data": ["x2"],
  "condition": "x2 is available"
}
```

`kind` values:

- `flow`: normal active data flow.
- `control`: control or state condition flow, rendered as dashed in the Web UI.
- `shadow`: placeholder flow carrying presence/absence information.

## Structure

Use `structures` when the graph has semantics that cannot be safely inferred from topology.

```json
{
  "id": "par_A",
  "kind": "parallel",
  "source": "A",
  "branches": [
    { "id": "x4_branch", "edges": ["e2", "e4"] },
    { "id": "x5_branch", "edges": ["e3", "e5"] }
  ]
}
```

Supported structure kinds:

- `parallel`, `broadcast`, `fork`, `separate`: branches can be related as parallel paths.
- `choice`, `condition`, `select`, `non-determinism`: branches are alternatives, not parallel.
- `join`, `merge`: branches feed the same output or downstream process.

Each branch can match paths by `edges`, `nodes`, `data`, `source`, `target`, or `condition`.

## Consistency Checks

After schema validation, the tool reports CDFD-module consistency warnings. These warnings are based on the SOFL idea that a CDFD and its associated module should describe the same processes, data flows, and stores.

Current warnings include:

- process nodes without process specifications;
- process specifications that are not used in any CDFD graph;
- process input/output lists that do not match graph data flows;
- data flows that are not declared in `module.var`;
- disconnected data stores.

## Minimal Complete Example

See [examples/cdfd_v1.json](../examples/cdfd_v1.json).

## Multi-Level Lecture Example

See [examples/multilevel.json](../examples/multilevel.json) for a CDFD with:

- top-level processes `A1`, `A2`, `A3`, and `A4`;
- process decomposition graphs `A1_detail`, `A3_detail`, and `A33_detail`;
- state/control nodes `s1` and `s2`;
- data labels such as `x1`, `x6`, `x7`, `y1`, `z2`, `d1`, and `d2`;
- explicit `join`, `parallel`, and `choice` structures.
