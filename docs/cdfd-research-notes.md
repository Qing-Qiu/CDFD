# CDFD Research Notes

This project follows the SOFL meaning of CDFD: **Condition Data Flow Diagram**.

The online material we used points to the same core model:

- SOFL specifications are built from CDFDs and modules. A CDFD describes the architecture by connecting processes, data flows, and data stores, while the module defines the related declarations and process specifications.
- A condition process has named input/output data flows plus preconditions and postconditions.
- Process decomposition maps a process in one CDFD to a lower-level CDFD.
- SOFL CDFD data flows may be simple flows or connector-style flows such as broadcast and choice. We model these connector semantics with explicit `structures`, and infer a conservative subset when topology proves independence.
- Functional scenarios can be derived from CDFDs. In the sources, they are used as inspection or animation units that describe how input data is transformed into output data through the process specifications involved in a data-flow path.

References:

- [An Object Semantic Model of SOFL](https://www.researchgate.net/publication/2504427_An_Object_Semantic_Model_of_SOFL)
- [A Formal Framework for Formal Specifications Review](https://www.jstage.jst.go.jp/article/jssstconference/21/0/21_0_58/_pdf/-char/ja)
- [IPA SOFL report](https://www.ipa.go.jp/archive/files/000026803.pdf)
- [Automatically Generating Functional Scenarios from SOFL CDFD for Specification Inspection](https://www.researchgate.net/publication/266631542_Automatically_Generating_Functional_Scenarios_from_SOFL_CDFD_for_Specification_Inspection)
- [Integrating top-down and scenario-based methods for constructing software specifications](https://www.sciencedirect.com/science/article/abs/pii/S0950584909000986)
- [A Systematic Inspection Approach to Verifying and Validating Formal Specifications based on Specification Animation and Traceability](https://123deta.com/document/yevk57er-systematic-inspection-verifying-validating-specifications-specification-animation-traceability.html)

## Project Decisions

1. Keep JSON as the project input format.
   The JSON file represents the SOFL-style package: module declarations, process specifications, graph layers, decomposition links, data/control flows, and explicit structures.

2. Treat paths as atomic data-flow traces.
   A path is a source-to-sink trace through CDFD data-flow edges. Control/state edges are kept as conditions on the target process, not as path segments. Parallel, choice, and join semantics are represented separately as `path_relations`.

   For inferred parallelism, relations are maximal mutually independent path sets rather than only pairwise combinations. This matches the data-flow view: independent branches can be considered parallel while each atomic path remains a separate source-to-sink trace.

3. Keep paths and functional scenarios separate.
   The tool now reports both layers. `paths` remain raw graph traces. `functional_scenarios` wrap those paths with process specifications, input/output data, preconditions, and postconditions so they can be used as inspection-oriented units.

4. Check CDFD-module consistency.
   The review literature says syntax-related consistency between a CDFD and its module can be checked automatically. We therefore report warnings when:

- a process node has no process specification;
- a process specification is not used by any graph node;
- a process specification's inputs or outputs differ from the graph data flows;
- a graph edge uses a data flow not declared in `module.var`;
- a data store has no data-flow connection.

These checks are warnings rather than hard failures because early-stage CDFD models are often incomplete. Schema errors still fail fast because they mean the file does not match the agreed JSON format.
