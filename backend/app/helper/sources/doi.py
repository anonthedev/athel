import json
import re
from urllib.parse import quote, unquote, urlparse

from app.helper.sources.http import TEXT_LIMIT, Response, get

_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
_META = re.compile(
    r"citation_doi|dc\.identifier|prism\.doi",
    re.I,
)
_VERSION_RANK = {"publishedVersion": 0, "acceptedVersion": 1, "submittedVersion": 2}


def matches(url: str) -> bool:
    return doi_from_url(url) is not None


def load(url: str, question: str, *, fetch=get) -> tuple[str, str] | None:
    doi = doi_from_url(url)
    if not doi:
        return None
    return resolve(doi, question, fetch)


def load_html(url: str, html: str, question: str, *, fetch=get) -> tuple[str, str] | None:
    if doi_from_url(url):
        return None
    doi = doi_from_html(html)
    if not doi:
        return None
    return resolve(doi, question, fetch)


def doi_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"doi.org", "dx.doi.org"}:
        return find_doi(unquote(parsed.path))
    return find_doi(unquote(parsed.path + "?" + parsed.query))


def doi_from_html(html: str) -> str | None:
    for tag in re.finditer(r"<meta\b[^>]*>", html[:200_000], re.I):
        raw = tag.group(0)
        if not _META.search(raw):
            continue
        content = re.search(r"content\s*=\s*['\"]([^'\"]+)['\"]", raw, re.I)
        if content:
            doi = find_doi(content.group(1))
            if doi:
                return doi
    return None


def find_doi(value: str) -> str | None:
    match = _DOI.search(unquote(value).strip())
    if not match:
        return None
    return match.group(0).rstrip(".,);")


def work_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in {"openalex.org", "api.openalex.org"}:
        return None
    match = re.search(r"(W\d+)", parsed.path)
    return match.group(1) if match else None


def page_url(work: dict) -> str:
    match = re.search(r"(W\d+)", str(work.get("id") or ""))
    if not match:
        return ""
    return f"https://openalex.org/{match.group(1)}"


def search_works(query: str, fetch=get, limit: int = 3) -> list[dict]:
    query = " ".join(query.split())
    if not query:
        return []
    url = f"https://api.openalex.org/works?search={quote(query)}&per-page={limit}"
    payload = _json(fetch(url, headers={"Accept": "application/json"}))
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    works = []
    for work in results:
        if not isinstance(work, dict):
            continue
        if not abstract_text(work.get("abstract_inverted_index")):
            continue
        if not page_url(work):
            continue
        works.append(work)
    return works


def work_urls(query: str, known_dois: set[str], fetch=get) -> list[str]:
    urls = []
    for work in search_works(query, fetch=fetch):
        doi = find_doi(str(work.get("doi") or ""))
        if doi and doi in known_dois:
            continue
        page = page_url(work)
        if page and page not in urls:
            urls.append(page)
    return urls


def load_work(url: str, question: str, fetch=get) -> tuple[str, str, str] | None:
    del question
    work_id = work_id_from_url(url)
    if not work_id:
        return None
    work = _openalex_id(work_id, fetch)
    if not isinstance(work, dict):
        return None
    text = render_work(work)
    if not text:
        return None
    doi = find_doi(str(work.get("doi") or ""))
    source = f"https://doi.org/{doi}" if doi else f"https://openalex.org/{work_id}"
    return text, source, choose_pdf(work.get("locations") or [])


def with_excerpt(text: str, excerpt: str) -> str:
    if not excerpt:
        return text
    room = TEXT_LIMIT - len(text) - 2
    if room <= 400:
        return text
    return _clip(f"{text}\n\n{excerpt[:room].rstrip()}")


def excerpt_pdf(pdf_url: str, question: str, fetch=get) -> str:
    return _pdf_excerpt(pdf_url, question, fetch)


def resolve(doi: str, question: str, fetch) -> tuple[str, str] | None:
    work = _openalex(doi, fetch)
    if not isinstance(work, dict):
        return None
    text = render_work(work)
    pdf_url = choose_pdf(work.get("locations") or [])
    excerpt = _pdf_excerpt(pdf_url, question, fetch) if pdf_url else ""
    if excerpt:
        room = TEXT_LIMIT - len(text) - 2
        text = f"{text}\n\n{excerpt[:room].rstrip()}" if room > 400 else text
    text = _clip(text)
    if not text:
        return None
    return text, f"https://doi.org/{doi}"


def render_work(work: dict) -> str:
    title = " ".join(str(work.get("title") or work.get("display_name") or "").split())
    authors = _authors(work)
    journal = _journal(work)
    year = work.get("publication_year")
    doi = find_doi(str(work.get("doi") or "")) or ""
    abstract = abstract_text(work.get("abstract_inverted_index"))
    if not title and not abstract:
        return ""
    lines = []
    if title:
        lines.append(f"Title: {title}")
    if authors:
        lines.append(f"Authors: {authors}")
    if journal and year:
        lines.append(f"Journal: {journal} ({year})")
    elif journal:
        lines.append(f"Journal: {journal}")
    if doi:
        lines.append(f"DOI: {doi}")
    if abstract:
        lines.append("")
        lines.append("Abstract")
        lines.append(abstract)
    return "\n".join(lines).strip()


def abstract_text(index) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    size = 0
    for positions in index.values():
        if not isinstance(positions, list):
            continue
        numbers = [position for position in positions if isinstance(position, int)]
        if numbers:
            size = max(size, max(numbers) + 1)
    if size == 0:
        return ""
    words = [""] * size
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and 0 <= position < size:
                words[position] = str(word)
    return " ".join(word for word in words if word)


def choose_pdf(locations: list) -> str:
    ranked: list[tuple[int, int, str]] = []
    for index, location in enumerate(locations):
        if not isinstance(location, dict):
            continue
        pdf_url = str(location.get("pdf_url") or "").strip()
        if not pdf_url.startswith(("http://", "https://")):
            continue
        rank = _VERSION_RANK.get(str(location.get("version") or ""), 3)
        ranked.append((rank, index, pdf_url))
    if not ranked:
        return ""
    ranked.sort()
    return ranked[0][2]


def _openalex(doi: str, fetch) -> dict | None:
    url = f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='')}"
    return _work(fetch(url, headers={"Accept": "application/json"}))


def _openalex_id(work_id: str, fetch) -> dict | None:
    return _work(fetch(f"https://api.openalex.org/works/{work_id}", headers={"Accept": "application/json"}))


def _work(response: Response | None) -> dict | None:
    payload = _json(response)
    if not isinstance(payload, dict):
        return None
    if payload.get("title") or payload.get("display_name"):
        return payload
    return None


def _pdf_excerpt(pdf_url: str, question: str, fetch) -> str:
    from app.helper.pdf import embedding_configured, pdf_excerpt

    if not embedding_configured():
        return ""
    response = fetch(pdf_url, headers={"Accept": "application/pdf"})
    if response is None or response.status != 200 or not response.data or not _is_pdf(response.data):
        return ""
    return pdf_excerpt(response.data, question)


def _authors(work: dict) -> str:
    names = []
    for authorship in work.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        name = str(author.get("display_name") or "").strip()
        if name:
            names.append(name)
    if len(names) > 8:
        return ", ".join(names[:8]) + ", et al."
    return ", ".join(names)


def _journal(work: dict) -> str:
    location = work.get("primary_location") or {}
    if not isinstance(location, dict):
        return ""
    source = location.get("source") or {}
    if not isinstance(source, dict):
        return ""
    return str(source.get("display_name") or "").strip()


def _json(response: Response | None):
    if response is None or response.status != 200 or not response.data:
        return None
    try:
        return json.loads(response.data.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _is_pdf(data: bytes) -> bool:
    head = data[:1024]
    stripped = head.lstrip(b"\xef\xbb\xbf\x00 \t\r\n")
    return stripped.startswith(b"%PDF-") or b"%PDF-" in head


def _clip(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= TEXT_LIMIT:
        return text
    cut = text.rfind("\n", 0, TEXT_LIMIT)
    if cut < TEXT_LIMIT // 2:
        cut = TEXT_LIMIT
    return text[:cut].rstrip()
