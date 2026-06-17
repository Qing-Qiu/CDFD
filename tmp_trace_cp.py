from pathlib import Path
from cdfd.parsers import parse_project
from cdfd.path_finder import _initial_token_states, _expand_token_state

project = parse_project(Path("examples/duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")
g = project.entry()
starts = sorted(g.starts)
initial_states = _initial_token_states(g, starts, project.processes)

target_start = "IN_submissionRequest"
state = next(s for s in initial_states if target_start in s.tokens)
print("From", target_start)

for step in range(40):
    ends_hit = state.tokens & g.ends
    all_ends = g.ends <= state.activated_nodes
    tokens_subset = bool(state.tokens) and state.tokens <= g.ends
    if all_ends or tokens_subset:
        print(f"COMPLETE step {step}: tokens={state.tokens} all_ends={all_ends}")
        break
    nexts = _expand_token_state(g, state, project.processes)
    if not nexts:
        print(f"STUCK step {step}: tokens={state.tokens} activated={sorted(state.activated_nodes)[-5:]}")
        break
    if len(nexts) > 1:
        print(f"step {step} branch {len(nexts)} states")
    state = nexts[0]
    if "separating" in str(state.tokens) or any("P6" in t for t in state.tokens):
        print(f"step {step} at parallel: tokens={state.tokens}")
