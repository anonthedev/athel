from app.progress import announce
from app.states import OverallState, KnowledgeGap, Finding, PlannedQuery, SourcedNote
from app.llm import planner_llm
from app.prompts import followup_queries, gaps, missing_parts, search_queries
from app.usage import collect_calls, structured
from pydantic import BaseModel
from langgraph.types import Send, Command
from langgraph.types import interrupt

def generate_gaps(state: OverallState):
    class GapList(BaseModel):
        questions: list[str]

    with collect_calls() as recorded:
        result = structured(planner_llm(), GapList, gaps(state["topic"]), role="planner", label="Draft questions")
        return {
            "gaps": [
                KnowledgeGap(id=index, question=question)
                for index, question in enumerate(result.questions[:12], start=1)
            ],
            "calls": list(recorded),
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

    with collect_calls() as recorded:
        result = structured(planner_llm(), QueryList, prompt, role="planner", label=gap.question)
        queries = result.queries[:4]

    blocked = state.get("blocked_domains", []) if isinstance(state, dict) else []
    engine = state.get("search_engine", "tavily") if isinstance(state, dict) else "tavily"

    question = gap.question
    if gap.missing:
        question = gap.question + "\nStill needed:\n" + "\n".join(gap.missing)

    return Command(
        update={
            "calls": list(recorded),
            "planned_queries": [PlannedQuery(question=gap.question, queries=queries)],
        },
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
            for query in queries
        ],
    )

_COLLAPSE = "What do the available sources actually say about "


def collapse_question(topic: str) -> str:
    return f"{_COLLAPSE}{topic.strip()}?"


def topic_of_collapse(question: str) -> str | None:
    line = question.split("\n", 1)[0].strip()
    if not line.startswith(_COLLAPSE) or not line.endswith("?"):
        return None
    topic = line[len(_COLLAPSE) : -1].strip()
    return topic or None


def collapse_empty_wave(
    gaps: list[KnowledgeGap], topic: str, *, first_wave: bool
) -> list[KnowledgeGap]:
    if not first_wave:
        return gaps
    empty = [gap for gap in gaps if not gap.notes]
    if len(empty) < 2 or len(empty) * 2 <= len(gaps):
        return gaps
    kept = [gap for gap in gaps if gap.notes]
    kept.append(KnowledgeGap(id=max(gap.id for gap in gaps) + 1, question=collapse_question(topic)))
    return kept


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

def update_checklist(state: OverallState) -> dict:
    announce("Checking for gaps")
    class MissingList(BaseModel):
        missing: list[str]

    first_wave = all(gap.attempts == 0 for gap in state["gaps"])
    updated = []
    # Side notes are kept across waves, including gaps this pass collapses away.
    extras = sourced_notes(state["findings"], "additional")

    with collect_calls() as recorded:
        for gap in state["gaps"]:
            gap = gap.model_copy(deep=True)

            if gap.status in ("resolved", "partial", "failed"):
                updated.append(gap)
                continue

            mine = [finding for finding in state["findings"] if finding.gap_id == gap.id]
            answering = [finding for finding in mine if finding.answers_gap and finding.note.strip()]
            gap.notes = sourced_notes(answering, "note")

            if gap.notes:
                listed = "\n".join(f"- {note.note}\n  source: {note.source}" for note in gap.notes)
                result = structured(
                    planner_llm(),
                    MissingList,
                    missing_parts(gap.question, listed),
                    role="planner",
                    label=gap.question,
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
        calls = list(recorded)
    updated = collapse_empty_wave(updated, state["topic"], first_wave=first_wave)
    return {"gaps": updated, "additional_info": extras, "calls": calls}