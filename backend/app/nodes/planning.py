from app.states import OverallState, KnowledgeGap, Finding, SourcedNote
from app.llm import planner_llm
from pydantic import BaseModel
from langgraph.types import Send, Command
from langgraph.types import interrupt

def generate_gaps(state: OverallState):
    class GapList(BaseModel):
        questions: list[str]

    prompt = f"""Split this topic into 5 to 7 questions that together cover it.

Stay inside what was asked. A question about history, famous people, ethics, or applications belongs here only when the topic asks for it.
Each question covers a different part. A review, a study, or a primary page should be able to answer it.
Write the question itself, not search keywords.

Topic:
{state["topic"]}"""

    result = planner_llm().with_structured_output(GapList).invoke(prompt)
    return {
        "gaps": [
            KnowledgeGap(id=index, question=question)
            for index, question in enumerate(result.questions[:7], start=1)
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
    return [question.strip() for question in raw if isinstance(question, str) and question.strip()][:7]


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
        prompt = (
            "Write 2 or 3 short web search queries that look up only the missing facts below.\n"
            "Use the names, dates, and terms in those facts. A query is a few search words, not a sentence.\n"
            "Do not search for facts already collected. Do not repeat the original question.\n\n"
            f"Question:\n{gap.question}\n\n"
            f"Already collected:\n{known}\n\n"
            f"Still needed:\n{needed}"
        )
        
    else:
        prompt = (
            "Write 3 or 4 short web search queries that would find a specific source for this question.\n"
            "Use the distinctive terms. Include one query aimed at a review or the named study when the question has one.\n"
            "A query is a few search words, not the question rewritten as a sentence.\n\n"
            f"Question:\n{gap.question}"
        )

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
                "List what this question still lacks. Return at most 4 items, shortest first.\n"
                "Each item is one lookup of ten words or fewer. Name the missing study, number, date, or mechanism. Do not write a new essay question.\n\n"
                "Put first any part the question already names that no note answers.\n"
                "A clinic page, a marketing page, or a quiz does not answer a part. A number with no study does not answer a part.\n\n"
                "Then add at most 3 new items the notes make necessary, still inside the 4-item cap: a figure with no study, a mechanism with no name, or two notes that disagree and neither names who measured it.\n"
                "Do not add history, ethics, or famous people unless the question asks for them.\n\n"
                "Return an empty list when the notes answer the question with claims that say who reported them, and no specific fact is still missing.\n\n"
                f"Question:\n{gap.question}\n\nNotes:\n{listed}"
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