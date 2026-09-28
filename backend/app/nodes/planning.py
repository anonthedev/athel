from app.states import OverallState, KnowledgeGap, Finding, SourcedNote
from app.llm import planner_llm
from pydantic import BaseModel
from langgraph.types import Send, Command
from langgraph.types import interrupt

MAX_ITERATIONS = 3

def generate_gaps(state: OverallState):
    class GapList(BaseModel):
        questions: list[str]

    prompt = f"""Break this research topic into 5 to 7 sub-questions that must be answered to write a comprehensive report.

                Each question should cover a distinct part of the topic, such as origins, key turning points, major contributors, how it works, applications, or limitations.
                Make each question specific enough that a web search could answer it.
                Do not write search keywords. Write the question itself.

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
    pending = [gap for gap in state["gaps"] if gap.status == "pending" and gap.attempts < MAX_ITERATIONS]
    blocked = list(dict.fromkeys(state.get("blocked_domains", [])))
    if pending:
        return [
            Send("draft_queries", {"gap": gap.model_dump(), "blocked_domains": blocked})
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
            "Write 2 or 3 short web search queries for only the unanswered parts.\n"
            "Do not write queries for facts already collected.\n\n"
            f"Question:\n{gap.question}\n\n"
            f"Already collected:\n{known}\n\n"
            f"Still unanswered:\n{needed}"
        )
        
    else:
        prompt = (
            "Write 3 or 4 short web search queries that would answer this question.\n\n"
            f"Question:\n{gap.question}"
        )

    result = planner_llm().with_structured_output(QueryList).invoke(prompt)

    blocked = state.get("blocked_domains", []) if isinstance(state, dict) else []

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

        if gap.status in ("resolved", "failed"):
            updated.append(gap)
            continue

        mine = [finding for finding in state["findings"] if finding.gap_id == gap.id]
        answering = [finding for finding in mine if finding.answers_gap and finding.note.strip()]
        extras.extend(sourced_notes(mine, "additional"))
        gap.notes = sourced_notes(answering, "note")

        if gap.notes:
            listed = "\n".join(f"- {note.note}\n  source: {note.source}" for note in gap.notes)
            result = planner_llm().with_structured_output(MissingList).invoke(
                "List only requirements the question already names that no note answers.\n"
                "Restate that requirement. Do not write a new question or a related issue.\n"
                "Return an empty list when the notes answer the question.\n\n"
                f"Question:\n{gap.question}\n\nNotes:\n{listed}"
            )

            gap.missing = result.missing
        else:
            gap.missing = [gap.question]
        if gap.notes and not gap.missing:
            gap.status = "resolved"
        else:
            gap.attempts += 1
            if gap.attempts >= MAX_ITERATIONS:
                gap.status = "failed"
        updated.append(gap)
    return {"gaps": updated, "additional_info": extras}