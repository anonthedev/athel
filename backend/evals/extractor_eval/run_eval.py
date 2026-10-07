import os
import sys
from pathlib import Path
from unittest.mock import patch

import dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.llm import ModelSelection, reset_selection, use_selection
from app.nodes.scrape import scrape
from app.states import Finding
from evals.extractor_eval.cases import CASES, Case
from evals.extractor_eval.verifier import failures, grade

_BACKEND = Path(__file__).resolve().parents[2]


def extract(case: Case) -> tuple[Finding | None, str | None]:
    state = {"gap_id": 1, "question": case.question, "url": case.url}
    try:
        page = (case.page, case.url)
        with patch("app.nodes.scrape.pubmed_source.load", return_value=page), \
                patch("app.nodes.scrape.doi_source.matches", return_value=True), \
                patch("app.nodes.scrape.doi_source.load", return_value=page), \
                patch("app.nodes.scrape.reddit_source.load", return_value=page), \
                patch("app.nodes.scrape.substack_source.matches", return_value=True), \
                patch("app.nodes.scrape.substack_source.load", return_value=page), \
                patch("app.nodes.scrape.load_text", return_value=page):
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
        scraper="openai/gpt-5-mini",
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
            note = finding.note if finding is not None else ""
            additional = finding.additional if finding is not None else ""
            if finding is not None or verdict == "fail":
                print(f"  note: {note}")
                print(f"  additional: {additional}")
            missed = failures(case, finding)
            if missed:
                print(f"  checks: {', '.join(missed)}")
    finally:
        reset_selection(token)

    print(f"{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
