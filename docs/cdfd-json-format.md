# CDFD JSON Format v1

This project uses JSON as its canonical CDFD project format. A valid file describes one CDFD project: module data, process specifications, graph layers, data/control flows, and explicit CDFD structures.

The parser can also import SOFL tool `.cdfd` XML files. Those files are converted into the same internal graph/project model before path generation. JSON remains the documented exchange format because it can carry the complete module/process/decomposition data in one file.

These are the only supported input formats. YAML and CSV are intentionally not accepted: YAML duplicates the JSON contract, while a CSV edge list cannot represent complete multi-level CDFD semantics such as modules, process decomposition, control conditions, and explicit parallel/choice/join structures.

The machine-readable schema is [cdfd-json-schema.json](cdfd-json-schema.json). JSON project input is validated against this schema before path generation. See [cdfd-research-notes.md](cdfd-research-notes.md) for the SOFL/CDFD references that guide this format.

## Path Definition

A path is not restricted to a plain list of graph nodes. The project uses two related layers:

- `paths`: atomic source-to-sink traces through CDFD data-flow edges.
- `concurrent_paths`: structured paths whose root is a tree built from `node`, `sequential`, and `parallel` elements.

The structured notation is:

```text
C ::= node | C -> C | [ C || ... || C ] | C XOR C
```

Linear paths are projections of this structured path model. Control/state edges are not path segments; they contribute conditions to the path when they point to a process on that path.

The generator reports:

- `paths`: individual source-to-sink traces.
- `concurrent_paths`: structured path trees for fork/join and synchronized multi-input cases.
- `path_relations`: relationships between paths, such as `parallel`, `exclusive`, or `joined-output`.
- `functional_scenarios`: inspection-oriented units derived from paths and process specifications.

Parallel paths remain separate atomic paths, while `concurrent_paths` can also express the same behavior as one structured path. When the generator infers parallelism from topology, it reports the largest mutually independent path sets it can prove, so three independent branches are shown as one relation instead of three pairwise relations. Functional scenarios keep a separate layer: each scenario references one or more path ids and adds process-specification context.

Relation display symbols:

- `P1 || P2`: parallel paths that can be considered independent.
- `P1 XOR P2`: exclusive alternatives.
- `P1 + P2`: joined-output paths that feed the same downstream output.

Each path in JSON output includes:

- `id`: stable display id such as `P1`.
- `source` and `sink`: the first and last node in the trace.
- `route`: human-readable route with data labels.
- `nodes`, `edges`, `data`, `outputs`, `preconditions`, and `conditions`: structured path details.

Each functional scenario includes:

- `id`: stable display id such as `FS1`.
- `path_ids`: the path or paths the scenario is derived from.
- `input_data` and `output_data`: the input/output relation being inspected.
- `operations`: process specifications involved in the scenario.
- `preconditions`, `postconditions`, and `conditions`: formal or semi-formal constraints collected from the process specs and path.

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
  "input_ports": [
    { "id": "default", "data": ["x1"] }
  ],
  "output_ports": [
    { "id": "x2_port", "data": ["x2"] },
    { "id": "x3_port", "data": ["x3"] }
  ],
  "pre": "s1 == 1",
  "post": "x2 and x3 are derived from x1",
  "decom": "A1_detail"
}
```

`decom` points to a graph that decomposes the process. When omitted, the process is treated as atomic.

`inputs` and `outputs` are compact process-level declarations. Use `input_ports` and `output_ports` when the CDFD must distinguish process interfaces:

- items inside one input port are combined with AND semantics;
- multiple input ports are mutually exclusive alternatives unless a process specification explicitly models a different policy;
- multiple output ports are choices by default;
- edges listed in the same output port belong to one selected interface and may be produced together;
- use a graph `structure` such as `parallel` or `fork` when branches from different output ports really fire together.

An input port may set `"mode": "any"` if one data item in that port is enough to activate it. The default is `"all"`, which is the normal CDFD interpretation for a port containing multiple required data items.

For example, a login process may accept either `{userAccount, passWord}` or `{token}`:

```json
{
  "id": "Login",
  "input_ports": [
    { "id": "password", "data": ["userAccount", "passWord"] },
    { "id": "token", "data": ["token"] }
  ],
  "output_ports": [
    { "id": "result", "data": ["loginResult"] }
  ]
}
```

This means `userAccount` alone is not enough, while `token` alone can activate the process through a different port.

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

Use `start` for a single source and `starts` for multiple sources. For example, a process may depend on both an external input and a data store. `start`/`starts` and `ends` can be inferred for simple acyclic graphs, but explicit values are preferred for CDFD project files. Automatic inference uses data-flow edges only, so state/control nodes such as `s1` are not treated as path starts.

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
- `single_condition`, `multiple_condition`, `binary_condition`: conditional CDFD structures.
- `broadcasting`, `separating`, `merging`, `connecting`, `nondeterministic`, `renaming`: SOFL CDFD structure nodes used by the desktop SOFL tool.

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
- `active-flow`: SOFL active data flow imported from `.cdfd` XML. It is traversed like a data-flow path edge.
- `control`: control or state condition flow, rendered as dashed in the Web UI and collected as a path condition rather than traversed as a path edge.
- `shadow`: placeholder flow carrying presence/absence information.

## SOFL `.cdfd` Import

SOFL desktop `.cdfd` files use XML with this shape:

```xml
<CDFD module="xuexitong">
  <componentList>...</componentList>
  <connectionList>...</connectionList>
</CDFD>
```

The importer maps SOFL components to JSON-equivalent node types:

- `process` -> `process`
- `dataStore` -> `data_store`
- `singleCondition`, `multipleCondition`, `binaryCondition` -> condition nodes
- `broadcasting`, `separating`, `merging`, `connecting`, `nondeterministic`, `renaming` -> CDFD structure nodes

Connection mapping:

- `dataFlow` -> `flow`
- `activeDataFlow` -> `active-flow`
- `controlDataFlow` -> `control`

The SOFL tool sometimes stores a visible line as `outSide -> outSide` even when its coordinates touch a component. The importer therefore first uses explicit `shapeIndex`/component names, then falls back to coordinate-based endpoint inference. This preserves realistic SOFL drawings such as [examples/xuexitong.cdfd](../examples/xuexitong.cdfd).

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
