from contextvars import ContextVar, Token

from app.states import OverallState, UrlHit, Finding
from app.llm import extractor_llm
from pydantic import BaseModel
from langgraph.types import Send
from trafilatura import fetch_url, extract
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from tavily import TavilyClient
from urllib.parse import urlparse

_tavily_key: ContextVar[str] = ContextVar("tavily_api_key", default="")


def use_tavily_key(api_key: str) -> Token:
    return _tavily_key.set(api_key.strip())


def reset_tavily_key(token: Token) -> None:
    _tavily_key.reset(token)


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")

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

    downloaded = fetch_url(state["url"])
    if not downloaded:
        domain = host_of(state["url"])
        return {"dead_urls": [state["url"]], "blocked_domains": [domain], "findings": []}

    text = extract(downloaded, url=state["url"]) or ""

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
Page:
{text[:12000]}"""
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
                source=state["url"],
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