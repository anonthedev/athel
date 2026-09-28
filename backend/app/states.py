from typing import Annotated, TypedDict, Literal
from pydantic import BaseModel
import operator

class SourcedNote(BaseModel):
    note: str
    source: str

class KnowledgeGap(BaseModel):
    id: int
    question: str
    status: Literal["pending", "resolved", "failed"] = "pending"
    notes: list[SourcedNote] = []
    missing: list[str] = []
    attempts: int = 0

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

class OverallState(TypedDict):
    topic: str
    gaps: list[KnowledgeGap]
    hits: Annotated[list[UrlHit], operator.add]
    findings: Annotated[list[Finding], operator.add]
    additional_info: list[SourcedNote]
    research_loops: int
    final_report: str
    dead_urls: Annotated[list[str], operator.add]
    blocked_domains: Annotated[list[str], operator.add]