import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.llm import ModelSelection, reset_selection, use_selection
from app.nodes.scrape import scrape
from evals.script_eval.cases import CASES
from evals.script_eval.verifier import failures, grade

_BACKEND = Path(__file__).resolve().parents[2]


def _text(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def run_case(case, calls, scripts, runs):
    def record(name):
        def wrapped(*args, **kwargs):
            calls.append(name)
            return None
        return wrapped

    def page_load(url, question):
        calls.append("trafilatura")
        return None

    real_popen = subprocess.Popen

    def popen(command, **kwargs):
        calls.append("python_scraping")
        path = Path(command[-1])
        scripts.append(path.read_text(encoding="utf-8") if path.is_file() else "")
        proc = real_popen(command, **kwargs)

        class Recording:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def __enter__(self):
                self._inner.__enter__()
                return self

            def __exit__(self, exc_type, exc, tb):
                return self._inner.__exit__(exc_type, exc, tb)

            def communicate(self, input=None, timeout=None):
                out, err = self._inner.communicate(input, timeout=timeout)
                runs.append({
                    "code": self._inner.returncode,
                    "out": _text(out),
                    "err": _text(err),
                })
                return out, err

        return Recording(proc)

    with patch("app.nodes.scrape.pubmed_source.load", record("pubmed")), \
            patch("app.nodes.scrape.doi_source.load", record("doi")), \
            patch("app.nodes.scrape.doi_source.load_html", record("doi")), \
            patch("app.nodes.scrape.reddit_source.load", record("reddit")), \
            patch("app.nodes.scrape.substack_source.load", record("substack")), \
            patch("app.nodes.scrape.load_text", page_load), \
            patch("app.nodes.scrape.subprocess.Popen", popen):
        return scrape({"gap_id": 1, "question": case.question, "url": case.url})


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
            calls: list[str] = []
            scripts: list[str] = []
            runs: list[dict] = []
            try:
                result = run_case(case, calls, scripts, runs)
            except Exception as exc:
                print(f"{case.id}: invalid ({type(exc).__name__}: {exc})")
                continue
            verdict = grade(case, result, calls, scripts, runs)
            passed += verdict == "pass"
            finding = (result.get("findings") or [None])[0]
            print(f"{case.id}: {verdict}")
            print(f"  url: {case.url}")
            print(f"  calls: {calls or 'none'}")
            if runs:
                print(f"  stdout: {runs[-1]['out'].strip()[:300]}")
            if finding is not None:
                print(f"  note: {finding.note}")
            missed = failures(case, result, calls, scripts, runs)
            if missed:
                print(f"  checks: {', '.join(missed)}")
                if scripts:
                    print("  script:")
                    print("\n".join(f"    {line}" for line in scripts[-1].splitlines()[:40]))
                if runs and runs[-1]["err"].strip():
                    print(f"  stderr: {runs[-1]['err'].strip()[:500]}")
    finally:
        reset_selection(token)

    print(f"{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
