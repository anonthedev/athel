"""Instructions for each model call. The graph already chains the steps, so each prompt does one job."""

GAPS = """Split this topic into 5 to 7 questions a researcher can answer from sources.

These questions are the checklist for the rest of the run. Search, reading, and the final report all follow them, and a person will edit them before research starts. Cover the topic. Each question covers a different part. Write the question itself, so a stranger can tell what a good answer contains.

Match the questions to the topic. When the topic asks which option to choose, or compares products, ask which options fit, what they cost and as of when, and which differences decide the choice. When the topic asks what is true, ask what was measured, who reported it, and where sources disagree. Include history, people, ethics, or uses when the topic asks for them. A single page, review, spec sheet, or study should be able to answer each question.

The examples show the shape of a question. The subject comes from the topic.

Buying topic: "Which phones sold in India under ₹20,000 have a rated battery of at least 5000 mAh, and what was the listed price?"
Factual topic: "What daily caffeine intake have regulators and systematic reviews treated as safe for healthy non-pregnant adults, and where do those limits differ?"

Topic:
"""

SEARCH_QUERIES = """Write 3 or 4 web search queries that find a specific source for this question.

A person will run these queries and read the pages they return. Each query is a few distinctive search words. Aim one query at a named study, a review, a spec sheet, or a product listing when the question calls for that kind of page.

Question:
"""

FOLLOWUP_QUERIES = """Write 2 or 3 web search queries that look up only the facts still needed.

The facts already collected are done. These queries exist so the next search can fill what is missing, using the names, dates, models, and terms in those facts. Each query is a few search words.

Question:
"""

MISSING = """List what this question still lacks after the notes below.

The list becomes the next round of searches. Each item is one lookup of ten words or fewer. Return at most 4 items, shortest first. Name the missing study, number, date, price, model, or mechanism.

Put first any part the question already names that no note answers. Then add at most 3 further lookups the notes make necessary, still inside the 4-item cap: a figure with no source, a price with no date, or two notes that disagree and neither names who reported it.

A note answers a part when it states the fact and, where the page gives them, who reported it and the date, price, model, sample, or method. A quiz, a symptom checker, or a page about something else leaves that part open.

Return an empty list when the notes answer the question and no specific fact is still missing. Leave a part missing rather than treating a vague sentence as an answer.

Question:
"""

EXTRACT = """Read this page and keep only the claims that answer the question.

The notes you write are the only record of this page. Later steps never see the page, so a dropped claim is gone and a vague claim cannot be repaired. A claim is one or two sentences and states a checkable fact the question asks for.

Match the fact to the question. A question about what is true needs who reported it, the year, and the sample or method when the page gives them. "4.4%" is incomplete when the page says who measured it and how. A question about a product or a choice needs the model or variant, the price, the date of that price, and the spec or review finding when the page gives them. On a discussion thread, keep a post or comment that states a result, measurement, citation, or firsthand account, and attribute it to the author shown in the text. Leave jokes and reactions out.

Set answers_gap to true and put the claims in note when any claim addresses the question. A partial answer is still true. Include every claim that bears on the question, up to 20, including later results, comparisons, and limits on the page.

Set answers_gap to false, leave note empty, and put the claim in additional when the page does not answer the question but names a study, mechanism, product, or comparison on the same subject.

Leave both fields empty when the page is a quiz, a symptom checker, a paywall notice, or about something else. Leave out any claim the page does not state. When the text has markers like [p.4] or [p.6-7], start that claim with the page, written as (p. 4) or (p. 6-7).

Question:
"""

REPORT = """Write a specific, comprehensive research report in Markdown from the notes below.

A person will read this as the finished piece. The notes are the only facts you may use. Where the notes are silent, say what was not established.

Begin with a # heading of a few words that names the subject. Follow it with a ## Overview of what the topic is and what the notes support. Develop the body in ## sections that fit the topic. Close with a ## Conclusion that draws together what the notes show, including important disagreements and what remained unestablished.

The questions inside the notes are a coverage checklist, not the outline. Choose section headings that fit the topic. Write in prose paragraphs. Use a list or a small table when the notes compare discrete options on the same facts, such as models and prices.

Let the notes decide the shape. When they compare products, prices, and specs, write that comparison and keep each price with its date and variant. When they report studies, write what was measured and keep each figure with the people who measured it. A kept fact looks like this: Simner et al. (2006) found grapheme-color synesthesia in 1.1% of a Scottish sample ([Simner et al., 2006](url-from-the-note)). A sentence that only says the phenomenon is fairly common has lost the fact. The citation URL is the one printed under that note.

When the same person, date, price, or mechanism appears under several questions, place it in the section where it belongs and leave it there. When notes disagree, give each figure with the note that states it. For a partially answered question, write what the notes establish and name the part that is still missing. For a failed question, say briefly that the research did not establish it.

Cite inline with a Markdown link on the sentence the note supports. The link text is the author, paper, product, or publication named in that note. When the note has a URL and no name, use the site name. Use the URL listed under the note the sentence comes from, pasted unchanged, including https:// and the host. End the report on the conclusion.

Bold the key names, models, and dates on first mention.

Topic:
"""


def gaps(topic: str) -> str:
    return GAPS + topic


def search_queries(question: str) -> str:
    return SEARCH_QUERIES + question


def followup_queries(question: str, known: str, needed: str) -> str:
    return (
        f"{FOLLOWUP_QUERIES}{question}\n\n"
        f"Already collected:\n{known}\n\n"
        f"Still needed:\n{needed}"
    )


def missing_parts(question: str, notes: str) -> str:
    return f"{MISSING}{question}\n\nNotes:\n{notes}"


def extract_page(question: str, page: str) -> str:
    return f"{EXTRACT}{question}\n\nPage:\n{page}"


def write_report(topic: str, notes: str, additional: str) -> str:
    return (
        f"{REPORT}{topic}\n\n"
        f"Notes:\n{notes}\n\n"
        "Additional notes, for a study, mechanism, product, or comparison on this topic:\n"
        f"{additional}"
    )
