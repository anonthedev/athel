from app.states import OverallState, UrlHit, Finding
from app.llm import extractor_llm
from pydantic import BaseModel
from langgraph.types import Send
from trafilatura import fetch_url, extract
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from urllib.parse import urlparse

def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")

def search(state: dict) -> dict:
    try:
        found = list(DDGS().text(state["query"], max_results=5))
    except DDGSException:
        found = []
    urls = list(dict.fromkeys(hit["href"] for hit in found))[:5]
    blocked = set(state.get("blocked_domains", []))
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
        
    result = extractor_llm.with_structured_output(PageResult, include_raw=True).invoke(
        f"""Read this page and decide if it answers the question.
Question:
{state["question"]}
Rules:
- If it answers the question, set answers_gap to true and put only the relevant facts, names, and dates in note.
- If it does not answer the question but contains useful facts about the broader topic, set answers_gap to false, leave note empty, and put those facts in additional.
- If the page states facts that address any part of the question, set answers_gap to true and put only those facts in note.
- A partial answer is still true. Do not require the page to cover the whole question.
- If it does not address the question but has useful facts on the broader topic, set answers_gap to false, leave note empty, and put those facts in additional.
- If it is navigation, ads, or unrelated, set answers_gap to false and leave both note and additional empty.
- Keep note and additional under 200 words.
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