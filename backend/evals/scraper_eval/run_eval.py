import os
import sys
from pathlib import Path
from unittest.mock import patch

import dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.helper.sources.http import Response
from app.llm import ModelSelection, reset_selection, use_selection
from app.nodes.scrape import scrape
from evals.scraper_eval.cases import CASES, Case
from evals.scraper_eval.verifier import failures, grade

_BACKEND = Path(__file__).resolve().parents[2]
_PUBLISHER_HTML = b'<meta name="citation_doi" content="10.1038/s41586-021-03819-2">'


def text_for(case: Case, tool: str) -> tuple[str, str] | None:
    if case.dead and tool == "trafilatura":
        return None
    if tool == case.via:
        return case.text, case.source or case.url
    if tool == "trafilatura" and case.decoy:
        return case.decoy, case.url
    return None


class _Script:
    def __init__(self, stdout: bytes, code: int):
        self.pid = 1
        self.returncode = code
        self._stdout = stdout

    def communicate(self, timeout=None):
        return self._stdout, b""


def run_case(case: Case) -> tuple[dict, list[str], list[str]]:
    calls: list[str] = []
    scripts: list[str] = []

    def pubmed_load(url, question):
        calls.append("pubmed")
        return text_for(case, "pubmed")

    def doi_load(url, question):
        calls.append("doi")
        return None if case.fetch else text_for(case, "doi")

    def doi_load_html(url, html, question):
        calls.append("doi")
        return text_for(case, "doi") if case.fetch else None

    def reddit_load(url, question):
        calls.append("reddit")
        return text_for(case, "reddit")

    def substack_load(url, question):
        calls.append("substack")
        return text_for(case, "substack")

    def page_load(url, question):
        calls.append("trafilatura")
        return text_for(case, "trafilatura")

    def fetch(url):
        if case.fetch:
            return Response(200, url, _PUBLISHER_HTML)
        return None

    def popen(command, **kwargs):
        calls.append("python_scraping")
        path = Path(command[-1])
        scripts.append(path.read_text(encoding="utf-8") if path.is_file() else "")
        loaded = text_for(case, "python_scraping")
        if loaded is None:
            return _Script(b"", 1)
        return _Script(loaded[0].encode(), 0)

    with patch("app.nodes.scrape.pubmed_source.load", pubmed_load), \
            patch("app.nodes.scrape.doi_source.load", doi_load), \
            patch("app.nodes.scrape.doi_source.load_html", doi_load_html), \
            patch("app.nodes.scrape.reddit_source.load", reddit_load), \
            patch("app.nodes.scrape.substack_source.load", substack_load), \
            patch("app.nodes.scrape.load_text", page_load), \
            patch("app.nodes.scrape.fetch_response", fetch), \
            patch("app.nodes.scrape.subprocess.Popen", popen):
        result = scrape({"gap_id": 1, "question": case.question, "url": case.url})
    return result, calls, scripts


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
            try:
                result, calls, scripts = run_case(case)
            except Exception as exc:
                print(f"{case.id}: invalid ({type(exc).__name__})")
                continue
            verdict = grade(case, result, calls, scripts)
            passed += verdict == "pass"
            finding = (result.get("findings") or [None])[0]
            print(f"{case.id}: {verdict}")
            print(f"  calls: {calls or 'none'}")
            if finding is not None:
                print(f"  note: {finding.note}")
                print(f"  additional: {finding.additional}")
            missed = failures(case, result, calls, scripts)
            if missed:
                print(f"  checks: {', '.join(missed)}")
    finally:
        reset_selection(token)

    print(f"{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
