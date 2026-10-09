from typing import Annotated, TypedDict, Literal
from pydantic import BaseModel
import operator

class SourcedNote(BaseModel):
    note: str
    source: str

class KnowledgeGap(BaseModel):
    id: int
    question: str
    status: Literal["pending", "resolved", "partial", "failed"] = "pending"
    notes: list[SourcedNote] = []
    missing: list[str] = []
    attempts: int = 0


def gap_mark(gap: KnowledgeGap) -> Literal["resolved", "partial", "unresolved"]:
    if gap.status == "resolved" or (gap.notes and not gap.missing):
        return "resolved"
    if gap.status == "partial" or gap.notes:
        return "partial"
    return "unresolved"

class Finding(BaseModel):
    gap_id: int
    answers_gap: bool
    note: str
    source: str
    additional: str = ""

class UrlHit(BaseModel):
    gap_id: int
    question: str
    url: str

class ModelCall(BaseModel):
    role: Literal["planner", "extractor", "writer", "embedding"]
    model: str
    label: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None

class PlannedQuery(BaseModel):
    question: str
    queries: list[str]

class OverallState(TypedDict):
    topic: str
    provider: str
    writing_tone: Literal["clear", "academic"]
    gaps: list[KnowledgeGap]
    hits: Annotated[list[UrlHit], operator.add]
    findings: Annotated[list[Finding], operator.add]
    additional_info: list[SourcedNote]
    planned_queries: Annotated[list[PlannedQuery], operator.add]
    calls: Annotated[list[ModelCall], operator.add]
    research_loops: int
    final_report: str
    dead_urls: Annotated[list[str], operator.add]
    blocked_domains: Annotated[list[str], operator.add]
    max_iterations: int
    search_engine: str