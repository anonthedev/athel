from app.states import OverallState
from app.llm import writer_llm

def write_final_report(state: OverallState) -> dict:
    checklist = []
    for gap in state["gaps"]:
        notes = "\n".join(
        f"- {note.note}\n  source: {note.source}" for note in gap.notes) or "- No notes found."
        checklist.append(
            f"## {gap.question}\nStatus: {gap.status}\n\nNotes:\n{notes}"
        )
    extra = "\n".join(f"- {item.note}\n  source: {item.source}" for item in state["additional_info"]) or "- None."

    prompt = f"""Write a publication-ready research report in Markdown.

Topic:
{state["topic"]}

Evidence dossier:
{chr(10).join(checklist)}

Additional information:
{extra}

The dossier questions are a coverage checklist, not the outline. Do not use those questions as headings, and do not answer them one by one. Choose section headings that fit this topic. Write one continuous report in prose, with bullets only for a genuine list of mechanisms, applications, or limits.

State each fact once. When the same person, date, or mechanism appears under several questions, put it in the section where it belongs and do not repeat it later.

Keep the concrete details from the notes: names, dates, paper and model titles, algorithms, organizations, products, and numbers. Do not replace a specific fact with a general sentence. "AlexNet won ImageNet in 2012" must not become "deep learning later improved image recognition." If a note gives SkinVision, IBM Watson, a percentage, or a dollar figure, that detail belongs in the report.

Use only facts from the dossier. Do not round a date, move an event to a different year, or fill a gap with a fact you were not given. If two notes disagree, keep the version tied to a source and do not blend them. For a failed question, say briefly that the research did not establish it. Use additional information only when it clearly supports the topic. Ignore navigation text, browser checks, paywalls, and unrelated pages.

Cite inline with a Markdown link, and use only a URL listed under the note the sentence comes from. The link must support that sentence. Do not point two unrelated claims at the same page, and do not add a source list at the end.

Use ## headings. Bold the key names and dates on first mention."""

    result = writer_llm.invoke(prompt)
    return {"final_report": result.content}