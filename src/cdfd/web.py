from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from cdfd.exporters import export_paths, graph_to_dict, render_svg
from cdfd.parsers import ParseError, parse_cdfd
from cdfd.path_finder import PathFindingOptions, PathLimitExceeded, detect_cycles, find_paths


class AnalyzeRequest(BaseModel):
    content: str
    input_format: str = "json"
    start: str | None = None
    ends: str | list[str] | None = None
    strategy: str = "simple"
    max_depth: int = 20
    max_paths: int = 10000


app = FastAPI(title="CDFD Path Generator")
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict[str, object]:
    try:
        graph = parse_cdfd(
            payload.content,
            payload.input_format,
            start=payload.start,
            ends=payload.ends,
        )
        cycles = detect_cycles(graph)
        paths = find_paths(
            graph,
            PathFindingOptions(
                strategy=payload.strategy,
                max_depth=payload.max_depth,
                max_paths=payload.max_paths,
            ),
        )
    except (ParseError, ValueError, PathLimitExceeded) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "graph": graph_to_dict(graph),
        "cycles": cycles,
        "paths": [path.model_dump() if hasattr(path, "model_dump") else path.dict() for path in paths],
        "text": export_paths(paths, "text"),
        "svg": render_svg(graph, paths),
    }


def main() -> None:
    import uvicorn

    uvicorn.run("cdfd.web:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
