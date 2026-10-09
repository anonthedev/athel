import os
import dotenv
import asyncio
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from langgraph.errors import GraphDrained
from langgraph.runtime import RunControl
from langgraph.types import Command
from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.graph import compile_graph, open_checkpointer
from app.states import gap_mark
from app.trace import trace_from_history
from app.llm import OLLAMA_BASE_URL, ModelSelection, reset_selection, use_selection
from app.nodes.search import reset_tavily_key, use_tavily_key

dotenv.load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS = Path(os.environ.get("DEEP_RESEARCH_REPORTS", Path(__file__).resolve().parent / "reports"))
THREAD_ID = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
graph = compile_graph(open_checkpointer(REPORTS / "checkpoints.sqlite"))
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}/[A-Za-z0-9][A-Za-z0-9._:@+-]{0,160}$")
OLLAMA_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,200}$")
MODELS_URL = "https://openrouter.ai/api/v1/models"
KEY_URL = "https://openrouter.ai/api/v1/key"
_models_cache: tuple[float, list["CatalogModel"]] | None = None
_embedding_models_cache: tuple[float, list["CatalogModel"]] | None = None
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


def require_provider(value: str) -> str:
    value = value.strip().lower()
    if value not in ("openrouter", "ollama"):
        raise ValueError("Choose OpenRouter or Ollama")
    return value


def require_ollama_model(value: str) -> str:
    value = value.strip()
    if not OLLAMA_MODEL.fullmatch(value):
        raise ValueError("Choose an Ollama model")
    return value


def optional_embedding(value: str, provider: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if provider == "ollama":
        return require_ollama_model(value)
    return require_model(value)


def normalize_run_models(
    provider: str,
    api_key: str,
    planner: str,
    extractor: str,
    writer: str,
    embedding: str,
) -> tuple[str, str, str, str, str, str]:
    provider = require_provider(provider)
    if provider == "ollama":
        return (
            provider,
            "",
            require_ollama_model(planner),
            require_ollama_model(extractor),
            require_ollama_model(writer),
            optional_embedding(embedding, provider),
        )
    return (
        provider,
        require_api_key(api_key),
        require_model(planner),
        require_model(extractor),
        require_model(writer),
        optional_embedding(embedding, provider),
    )


def require_search_engine(value: str) -> str:
    value = value.strip().lower()
    if value not in ("tavily", "duckduckgo"):
        raise ValueError("Choose Tavily or DuckDuckGo")
    return value


def normalize_tavily_key(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) < 8 or len(value) > 300 or any(character.isspace() for character in value):
        raise ValueError("That isn't a Tavily API key")
    return value


ApiKey = Annotated[str, AfterValidator(require_api_key)]
SearchEngine = Annotated[str, AfterValidator(require_search_engine)]
TavilyKey = Annotated[str, AfterValidator(normalize_tavily_key)]
WritingTone = Literal["clear", "academic"]


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1)
    provider: str = "openrouter"
    api_key: str = ""
    planner_model: str
    extractor_model: str
    writer_model: str
    embedding_model: str
    thread_id: str = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1, le=10)
    search_engine: SearchEngine = "duckduckgo"
    tavily_api_key: TavilyKey = ""
    writing_tone: WritingTone = "clear"

    @model_validator(mode="after")
    def normalize(self):
        (
            self.provider,
            self.api_key,
            self.planner_model,
            self.extractor_model,
            self.writer_model,
            self.embedding_model,
        ) = normalize_run_models(
            self.provider,
            self.api_key,
            self.planner_model,
            self.extractor_model,
            self.writer_model,
            self.embedding_model,
        )
        if self.search_engine == "tavily" and not self.tavily_api_key:
            raise ValueError("Add a Tavily API key")
        return self

class ResumeRequest(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=12)
    provider: str = "openrouter"
    api_key: str = ""
    planner_model: str
    extractor_model: str
    writer_model: str
    embedding_model: str
    tavily_api_key: TavilyKey = ""
    writing_tone: WritingTone = "clear"

    @model_validator(mode="after")
    def normalize(self):
        (
            self.provider,
            self.api_key,
            self.planner_model,
            self.extractor_model,
            self.writer_model,
            self.embedding_model,
        ) = normalize_run_models(
            self.provider,
            self.api_key,
            self.planner_model,
            self.extractor_model,
            self.writer_model,
            self.embedding_model,
        )
        return self

class KeyCheck(BaseModel):
    api_key: ApiKey


class CatalogModel(BaseModel):
    id: str
    name: str
    tools: bool
    embedding: bool = False


class ReportSummary(BaseModel):
    slug: str
    title: str
    updated_at: datetime


def selection_for(body: ResearchRequest | ResumeRequest) -> ModelSelection:
    return ModelSelection(
        provider=body.provider,
        api_key=body.api_key,
        planner=body.planner_model,
        extractor=body.extractor_model,
        writer=body.writer_model,
        embedding=body.embedding_model,
    )


def initial_state(
    topic: str,
    max_iterations: int,
    search_engine: str,
    provider: str,
    writing_tone: WritingTone = "clear",
) -> dict:
    return {
        "topic": topic,
        "provider": provider,
        "writing_tone": writing_tone,
        "gaps": [],
        "findings": [],
        "additional_info": [],
        "planned_queries": [],
        "calls": [],
        "research_loops": 0,
        "final_report": "",
        "hits": [],
        "dead_urls": [],
        "blocked_domains": [],
        "max_iterations": max_iterations,
        "search_engine": search_engine,
    }


def slugify(topic: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in topic).strip("-")
    return slug[:40].strip("-")


def valid_slug(slug: str) -> bool:
    return bool(slug) and slug.replace("-", "").isalnum()


def report_title(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    return path.stem.replace("-", " ")


def save_report(report: str, topic: str, thread_id: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)
    if not valid_slug(slug):
        raise ValueError("Topic did not produce a report filename")
    path = REPORTS / f"{slug}.md"
    path.write_text(report.strip() + "\n", encoding="utf-8")
    if THREAD_ID.fullmatch(thread_id):
        (REPORTS / f"{slug}.thread").write_text(thread_id + "\n", encoding="utf-8")
    return path


def thread_for(slug: str) -> str | None:
    path = REPORTS / f"{slug}.thread"
    if not path.is_file():
        return None
    thread_id = path.read_text(encoding="utf-8").strip()
    if not THREAD_ID.fullmatch(thread_id):
        return None
    return thread_id


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


def drive(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, chunks, api_key: str, tavily_api_key: str = "") -> str | None:
    report = ""
    try:
        for chunk in chunks:
            mode, payload = chunk if isinstance(chunk, tuple) else ("updates", chunk)
            if mode == "custom":
                if isinstance(payload, dict) and payload.get("type") == "activity":
                    publish(loop, queue, payload)
                continue
            if mode != "updates" or not isinstance(payload, dict):
                continue
            for node, update in payload.items():
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
        publish(loop, queue, {"type": "error", "message": public_error(exc, api_key, tavily_api_key)})
        return None
    return report


def public_error(exc: Exception, *secrets: str) -> str:
    message = str(exc).strip() or "Research failed"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
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


def embedding_catalog(api_key: str) -> list[CatalogModel]:
    global _embedding_models_cache
    cached = _embedding_models_cache
    now = time.monotonic()
    if cached is not None and now - cached[0] < 600:
        return cached[1]

    payload = openrouter_json("https://openrouter.ai/api/v1/embeddings/models", api_key)
    models: list[CatalogModel] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            name = model_id
        models.append(CatalogModel(id=model_id, name=name.strip(), tools=False))
    models.sort(key=lambda model: model.name.casefold())
    _embedding_models_cache = (now, models)
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
            if finding.note.strip() or finding.additional.strip()
        ]
        events.extend({"type": "dead_url", "url": url} for url in update.get("dead_urls", []))
        return events

    if node == "update_checklist":
        return [
            {
                "type": "gap",
                "id": gap.id,
                "question": gap.question,
                "status": gap_mark(gap),
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
        save_report(report, topic, thread_id)
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
        token = use_selection(selection_for(body))
        tavily_token = use_tavily_key(body.tavily_api_key)
        try:
            report = drive(
                loop,
                queue,
                graph.stream(
                    initial_state(
                        body.topic,
                        body.max_iterations,
                        body.search_engine,
                        body.provider,
                        body.writing_tone,
                    ),
                    config=config,
                    control=control,
                    stream_mode=["updates", "custom"],
                ),
                body.api_key,
                body.tavily_api_key,
            )
            try:
                finish_stream(loop, queue, body.thread_id, report, body.topic)
            except Exception as exc:
                publish(loop, queue, {"type": "error", "message": public_error(exc, body.api_key, body.tavily_api_key)})
        finally:
            end_run(body.thread_id, control)
            reset_selection(token)
            reset_tavily_key(tavily_token)
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
    questions = [question.strip() for question in body.questions if question.strip()][:12]
    if not questions:
        raise HTTPException(status_code=422, detail="Add at least one question")
    if snapshot.values.get("search_engine") == "tavily" and not body.tavily_api_key:
        raise HTTPException(status_code=422, detail="Add a Tavily API key")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    control = begin_run(thread_id)

    def run():
        token = use_selection(selection_for(body))
        tavily_token = use_tavily_key(body.tavily_api_key)
        try:
            report = drive(
                loop,
                queue,
                graph.stream(
                    Command(
                        resume={"questions": questions},
                        update={"writing_tone": body.writing_tone},
                    ),
                    config=config,
                    control=control,
                    stream_mode=["updates", "custom"],
                ),
                body.api_key,
                body.tavily_api_key,
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
                publish(loop, queue, {"type": "error", "message": public_error(exc, body.api_key, body.tavily_api_key)})
        finally:
            end_run(thread_id, control)
            reset_selection(token)
            reset_tavily_key(tavily_token)
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


@app.get("/reports/{slug}/trace")
def read_trace(slug: str):
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="Report not found")
    thread_id = thread_for(slug)
    if thread_id is None:
        raise HTTPException(status_code=404, detail="Usage was not saved for this report")
    history = list(graph.get_state_history({"configurable": {"thread_id": thread_id}}))
    return trace_from_history(history)


@app.get("/reports/{slug}")
def read_report(slug: str):
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="Report not found")
    path = REPORTS / f"{slug}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="text/markdown")

def _ollama_json(url: str, payload: dict | None = None, timeout: float = 5) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    if not isinstance(body, dict):
        raise ValueError("Ollama returned an unexpected response")
    return body


def classify_ollama(name: str, family: str, capabilities: list | None) -> tuple[bool, bool]:
    if capabilities:
        caps = {str(item) for item in capabilities}
        return "tools" in caps, "embedding" in caps
    embedding = "embed" in name.casefold() or "embed" in family.casefold()
    return not embedding, embedding


def describe_ollama_model(name: str, family: str) -> CatalogModel:
    capabilities = None
    try:
        shown = _ollama_json(f"{OLLAMA_BASE_URL}/api/show", {"model": name})
        caps = shown.get("capabilities")
        if isinstance(caps, list):
            capabilities = caps
        if not family:
            details = shown.get("details")
            if isinstance(details, dict) and isinstance(details.get("family"), str):
                family = details["family"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        capabilities = None
    tools, embedding = classify_ollama(name, family, capabilities)
    return CatalogModel(id=name, name=name, tools=tools, embedding=embedding)


def ollama_catalog() -> list[CatalogModel]:
    try:
        payload = _ollama_json(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Ollama isn't running on this computer") from None
    raw = payload.get("models")
    if not isinstance(raw, list):
        raise HTTPException(status_code=503, detail="Ollama isn't running on this computer")
    entries: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not isinstance(name, str) or not OLLAMA_MODEL.fullmatch(name):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        family = details.get("family") if isinstance(details.get("family"), str) else ""
        entries.append((name, family))
    with ThreadPoolExecutor(max_workers=8) as pool:
        models = list(pool.map(lambda entry: describe_ollama_model(*entry), entries))
    models.sort(key=lambda model: model.name.casefold())
    return models


@app.get("/models")
def list_models() -> list[CatalogModel]:
    return catalog_models()


@app.get("/ollama/models")
def list_ollama_models() -> list[CatalogModel]:
    return ollama_catalog()


@app.post("/embedding-models")
def list_embedding_models(body: KeyCheck) -> list[CatalogModel]:
    return embedding_catalog(body.api_key)


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

