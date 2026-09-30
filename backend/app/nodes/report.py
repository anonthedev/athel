import re
from urllib.parse import urlparse

from app.states import OverallState
from app.llm import writer_llm

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


def write_final_report(state: OverallState) -> dict:
    checklist = []
    for gap in state["gaps"]:
        notes = "\n".join(
        f"- {note.note}\n  source: {note.source}" for note in gap.notes) or "- No notes found."
        status = "partially answered" if gap.status == "partial" else gap.status
        checklist.append(
            f"## {gap.question}\nStatus: {status}\n\nNotes:\n{notes}"
        )
    extra = "\n".join(f"- {item.note}\n  source: {item.source}" for item in state["additional_info"]) or "- None."

    prompt = f"""Write a specific, direct, and comprehensive research report in Markdown.

Specific: every name, date, and number stays attached to the study or page that reported it.
Direct: a paragraph states the finding, then the evidence.
Comprehensive: every part of the topic that the dossier covers appears once, in the section where it belongs.

Topic:
{state["topic"]}

Evidence dossier:
{chr(10).join(checklist)}

Additional information:
{extra}

The dossier questions are a coverage checklist, not the outline. Choose headings that fit the topic. Write one continuous report in prose. Use a bullet list only for a real set of mechanisms, types, or limits.

State each fact once. When the same person, date, or mechanism appears under several questions, put it in the section where it belongs.

Keep the concrete details from the notes: names, dates, paper titles, sample sizes, methods, organizations, and numbers. "Simner et al. 2006 found 4.4% in a Scottish sample" must not become "synesthesia is fairly common."

Use only facts from the dossier. Do not round a date, move an event to a different year, or add a fact you were not given. When notes disagree, give the range and attach each figure to the note that states it. Do not average them. For a partially answered question, write what the notes establish and name the part that is still missing. For a failed question, which has no notes, say briefly that the research did not establish it.

Prefer a note that names a study, author, or dataset over a clinic page, wellness blog, or marketing page. Do not give a commercial coping list its own section. Use additional information only when it names a study or mechanism on this topic. Ignore navigation text, browser checks, paywalls, quizzes, and unrelated pages.

Cite inline with a Markdown link. The link text is the author, paper, or publication named in that note. It is never the word "source". If the note has a URL and no name, use the site name. Use only a URL listed under the note the sentence comes from. That page must support that sentence. Do not point two unrelated claims at the same page, and do not add a source list at the end.

Citation form, using the note's own URL: Grapheme-color synesthesia affects about 1.1% of people ([Simner et al., 2006](url-from-the-note)). Paste that URL unchanged, including https:// and the host. A path such as /images/file.pdf is invalid.

Use ## headings. Bold the key names and dates on first mention."""

    result = writer_llm().invoke(prompt)
    return {"final_report": restore_citation_urls(result.content, citation_urls(state))}