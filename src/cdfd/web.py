from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from cdfd.concurrent_paths import (
    build_concurrent_results_from_relations,
    format_tree_lines,
)
from cdfd.consistency import inspect_project_consistency
from cdfd.exporters import (
    concurrent_paths_to_dicts,
    export_analysis,
    graph_to_dict,
    paths_to_dicts,
    project_to_dict,
    render_svg,
    scenarios_to_dicts,
)
from cdfd.models import model_dump
from cdfd.multilevel import detect_project_cycles, find_project_paths
from cdfd.parsers import ParseError, parse_project
from cdfd.path_groups import build_path_relations
from cdfd.path_finder import PathFindingOptions, PathLimitExceeded, find_concurrent_paths
from cdfd.scenarios import build_functional_scenarios


class AnalyzeRequest(BaseModel):
    content: str
    input_format: Literal["json", "cdfd"] = "json"
    start: str | None = None
    ends: str | list[str] | None = None
    strategy: str = "simple"
    max_depth: int = 20
    max_paths: int = 10000
    expand: bool = True


app = FastAPI(title="CDFD Path Generator")
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict[str, object]:
    try:
        project = parse_project(
            payload.content,
            payload.input_format,
            start=payload.start,
            ends=payload.ends,
        )
        graph = project.entry()
        consistency_issues = inspect_project_consistency(project)
        cycles = detect_project_cycles(project)
        paths = find_project_paths(
            project,
            PathFindingOptions(
                strategy=payload.strategy,
                max_depth=payload.max_depth,
                max_paths=payload.max_paths,
            ),
            expand=payload.expand,
        )
        path_relations = build_path_relations(
            paths,
            project=project if payload.expand else None,
            graph=project.entry() if not payload.expand else None,
            graph_name=project.entry_graph if payload.expand else None,
        )
        concurrent_paths = find_concurrent_paths(
            graph,
            PathFindingOptions(
                strategy=payload.strategy,
                max_depth=payload.max_depth,
                max_paths=payload.max_paths,
            ),
            project=project,
        )
        if not concurrent_paths:
            concurrent_paths = build_concurrent_results_from_relations(paths, path_relations)
        concurrent_tree_lines = [
            format_tree_lines(item.root, title=f"Concurrent Path {index}")
            for index, item in enumerate(concurrent_paths, start=1)
        ]
        functional_scenarios = build_functional_scenarios(
            paths,
            project=project,
            concurrent_paths=concurrent_paths,
            path_relations=path_relations,
        )
    except (ParseError, ValueError, PathLimitExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "graph": graph_to_dict(graph),
        "project": project_to_dict(project),
        "consistency_issues": [model_dump(issue) for issue in consistency_issues],
        "cycles": cycles,
        "paths": paths_to_dicts(paths),
        "concurrent_paths": concurrent_paths_to_dicts(
            concurrent_paths,
            tree_lines=concurrent_tree_lines,
        ),
        "functional_scenarios": scenarios_to_dicts(functional_scenarios),
        "path_relations": [
            relation.model_dump() if hasattr(relation, "model_dump") else relation.dict()
            for relation in path_relations
        ],
        "text": export_analysis(
            paths,
            path_relations,
            "text",
            functional_scenarios,
            concurrent_paths,
        ),
        "svg": render_svg(graph, paths, graph_name=project.entry_graph),
        "graph_svgs": {
            name: render_svg(project_graph, paths, graph_name=name)
            for name, project_graph in project.graphs.items()
        },
    }


def main() -> None:
    import uvicorn

    uvicorn.run("cdfd.web:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
