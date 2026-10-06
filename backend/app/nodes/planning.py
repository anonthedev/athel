from app.progress import announce
from app.states import OverallState, KnowledgeGap, Finding, SourcedNote
from app.llm import planner_llm
from app.prompts import followup_queries, gaps, missing_parts, search_queries
from pydantic import BaseModel
from langgraph.types import Send, Command
from langgraph.types import interrupt

def generate_gaps(state: OverallState):
    class GapList(BaseModel):
        questions: list[str]

    result = planner_llm().with_structured_output(GapList).invoke(gaps(state["topic"]))
    return {
        "gaps": [
            KnowledgeGap(id=index, question=question)
            for index, question in enumerate(result.questions[:12], start=1)
        ]
    }

def fan_out_gaps(state: OverallState):
    pending = [gap for gap in state["gaps"] if gap.status == "pending" and gap.attempts < state["max_iterations"]]
    blocked = list(dict.fromkeys(state.get("blocked_domains", [])))
    if pending:
        engine = state.get("search_engine", "tavily")
        return [
            Send(
                "draft_queries",
                {"gap": gap.model_dump(), "blocked_domains": blocked, "search_engine": engine},
            )
            for gap in pending
        ]

    return "write_final_report"

def approved_questions(payload: dict) -> list[str]:
    raw = payload.get("questions", [])
    if not isinstance(raw, list):
        return []
    return [question.strip() for question in raw if isinstance(question, str) and question.strip()][:12]


def review_gaps(state: OverallState):
    edited = interrupt({"questions": [gap.question for gap in state["gaps"]]})
    questions = approved_questions(edited)

    if not questions:
        edited = interrupt({
            "questions": [gap.question for gap in state["gaps"]],
            "error": "Add at least one question",
        })
        questions = approved_questions(edited)

    return {
        "gaps": [
            KnowledgeGap(id=index, question=question)
            for index, question in enumerate(questions, start=1)
        ]
    }

def draft_queries(state: dict) -> Command:
    class QueryList(BaseModel):
        queries: list[str]
    gap = state["gap"] if isinstance(state, dict) and "gap" in state else state

    if isinstance(gap, dict):
        gap = KnowledgeGap.model_validate(gap)

    if gap.missing and gap.notes:
        known = "\n".join(f"- {note.note}" for note in gap.notes)
        needed = "\n".join(f"- {part}" for part in gap.missing)
        prompt = followup_queries(gap.question, known, needed)
    else:
        prompt = search_queries(gap.question)

    result = planner_llm().with_structured_output(QueryList).invoke(prompt)

    blocked = state.get("blocked_domains", []) if isinstance(state, dict) else []
    engine = state.get("search_engine", "tavily") if isinstance(state, dict) else "tavily"

    question = gap.question
    if gap.missing:
        question = gap.question + "\nStill needed:\n" + "\n".join(gap.missing)

    return Command(
        goto=[
            Send(
                "search",
                {
                    "gap_id": gap.id,
                    "question": question,
                    "query": query,
                    "blocked_domains": blocked,
                    "search_engine": engine,
                },
            )
            for query in result.queries[:4]
        ]
    )

def sourced_notes(findings: list[Finding], field: str) -> list[SourcedNote]:
    seen = set()
    notes = []
    for finding in findings:
        text = getattr(finding, field).strip()
        key = (text, finding.source)
        if not text or key in seen:
            continue
        seen.add(key)
        notes.append(SourcedNote(note=text, source=finding.source))
    return notes

def update_checklist(state: OverallState) -> Command:
    announce("Checking for gaps")
    class MissingList(BaseModel):
        missing: list[str]
    
    extras = []
    updated = []

    for gap in state["gaps"]:
        gap = gap.model_copy(deep=True)

        if gap.status in ("resolved", "partial", "failed"):
            updated.append(gap)
            continue

        mine = [finding for finding in state["findings"] if finding.gap_id == gap.id]
        answering = [finding for finding in mine if finding.answers_gap and finding.note.strip()]
        extras.extend(sourced_notes(mine, "additional"))
        gap.notes = sourced_notes(answering, "note")

        if gap.notes:
            listed = "\n".join(f"- {note.note}\n  source: {note.source}" for note in gap.notes)
            result = planner_llm().with_structured_output(MissingList).invoke(
                missing_parts(gap.question, listed)
            )

            gap.missing = result.missing
        else:
            gap.missing = [gap.question]
        if gap.notes and not gap.missing:
            gap.status = "resolved"
        else:
            gap.attempts += 1
            if gap.attempts >= state["max_iterations"]:
                gap.status = "partial" if gap.notes else "failed"
        updated.append(gap)
    return {"gaps": updated, "additional_info": extras}