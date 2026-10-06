import re
from urllib.parse import urlparse

from app.progress import announce
from app.states import OverallState
from app.llm import writer_llm
from app.prompts import write_report

_LINK = re.compile(r"(!?\[[^\[\]]*\]\()([^)\s]+)(\))")


def citation_urls(state: OverallState) -> list[str]:
    found = [note.source for gap in state["gaps"] for note in gap.notes]
    found.extend(item.source for item in state["additional_info"])
    urls = []
    for url in found:
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls


def restore_citation_urls(markdown: str, urls: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        href = match.group(2)
        if href.startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        path = urlparse(href).path or href
        if not path.startswith("/"):
            path = "/" + path
        hits = [
            url for url in urls
            if (urlparse(url).path or "/").rstrip("/") == path.rstrip("/")
        ]
        if len(hits) != 1:
            return match.group(0)
        return f"{match.group(1)}{hits[0]}{match.group(3)}"

    return _LINK.sub(replace, markdown)


def ensure_heading(markdown: str, topic: str) -> str:
    body = markdown.lstrip()
    for line in body.splitlines():
        if not line.strip():
            continue
        if line.strip().startswith("# "):
            return body
        break
    title = " ".join(topic.split()).strip().rstrip(".")
    if not title:
        return body
    return f"# {title}\n\n{body}"


def write_final_report(state: OverallState) -> dict:
    announce("Writing your report")
    checklist = []
    for gap in state["gaps"]:
        notes = "\n".join(
        f"- {note.note}\n  source: {note.source}" for note in gap.notes) or "- No notes found."
        status = "partially answered" if gap.status == "partial" else gap.status
        checklist.append(
            f"## {gap.question}\nStatus: {status}\n\nNotes:\n{notes}"
        )
    extra = "\n".join(f"- {item.note}\n  source: {item.source}" for item in state["additional_info"]) or "- None."

    result = writer_llm().invoke(write_report(state["topic"], "\n".join(checklist), extra))
    markdown = restore_citation_urls(result.content, citation_urls(state))
    return {"final_report": ensure_heading(markdown, state["topic"])}