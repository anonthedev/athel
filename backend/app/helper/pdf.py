import json
import re
import urllib.error
import urllib.request

import pymupdf

PDF_BUDGET = 24_000
SPILL = 400
MAX_CHUNKS = 12

_SENTENCE_END = re.compile(r"""[.?!]["')\]]?\s*$""")
_SENTENCE_BREAK = re.compile(r"""[.?!]["')\]]?(?=\s|$)""")
_HYPHEN = re.compile(r"([A-Za-z]{2,})-\s*$")
_NEXT_WORD = re.compile(r"^([A-Za-z]+)([^\w\s]*)")


def pdf_excerpt(data: bytes, question: str) -> str:
    if not _embedding_model():
        return ""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    pages = []
    try:
        for number, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages.append((number, text))
    finally:
        doc.close()
    return excerpt_pages(pages, question)


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _unit(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def embedding_configured() -> bool:
    return bool(_embedding_model())


def _embedding_model() -> str:
    from app.llm import current_selection

    try:
        return current_selection().embedding.strip()
    except RuntimeError:
        return ""


def _embeddings(texts: list[str]) -> list[list[float]] | None:
    from app.llm import OLLAMA_BASE_URL, OPENROUTER_BASE_URL, current_selection

    if not texts:
        return []
    model = _embedding_model()
    if not model:
        return None
    try:
        selection = current_selection()
    except RuntimeError:
        return None
    if selection.provider == "ollama":
        url = f"{OLLAMA_BASE_URL}/v1/embeddings"
        token = "ollama"
    else:
        url = f"{OPENROUTER_BASE_URL}/embeddings"
        token = selection.api_key
    ordered: list[list[float] | None] = [None] * len(texts)
    for offset in range(0, len(texts), 64):
        batch = texts[offset : offset + 64]
        payload = json.dumps({"model": model, "input": batch}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return None
        for item in data:
            if not isinstance(item, dict):
                return None
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or not isinstance(embedding, list):
                return None
            slot = offset + index
            if slot < 0 or slot >= len(ordered):
                return None
            try:
                ordered[slot] = _unit([float(value) for value in embedding])
            except (TypeError, ValueError):
                return None
    if any(vector is None for vector in ordered):
        return None
    return [vector for vector in ordered if vector is not None]


def excerpt_pages(pages: list[tuple[int, str]], question: str) -> str:
    prepared = _prepare(pages)
    if not prepared:
        return ""
    passages = _passages(prepared)
    vectors = _embeddings([question, *(text for _, _, _, text in passages)])
    if not vectors or len(vectors) != len(passages) + 1:
        return ""
    query = vectors[0]

    ranked = sorted(
        (
            (_dot(query, vector), start, end, order, text)
            for vector, (start, end, order, text) in zip(vectors[1:], passages)
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    if not ranked or ranked[0][0] <= 0:
        return ""
    chosen = []
    used = 0
    best = ranked[0][0]

    for score, start, end, order, text in ranked:
        block = len(f"[p.{_page_label(start, end)}]\n{text}")
        if score / best <= 0.6 or len(chosen) >= MAX_CHUNKS or used + block > PDF_BUDGET:
            break
        chosen.append((start, end, order, text))
        used += block
    chosen.sort(key=lambda item: item[2])
    return "\n\n".join(
        f"[p.{_page_label(start, end)}]\n{text}" for start, end, _, text in chosen
    )


def _chunk_words(text: str, size: int = 200, overlap: int = 20) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text]
    pieces = []
    start = 0
    while start < len(words):
        pieces.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
        start += size - overlap
    return pieces


def _passages(pages: dict[int, str]) -> list[tuple[int, int, int, str]]:
    numbers = sorted(pages)
    passages = []
    order = 0

    for index, number in enumerate(numbers):
        chunks = _chunk_words(pages[number])
        nxt = numbers[index + 1] if index + 1 < len(numbers) else None
        for chunk_index, chunk in enumerate(chunks):
            start = end = number
            text = chunk.strip()
            if chunk_index == len(chunks) - 1 and nxt == number + 1 and not _ends_sentence(text):
                extra = _leading_sentence(pages[nxt])
                if extra:
                    text = f"{text} {extra}".strip()
                    end = nxt
            if text:
                passages.append((start, end, order, text))
                order += 1
    return passages


def _prepare(pages: list[tuple[int, str]]) -> dict[int, str]:
    cleaned = [(number, text.strip()) for number, text in pages if text and text.strip()]
    prepared: dict[int, str] = {}
    for index, (number, text) in enumerate(cleaned):
        if index + 1 < len(cleaned) and cleaned[index + 1][0] == number + 1:
            text, nxt = _dehyphen(text, cleaned[index + 1][1])
            cleaned[index + 1] = (cleaned[index + 1][0], nxt)
        prepared[number] = text
    return prepared


def _dehyphen(left: str, right: str) -> tuple[str, str]:
    stripped = left.rstrip()
    broken = _HYPHEN.search(stripped)
    word = _NEXT_WORD.match(right.lstrip())
    if not broken or not word:
        return left, right
    joined = stripped[: broken.start()] + broken.group(1) + word.group(1) + word.group(2)
    return joined, right.lstrip()[word.end() :].lstrip()


def _ends_sentence(text: str) -> bool:
    return bool(_SENTENCE_END.search(text.rstrip()))


def _leading_sentence(text: str) -> str:
    window = text[:SPILL]
    match = _SENTENCE_BREAK.search(window)
    if match:
        return text[: match.end()].strip()
    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).strip()


def _page_label(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"
