import os
import re
import sys
import urllib.request
from pathlib import Path

import dotenv
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.helper.pdf import excerpt_pages
from app.llm import ModelSelection, reset_selection, use_selection
from evals.pdf_eval.cases import CASES, Case

_BACKEND = Path(__file__).resolve().parents[2]
_CACHE = Path("/tmp/deep-research-arxiv")
_LABEL = re.compile(r"\[p\.(\d+)(?:-(\d+))?\]")


def download(case: Case) -> bytes:
    _CACHE.mkdir(parents=True, exist_ok=True)
    dest = _CACHE / f"{case.id}.pdf"
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest.read_bytes()
    request = urllib.request.Request(
        case.url,
        headers={"User-Agent": "deep-research-eval/0.1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    dest.write_bytes(data)
    return data


def load_pages(data: bytes) -> list[tuple[int, str]]:
    document = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    try:
        for number, page in enumerate(document, start=1):
            text = page.get_text().strip()
            if text:
                pages.append((number, text))
    finally:
        document.close()
    return pages


def selected_pages(excerpt: str) -> list[int]:
    found = []
    for match in _LABEL.finditer(excerpt):
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        for number in range(start, end + 1):
            if number not in found:
                found.append(number)
    return found


def score(relevant_pages: list[int], irrelevant: tuple[int, ...], relevant: str, excerpt: str) -> dict:
    selected = selected_pages(excerpt)
    leaked = [page for page in irrelevant if page in selected]
    return {
        "recall_hit": sum(page in selected for page in relevant_pages),
        "recall_total": len(relevant_pages),
        "text_included": relevant in excerpt,
        "leaked": leaked,
        "pages": selected,
        "empty": not excerpt.strip(),
    }


def _ratio(hit: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{hit}/{total} ({hit / total:.2f})"


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
    rows = []
    try:
        for case in CASES:
            print(f"{case.id}  {case.url}")
            try:
                pages = load_pages(download(case))
            except Exception as exc:
                print(f"  invalid download ({type(exc).__name__})")
                continue
            relevant_pages = [number for number, text in pages if case.relevant in text]
            if not relevant_pages:
                print(f"  invalid: {case.relevant!r} is not in the PDF")
                continue
            try:
                excerpt = excerpt_pages(pages, case.question)
            except Exception as exc:
                print(f"  invalid ({type(exc).__name__})")
                continue
            row = score(relevant_pages, case.irrelevant, case.relevant, excerpt)
            rows.append(row)
            print(f"  relevant pages: {relevant_pages}")
            print(f"  recall: {_ratio(row['recall_hit'], row['recall_total'])}")
            print(f"  relevant text included: {'yes' if row['text_included'] else 'no'}")
            print(f"  irrelevant pages included: {row['leaked'] or 'none'}")
            print(f"  pages passed on: {row['pages'] or 'none'}")
            if row["empty"]:
                print("  empty excerpt")
    finally:
        reset_selection(token)

    if not rows:
        print("recall: n/a")
        return 1

    recall_hit = sum(row["recall_hit"] for row in rows)
    recall_total = sum(row["recall_total"] for row in rows)
    included = sum(row["text_included"] for row in rows)
    clean = sum(not row["leaked"] for row in rows)
    print(
        f"recall {_ratio(recall_hit, recall_total)}  "
        f"relevant text included {_ratio(included, len(rows))}  "
        f"no irrelevant pages {_ratio(clean, len(rows))}"
    )
    passed = recall_hit == recall_total and included == len(rows) and clean == len(rows)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
