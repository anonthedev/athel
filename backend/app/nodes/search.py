from contextvars import ContextVar, Token
import re
from app.states import OverallState, UrlHit, Finding
from app.llm import extractor_llm
from pydantic import BaseModel
from langgraph.types import Send
from trafilatura import fetch_response, extract
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from tavily import TavilyClient
from urllib.parse import urljoin, urlparse
from app.helper.pdf import pdf_excerpt

_tavily_key: ContextVar[str] = ContextVar("tavily_api_key", default="")
HTML_LIMIT = 12_000


def use_tavily_key(api_key: str) -> Token:
    return _tavily_key.set(api_key.strip())


def reset_tavily_key(token: Token) -> None:
    _tavily_key.reset(token)


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


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
    response = fetch_response(url)
    if response is None or response.status != 200 or not response.data:
        return None
    source = landed_url(url, response.url)
    if is_pdf(response.data):
        return pdf_excerpt(response.data, question), source

    html = response.data.decode("utf-8", errors="replace")
    text = extract(html, url=source) or ""
    pdf_url = citation_pdf_url(html, source)
    if pdf_url and pdf_url != source:
        hopped = fetch_response(pdf_url)
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
        exclude_domains=sorted(blocked)[:150],
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
    urls = [url for url in urls if host_of(url) not in blocked]

    return {
        "hits": [
            UrlHit(gap_id=state["gap_id"], question=state["question"], url=url)
            for url in urls
        ]
    }

def scrape(state: dict) -> dict:
    class PageResult(BaseModel):
        answers_gap: bool
        note: str
        additional: str = ""

    loaded = load_text(state["url"], state["question"])
    if loaded is None:
        domain = host_of(state["url"])
        return {"dead_urls": [state["url"]], "blocked_domains": [domain], "findings": []}
    text, source = loaded
    if not text:
        return {"findings": []}

    result = extractor_llm().with_structured_output(PageResult, include_raw=True).invoke(
        f"""Keep only claims from this page that bear on the question.
Question:
{state["question"]}
Rules:
- A claim states the fact and, when the page gives them, who reported it, the year, and the sample or method. "4.4%" is incomplete when the page says who measured it and how.
- If any claim addresses the question, set answers_gap to true and put those claims in note. A partial answer is still true.
- If the page does not address the question but names a study or mechanism on this same subject, set answers_gap to false, leave note empty, and put those claims in additional.
- If the page is a quiz, symptom checker, ad, forum, AI encyclopedia, or about something else, set answers_gap to false and leave both fields empty.
- At most 8 claims. Each claim is one or two sentences.
- When the text has markers like [p.4] or [p.6-7], start each claim with that page, written as (p. 4) or (p. 6-7).
Page:
{text}"""
    )
    
    if result["parsing_error"] or result["parsed"] is None:
        return {"findings": []}

    parsed = result["parsed"]

    if not parsed.note.strip() and not parsed.additional.strip():
        return {"findings": []}

    return {
        "findings": [
            Finding(
                gap_id=state["gap_id"],
                answers_gap=parsed.answers_gap and bool(parsed.note.strip()),
                note=parsed.note.strip(),
                source=source,
                additional=parsed.additional.strip(),
            )
        ]
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
        if hit.url in dead or host_of(hit.url) in blocked:
            continue
        sends.append(Send("scrape", {"gap_id": hit.gap_id, "question": hit.question, "url": hit.url}))
    if sends:
        return sends
    return "update_checklist"