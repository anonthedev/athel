import os
import sys
from pathlib import Path
from unittest.mock import patch

import dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.llm import ModelSelection, reset_selection, use_selection
from app.nodes.search import scrape
from app.states import Finding
from evals.extractor_eval.cases import CASES, Case
from evals.extractor_eval.verifier import failures, grade

_BACKEND = Path(__file__).resolve().parents[2]


def extract(case: Case) -> tuple[Finding | None, str | None]:
    state = {"gap_id": 1, "question": case.question, "url": case.url}
    try:
        with patch("app.nodes.search.load_text", return_value=(case.page, case.url)):
            result = scrape(state)
    except Exception as exc:
        return None, type(exc).__name__
    findings = result.get("findings") or []
    return (findings[0] if findings else None), None


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
            finding, error = extract(case)
            if error:
                print(f"{case.id}: invalid ({error})")
                continue
            verdict = grade(case, finding)
            passed += verdict == "pass"
            print(f"{case.id}: {verdict}")
            if finding is not None:
                print(f"  note: {finding.note}")
                print(f"  additional: {finding.additional}")
            missed = failures(case, finding)
            if missed:
                print(f"  checks: {', '.join(missed)}")
    finally:
        reset_selection(token)

    print(f"{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
