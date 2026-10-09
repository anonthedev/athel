import os
import sys
from pathlib import Path

import dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.llm import ModelSelection, reset_selection, use_selection
from app.nodes.planning import update_checklist
from app.states import Finding, KnowledgeGap, OverallState
from evals.checklist_eval.cases import CASES, Case
from evals.checklist_eval.verifier import failures, grade

_BACKEND = Path(__file__).resolve().parents[2]


def state_for(case: Case) -> OverallState:
    findings = [
        Finding(
            gap_id=1,
            answers_gap=True,
            note=note,
            source=f"https://fixture.test/{case.id}/{index}",
        )
        for index, note in enumerate(case.notes, start=1)
    ]
    return {
        "topic": case.question,
        "gaps": [KnowledgeGap(id=1, question=case.question)],
        "findings": findings,
        "additional_info": [],
        "planned_queries": [],
        "calls": [],
        "provider": "openrouter",
        "hits": [],
        "dead_urls": [],
        "blocked_domains": [],
        "max_iterations": 3,
        "search_engine": "duckduckgo",
        "research_loops": 0,
        "final_report": "",
    }


def main() -> int:
    dotenv.load_dotenv(_BACKEND / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("invalid: OPENROUTER_API_KEY is not set")
        return 2

    token = use_selection(ModelSelection(
        provider="openrouter",
        api_key=api_key,
        planner="openai/gpt-5-mini",
        extractor="google/gemini-3.1-flash-lite",
        writer="anthropic/claude-sonnet-5",
        embedding="openai/text-embedding-3-small",
    ))
    passed = 0
    try:
        for case in CASES:
            try:
                result = update_checklist(state_for(case))
            except Exception as exc:
                print(f"{case.id}: invalid ({type(exc).__name__})")
                continue
            updated = result["gaps"][0]
            verdict = grade(case, updated)
            passed += verdict == "pass"
            print(f"{case.id}: {verdict}")
            print(f"  status: {updated.status}")
            print(f"  missing: {updated.missing}")
            missed = failures(case, updated)
            if missed:
                print(f"  checks: {', '.join(missed)}")
    finally:
        reset_selection(token)

    print(f"{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
