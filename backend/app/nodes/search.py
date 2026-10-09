from contextvars import ContextVar, Token
import re
from app.states import OverallState, UrlHit, Finding
from app.llm import extractor_llm
from app.prompts import extract_page
from app.usage import UnreadableModel, collect_calls, structured
from pydantic import BaseModel
from langgraph.types import Send
from trafilatura import extract
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from tavily import TavilyClient
from urllib.parse import urljoin, urlparse
from app.helper.pdf import embedding_configured, pdf_excerpt
from app.helper.sources import load_specialized, load_specialized_html
from app.helper.sources.doi import doi_from_url, excerpt_pdf, load_work, with_excerpt, work_id_from_url, work_urls
from app.helper.sources.http import get as http_get
from app.helper.sources.wikipedia import article_url, citation_links, matches as wikipedia_page
from app.nodes.planning import topic_of_collapse

_tavily_key: ContextVar[str] = ContextVar("tavily_api_key", default="")
HTML_LIMIT = 12_000
PAGE_LIMIT = 20_000_000
_BROWSER = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def fetch_page(url: str):
    # Trafilatura retries 429 and sleeps for Retry-After. Pathology Outlines
    # sends Retry-After: 86400, which holds the whole research wave for a day.
    return http_get(
        url,
        headers={"User-Agent": _BROWSER, "Accept": "text/html,application/pdf,*/*"},
        timeout=20,
        max_bytes=PAGE_LIMIT,
    )


def use_tavily_key(api_key: str) -> Token:
    return _tavily_key.set(api_key.strip())


def reset_tavily_key(token: Token) -> None:
    _tavily_key.reset(token)


_SKIP_HOSTS = ("researchgate.net", "sciencedirect.com")


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def skipped_host(url: str) -> bool:
    host = host_of(url)
    return any(host == name or host.endswith("." + name) for name in _SKIP_HOSTS)


def landed_url(requested: str, returned: str | bytes | None) -> str:
    if isinstance(returned, bytes):
        returned = returned.decode("utf-8", errors="replace")
    candidate = (returned or "").strip()
    if not candidate:
        return requested
    absolute = urljoin(requested, candidate)
    parsed = urlparse(absolute)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return absolute
    return requested

def is_pdf(data: bytes) -> bool:
    head = data[:1024]
    stripped = head.lstrip(b"\xef\xbb\xbf\x00 \t\r\n")
    if stripped.startswith(b"%PDF-"):
        return True
    return b"%PDF-" in head

def load_text(url: str, question: str) -> tuple[str, str] | None:
    specialized = load_specialized(url, question)
    if specialized is not None:
        return specialized

    response = fetch_page(url)
    if response is None or response.status != 200 or not response.data:
        return None
    source = landed_url(url, response.url)
    if is_pdf(response.data):
        return pdf_excerpt(response.data, question), source

    html = response.data.decode("utf-8", errors="replace")
    specialized = load_specialized_html(source, html, question)
    if specialized is not None:
        return specialized
    text = extract(html, url=source) or ""
    pdf_url = citation_pdf_url(html, source)
    if pdf_url and pdf_url != source and embedding_configured():
        hopped = fetch_page(pdf_url)
        if hopped and hopped.status == 200 and hopped.data and is_pdf(hopped.data):
            excerpt = pdf_excerpt(hopped.data, question)
            if excerpt:
                return excerpt, landed_url(pdf_url, hopped.url)
    return text[:HTML_LIMIT], source

def citation_pdf_url(html: str, source: str) -> str | None:
    for tag in re.finditer(r"<meta\b[^>]*>", html, re.I):
        raw = tag.group(0)
        if not re.search(r"name\s*=\s*['\"]citation_pdf_url['\"]", raw, re.I):
            continue
        content = re.search(r"content\s*=\s*['\"]([^'\"]+)['\"]", raw, re.I)
        if content:
            return urljoin(source, content.group(1).strip())
    return None


def duckduckgo_urls(query: str) -> list[str]:
    try:
        found = list(DDGS().text(query, max_results=5))
    except DDGSException:
        found = []
    return list(dict.fromkeys(hit["href"] for hit in found if hit.get("href")))[:5]

def tavily_urls(query: str, blocked: set[str]) -> list[str]:
    api_key = _tavily_key.get()
    if not api_key:
        raise RuntimeError("Add a Tavily API key")
    response = TavilyClient(api_key=api_key).search(
        query=query,
        search_depth="advanced",
        max_results=5,
        include_answer=False,
        exclude_domains=sorted(set(blocked).union(_SKIP_HOSTS))[:150],
    )
    found = response.get("results", []) if isinstance(response, dict) else []
    urls = [item["url"] for item in found if isinstance(item, dict) and isinstance(item.get("url"), str)]
    return list(dict.fromkeys(urls))[:5]

def search(state: dict) -> dict:
    blocked = set(state.get("blocked_domains", []))
    if state.get("search_engine") == "duckduckgo":
        urls = duckduckgo_urls(state["query"])
    else:
        urls = tavily_urls(state["query"], blocked)
    urls = [url for url in urls if host_of(url) not in blocked and not skipped_host(url)]
    known = {doi for url in urls if (doi := doi_from_url(url))}
    for url in work_urls(state["query"], known):
        if url not in urls and host_of(url) not in blocked and not skipped_host(url):
            urls.append(url)
    topic = topic_of_collapse(state.get("question") or "")
    if topic:
        wiki = article_url(topic)
        if wiki and wiki not in urls and host_of(wiki) not in blocked and not skipped_host(wiki):
            urls.append(wiki)

    return {
        "hits": [
            UrlHit(gap_id=state["gap_id"], question=state["question"], url=url)
            for url in urls
        ]
    }

class PageResult(BaseModel):
    answers_gap: bool
    note: str
    additional: str = ""


def read_page(question: str, text: str, source: str, gap_id: int) -> Finding | None:
    try:
        parsed = structured(
            extractor_llm(),
            PageResult,
            extract_page(question, text),
            role="extractor",
            label=source,
        )
    except UnreadableModel:
        return None
    if not parsed.note.strip() and not parsed.additional.strip():
        return None
    return Finding(
        gap_id=gap_id,
        answers_gap=parsed.answers_gap and bool(parsed.note.strip()),
        note=parsed.note.strip(),
        source=source,
        additional=parsed.additional.strip(),
    )


def visited(state: dict, source: str) -> Finding:
    return Finding(gap_id=state["gap_id"], answers_gap=False, note="", source=source)


def scrape(state: dict) -> dict:
    with collect_calls() as recorded:
        if wikipedia_page(state["url"]):
            return scrape_wikipedia(state, recorded)
        if work_id_from_url(state["url"]):
            return scrape_work(state, recorded)
        loaded = load_text(state["url"], state["question"])
        if loaded is None:
            return {
                "dead_urls": [state["url"]],
                "findings": [],
                "calls": list(recorded),
            }
        text, source = loaded
        if not text:
            return {"findings": [], "calls": list(recorded)}
        findings = []
        finding = read_page(state["question"], text, source, state["gap_id"])
        if finding is not None:
            findings.append(finding)
        if source != state["url"]:
            findings.append(visited(state, state["url"]))
        return {"findings": findings, "calls": list(recorded)}


def scrape_work(state: dict, recorded: list) -> dict:
    loaded = load_work(state["url"], state["question"])
    if loaded is None:
        return {"dead_urls": [state["url"]], "findings": [], "calls": list(recorded)}
    text, source, pdf_url = loaded
    finding = read_page(state["question"], text, source, state["gap_id"])
    if finding is None:
        return {"findings": [visited(state, state["url"])], "calls": list(recorded)}
    if pdf_url:
        excerpt = excerpt_pdf(pdf_url, state["question"])
        if excerpt:
            fuller = read_page(state["question"], with_excerpt(text, excerpt), source, state["gap_id"])
            if fuller is not None:
                finding = fuller
    return {"findings": [finding, visited(state, state["url"])], "calls": list(recorded)}


def scrape_wikipedia(state: dict, recorded: list) -> dict:
    response = fetch_page(state["url"])
    if response is None or response.status != 200 or not response.data:
        return {"dead_urls": [state["url"]], "findings": [], "calls": list(recorded)}
    page = landed_url(state["url"], response.url)
    html = response.data.decode("utf-8", errors="replace")
    findings = [visited(state, state["url"])]
    dead = []
    for link in citation_links(html, page):
        if skipped_host(link):
            continue
        loaded = load_text(link, state["question"])
        if loaded is None:
            dead.append(link)
            continue
        text, source = loaded
        if not text:
            continue
        finding = read_page(state["question"], text, source, state["gap_id"])
        if finding is not None:
            findings.append(finding)
    return {
        "findings": findings,
        "dead_urls": dead,
        "calls": list(recorded),
    }


def fan_out_scrapes(state: OverallState):
    seen = {(finding.gap_id, finding.source) for finding in state["findings"]}
    sends = []
    dead = set(state.get("dead_urls", []))
    blocked = set(state.get("blocked_domains", []))

    for hit in state["hits"]:
        key = (hit.gap_id, hit.url)
        if key in seen:
            continue
        seen.add(key)
        if hit.url in dead or host_of(hit.url) in blocked or skipped_host(hit.url):
            continue
        sends.append(Send("scrape", {"gap_id": hit.gap_id, "question": hit.question, "url": hit.url}))
    if sends:
        return sends
    return "update_checklist"