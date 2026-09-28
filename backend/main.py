import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.graph import graph

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS = Path(__file__).resolve().parent / "reports"


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1)


class ReportSummary(BaseModel):
    slug: str
    title: str
    updated_at: datetime


def initial_state(topic: str) -> dict:
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


@app.post("/research")
async def research(body: ResearchRequest, request: Request):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def run():
        report = ""
        try:
            for chunk in graph.stream(initial_state(body.topic)):
                for node, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    for event in events_from(node, update):
                        if event["type"] == "report":
                            report = event["markdown"]
                        loop.call_soon_threadsafe(queue.put_nowait, event)
            if report:
                save_report(report, body.topic)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(exc)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=run, daemon=True).start()

    async def generate():
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

    return StreamingResponse(generate(), media_type="text/event-stream")


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

@app.get("/health")
def health():
    return {"status": "ok"}