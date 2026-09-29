import os
import dotenv
import asyncio
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from langgraph.errors import GraphDrained
from langgraph.runtime import RunControl
from langgraph.types import Command
from pydantic import AfterValidator, BaseModel, Field

from app.graph import graph
from app.llm import ModelSelection, reset_selection, use_selection

dotenv.load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS = Path(os.environ.get("DEEP_RESEARCH_REPORTS", Path(__file__).resolve().parent / "reports"))
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}/[A-Za-z0-9][A-Za-z0-9._:@+-]{0,160}$")
MODELS_URL = "https://openrouter.ai/api/v1/models"
KEY_URL = "https://openrouter.ai/api/v1/key"
_models_cache: tuple[float, list["CatalogModel"]] | None = None
_runs: dict[str, RunControl] = {}
_aborted: set[str] = set()
_runs_lock = threading.Lock()


def require_api_key(value: str) -> str:
    value = value.strip()
    if len(value) < 8 or len(value) > 300 or any(character.isspace() for character in value):
        raise ValueError("That isn't an OpenRouter API key")
    return value


def require_model(value: str) -> str:
    value = value.strip()
    if not MODEL_ID.fullmatch(value):
        raise ValueError("Choose an OpenRouter model")
    return value


ApiKey = Annotated[str, AfterValidator(require_api_key)]
ModelId = Annotated[str, AfterValidator(require_model)]


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1)
    api_key: ApiKey
    planner_model: ModelId
    extractor_model: ModelId
    writer_model: ModelId
    thread_id: str = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1, le=10)

class ResumeRequest(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=7)
    api_key: ApiKey
    planner_model: ModelId
    extractor_model: ModelId
    writer_model: ModelId

class KeyCheck(BaseModel):
    api_key: ApiKey


class CatalogModel(BaseModel):
    id: str
    name: str
    tools: bool


class ReportSummary(BaseModel):
    slug: str
    title: str
    updated_at: datetime


def initial_state(topic: str, max_iterations: int) -> dict:
    return {
        "topic": topic,
        "gaps": [],
        "findings": [],
        "additional_info": [],
        "research_loops": 0,
        "final_report": "",
        "hits": [],
        "dead_urls": [],
        "blocked_domains": [],
        "max_iterations": max_iterations,
    }


def slugify(topic: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in topic).strip("-")


def valid_slug(slug: str) -> bool:
    return bool(slug) and slug.replace("-", "").isalnum()


def report_title(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    return path.stem.replace("-", " ")


def save_report(report: str, topic: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)
    if not valid_slug(slug):
        raise ValueError("Topic did not produce a report filename")
    path = REPORTS / f"{slug}.md"
    path.write_text(report.strip() + "\n", encoding="utf-8")
    return path


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def begin_run(thread_id: str) -> RunControl:
    control = RunControl()
    with _runs_lock:
        _runs[thread_id] = control
        if thread_id in _aborted:
            control.request_drain("abort")
    return control


def end_run(thread_id: str, control: RunControl) -> None:
    with _runs_lock:
        if _runs.get(thread_id) is control:
            _runs.pop(thread_id, None)


def request_abort(thread_id: str) -> None:
    with _runs_lock:
        _aborted.add(thread_id)
        control = _runs.get(thread_id)
    if control is not None:
        control.request_drain("abort")


def run_aborted(thread_id: str) -> bool:
    with _runs_lock:
        return thread_id in _aborted


def publish(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, event: dict | None) -> None:
    loop.call_soon_threadsafe(queue.put_nowait, event)


def drive(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, chunks, api_key: str) -> str | None:
    report = ""
    try:
        for chunk in chunks:
            for node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                for event in events_from(node, update):
                    if event["type"] == "report":
                        report = event["markdown"]
                    publish(loop, queue, event)
    except GraphDrained:
        publish(loop, queue, {"type": "aborted"})
        return None
    except Exception as exc:
        publish(loop, queue, {"type": "error", "message": public_error(exc, api_key)})
        return None
    return report


def public_error(exc: Exception, api_key: str) -> str:
    message = str(exc).strip() or "Research failed"
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:500]


def openrouter_json(url: str, api_key: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="OpenRouter rejected that key") from None
        raise HTTPException(status_code=502, detail="Could not reach OpenRouter") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="Could not reach OpenRouter") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Could not reach OpenRouter")
    return payload


def catalog_models() -> list[CatalogModel]:
    global _models_cache
    cached = _models_cache
    now = time.monotonic()
    if cached is not None and now - cached[0] < 600:
        return cached[1]

    payload = openrouter_json(MODELS_URL)
    models: list[CatalogModel] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
            continue
        architecture = item.get("architecture")
        modalities = architecture.get("output_modalities") if isinstance(architecture, dict) else []
        if not isinstance(modalities, list) or "text" not in modalities:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            name = model_id
        parameters = item.get("supported_parameters")
        if not isinstance(parameters, list):
            parameters = []
        models.append(CatalogModel(id=model_id, name=name.strip(), tools="tools" in parameters))
    models.sort(key=lambda model: model.name.casefold())
    _models_cache = (now, models)
    return models


def events_from(node: str, update: dict) -> list[dict]:
    if node == "generate_gaps":
        return [{"type": "gaps", "questions": [gap.question for gap in update["gaps"]]}]

    if node == "search":
        hits = update.get("hits", [])
        if not hits:
            return []
        return [{
            "type": "search",
            "gap_id": hits[0].gap_id,
            "urls": [hit.url for hit in hits],
        }]

    if node == "scrape":
        events = [
            {
                "type": "finding",
                "gap_id": finding.gap_id,
                "source": finding.source,
                "answers": finding.answers_gap,
                "note": finding.note,
            }
            for finding in update.get("findings", [])
        ]
        events.extend({"type": "dead_url", "url": url} for url in update.get("dead_urls", []))
        return events

    if node == "update_checklist":
        return [
            {
                "type": "gap",
                "id": gap.id,
                "question": gap.question,
                "status": gap.status,
                "missing": gap.missing,
            }
            for gap in update["gaps"]
        ]

    if node == "write_final_report":
        return [{"type": "report", "markdown": update["final_report"]}]

    return []


def finish_stream(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    thread_id: str,
    report: str | None,
    topic: str,
) -> None:
    if report is None or run_aborted(thread_id):
        return
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if snapshot.next:
        publish(loop, queue, {
            "type": "review",
            "thread_id": thread_id,
            "questions": [gap.question for gap in snapshot.values["gaps"]],
        })
        return
    if report:
        if run_aborted(thread_id):
            return
        save_report(report, topic)
    if run_aborted(thread_id):
        return
    publish(loop, queue, {"type": "done"})


async def event_stream(request: Request, queue: asyncio.Queue):
    while True:
        if await request.is_disconnected():
            break
        try:
            event = await asyncio.wait_for(queue.get(), timeout=15)
        except asyncio.TimeoutError:
            yield ": ping\n\n"
            continue
        if event is None:
            break
        yield sse(event)


@app.post("/research")
async def research(body: ResearchRequest, request: Request):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    config = {"configurable": {"thread_id": body.thread_id}}
    control = begin_run(body.thread_id)

    def run():
        token = use_selection(ModelSelection(
            api_key=body.api_key,
            planner=body.planner_model,
            extractor=body.extractor_model,
            writer=body.writer_model
        ))
        try:
            report = drive(
                loop,
                queue,
                graph.stream(
                    initial_state(body.topic, body.max_iterations),
                    config=config,
                    control=control,
                ),
                body.api_key,
            )
            try:
                finish_stream(loop, queue, body.thread_id, report, body.topic)
            except Exception as exc:
                publish(loop, queue, {"type": "error", "message": public_error(exc, body.api_key)})
        finally:
            end_run(body.thread_id, control)
            reset_selection(token)
            publish(loop, queue, None)

    threading.Thread(target=run, daemon=True).start()
    return StreamingResponse(event_stream(request, queue), media_type="text/event-stream")

@app.post("/research/{thread_id}/resume")
async def resume_research(thread_id: str, body: ResumeRequest, request: Request):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.next:
        raise HTTPException(status_code=404, detail="Research not found")
    
    topic = snapshot.values["topic"]
    questions = [question.strip() for question in body.questions if question.strip()][:7]
    if not questions:
        raise HTTPException(status_code=422, detail="Add at least one question")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    control = begin_run(thread_id)

    def run():
        token = use_selection(ModelSelection(
            api_key=body.api_key,
            planner=body.planner_model,
            extractor=body.extractor_model,
            writer=body.writer_model
        ))
        try:
            report = drive(
                loop,
                queue,
                graph.stream(Command(resume={"questions": questions}), config=config, control=control),
                body.api_key,
            )
            try:
                if report is not None and not run_aborted(thread_id):
                    snapshot = graph.get_state(config)
                    if snapshot.next:
                        publish(loop, queue, {
                            "type": "review",
                            "thread_id": thread_id,
                            "questions": [gap.question for gap in snapshot.values["gaps"]],
                            "error": "Add at least one question",
                        })
                    else:
                        finish_stream(loop, queue, thread_id, report, topic)
            except Exception as exc:
                publish(loop, queue, {"type": "error", "message": public_error(exc, body.api_key)})
        finally:
            end_run(thread_id, control)
            reset_selection(token)
            publish(loop, queue, None)

    threading.Thread(target=run, daemon=True).start()
    return StreamingResponse(event_stream(request, queue), media_type="text/event-stream")


@app.post("/research/{thread_id}/abort")
def abort_research(thread_id: str):
    request_abort(thread_id)
    return {"ok": True}

@app.get("/reports")
def list_reports() -> list[ReportSummary]:
    if not REPORTS.is_dir():
        return []
    reports = [
        ReportSummary(
            slug=path.stem,
            title=report_title(path),
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
        )
        for path in REPORTS.glob("*.md")
        if path.is_file() and valid_slug(path.stem)
    ]
    reports.sort(key=lambda item: item.updated_at, reverse=True)
    return reports


@app.get("/reports/{slug}")
def read_report(slug: str):
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="Report not found")
    path = REPORTS / f"{slug}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="text/markdown")

@app.get("/models")
def list_models() -> list[CatalogModel]:
    return catalog_models()


@app.post("/openrouter/key")
def check_key(body: KeyCheck):
    openrouter_json(KEY_URL, body.api_key)
    return {"ok": True}


@app.exception_handler(RequestValidationError)
async def hide_rejected_input(_request: Request, exc: RequestValidationError):
    message = "Invalid request"
    errors = exc.errors()
    if errors:
        raw = errors[0].get("msg", message)
        if isinstance(raw, str):
            message = raw.removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/health")
def health():
    return {"status": "ok"}