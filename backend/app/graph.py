from app.states import OverallState, KnowledgeGap
from app.nodes.planning import generate_gaps, fan_out_gaps, update_checklist, draft_queries, review_gaps
from app.nodes.scrape import scrape
from app.nodes.search import search, fan_out_scrapes
from app.nodes.report import write_final_report
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

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


graph = workflow.compile(checkpointer=InMemorySaver())