from app.states import (
    Finding,
    KnowledgeGap,
    ModelCall,
    OverallState,
    PlannedQuery,
    SourcedNote,
    UrlHit,
)
from app.nodes.planning import generate_gaps, fan_out_gaps, update_checklist, draft_queries, review_gaps
from app.nodes.search import search, scrape, fan_out_scrapes
from app.nodes.report import write_final_report
from pathlib import Path
import sqlite3

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END

_CHECKPOINT_TYPES = (KnowledgeGap, SourcedNote, Finding, UrlHit, ModelCall, PlannedQuery)

workflow = StateGraph(OverallState)

workflow.add_node("generate_gaps", generate_gaps)
workflow.add_node("review_gaps", review_gaps)
workflow.add_node("draft_queries", draft_queries, input_schema=KnowledgeGap)
workflow.add_node("search", search)
workflow.add_node("scrape", scrape)
workflow.add_node("update_checklist", update_checklist, defer=True)
workflow.add_node("write_final_report", write_final_report)
workflow.add_node("collect_hits", lambda state: {}, defer=True)


workflow.add_edge(START, "generate_gaps")
workflow.add_edge("generate_gaps", "review_gaps")
workflow.add_conditional_edges("review_gaps", fan_out_gaps, ["draft_queries", "write_final_report"])
workflow.add_edge("search", "collect_hits")
workflow.add_conditional_edges("collect_hits", fan_out_scrapes, ["scrape", "update_checklist"])
workflow.add_edge("scrape", "update_checklist")
workflow.add_conditional_edges("update_checklist", fan_out_gaps, ["draft_queries", "write_final_report"])
workflow.add_edge("write_final_report", END)


def compile_graph(checkpointer):
    return workflow.compile(checkpointer=checkpointer)


def open_checkpointer(path: Path) -> SqliteSaver:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    checkpointer = SqliteSaver(
        connection,
        serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES),
    )
    checkpointer.setup()
    return checkpointer