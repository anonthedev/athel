"""Instructions for each model call. The graph already chains the steps, so each prompt does one job."""

GAPS = """Split this topic into 10 to 12 short questions a researcher can answer from sources.

These questions are the checklist for the rest of the run. Search, reading, and the final report all follow them, and a person will edit them before research starts. Cover the topic. Each question covers a different part. Write the question itself, so a stranger can tell what a good answer contains.

Each item is one question. One question asks for one fact: one measurement, one limit, one comparison, or one disagreement. End it with a question mark. Leave out a second clause, a colon, and any list of outcomes, populations, routes, or sources. A single page, review, spec sheet, or study should be able to answer it.

Match the questions to the topic. When the topic asks which option to choose, or compares products, give the options, the price, and the deciding difference each their own question. When the topic asks what is true, give what was measured, who reported it, and where sources disagree each their own question. Include history, people, ethics, or uses when the topic asks for them.

The examples show the shape of a question. The subject comes from the topic.

Buying topic: "Which phones sold in India under ₹20,000 list a battery of at least 5000 mAh?"
Factual topic: "What daily caffeine intake limit do regulators set for healthy non-pregnant adults?"
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

EXTRACT = """Read this page and extract claims based on the question.

A claim is 1-2 sentences and states a checkable fact. When extracting, include who reported it, the year, and the sample/method when provided. When the text has markers like [p.4], start that claim with (p. 4). 

STRICT EXTRACTION RULES:
1. Ignore Meta-Text: If a sentence states that the page does not contain the answer, lacks a number, or cannot answer the question (e.g., "This page does not give a regulatory daily limit"), IGNORE IT. Do not extract it into any field. Do not write "the page does not state it".
2. No Inventions: Never invent numbers, dates, or sample sizes. Only use what the text states.

EVALUATE AND OUTPUT BASED ON THESE EXACT CONDITIONS:

CONDITION A: The page CONTAINS the answer to the question (even partially).
* answers_gap: true
* note: Extract the claims that answer the question.
* additional: Leave empty.

CONDITION B: The page DOES NOT contain the answer, BUT it states a related claim: a result, mechanism, product fact, or comparison about the same subject.
A name, a year, or a paper title is not a claim. A reference entry that only cites a paper states nothing the report can use, so leave both fields empty.
* answers_gap: false
* note: LEAVE COMPLETELY EMPTY.
* additional: Extract ONLY the sentence that states the related claim. 

CONDITION C: The page is completely irrelevant (a quiz, a paywall, or a different subject that only reuses the question's words). Do not copy it into additional.
* answers_gap: false
* note: Leave empty.
* additional: Leave empty.

Question:
"""

REPORT = """Write an evidence-led, publication-quality research report in Markdown.

The reader should receive a finished article, not a transcript of the research process. The supplied material is the complete evidence base: use no outside facts. Never refer to "the notes", "the checklist", extraction, search rounds, or the writer's instructions.

SYNTHESIZE BEFORE WRITING
- Silently merge duplicate claims, repeated search results, and preprint/published/repository versions of the same study.
- Organize around findings and arguments, not around the source order or the research questions.
- A fact may appear twice only when each occurrence establishes a genuinely different point. The same evidence may support different arguments, but do not restate the same claim merely with a new citation or wording.
- Prefer the strongest direct source for a claim. Do not add blogs or news articles as extra corroboration when a paper, official source, or primary record already supports it.
- There is no target word count. Include every material finding once, explain it fully, and stop. Never pad the report with source-by-source summaries, repeated background, or a conclusion that retells the body.

STRUCTURE AND ARGUMENT
- Begin with a short # title.
- Open with a ## Overview that gives the central answer and why it matters. It is not a table of contents and must not list every section or every unanswered question.
- Build a coherent body with descriptive ## headings chosen for this topic. Each paragraph should make one clear point, present the best evidence, explain its significance, and transition naturally to the next point.
- Distinguish observation, experimental result, interpretation, and hypothesis. State what was measured or compared, in which population/model, and by whom when the material provides it.
- When sources disagree, state the disagreement precisely and explain what evidence supports each side. Do not manufacture consensus.
- Mention a meaningful limitation or unresolved point where it affects the relevant claim. Gather only substantial remaining gaps in one brief final limitations section if needed; do not repeat them in the overview, body, and conclusion.
- End with a concise ## Conclusion that answers "What follows from this evidence?" It should synthesize implications and uncertainty, not summarize each preceding section.

EVIDENCE AND CITATIONS
- Preserve concrete numbers, dates, variants, samples, methods, and comparisons. For example: Simner et al. (2006) found grapheme-color synesthesia in 1.1% of a Scottish sample ([Simner et al., 2006](url-from-the-note)).
- Cite inline on the sentence the source supports. Use the exact source URL supplied with that claim.
- Use useful link text: author and year, paper title, product, or publication. Do not use generic labels such as "source", "PubMed", "PMC", or "doi.org" when the material names the work or author.
- One strong citation is enough for one claim. Add another only when it contributes independent evidence, a different population, or a meaningful disagreement.
- Never combine a claim with a citation that does not support it. Where the evidence is silent, say once and plainly that the available sources did not establish the point.

EDITORIAL STANDARD
- Write precise, fluent English with varied sentence structure and strong transitions. Prefer concrete verbs and direct sentences over throat-clearing, inflated phrasing, and strings of qualifications.
- Avoid canned phrases such as "it is important to note", "the evidence collectively suggests", and "further research is needed" unless the supplied evidence makes the exact statement necessary.
- Define specialist terms on first use. Keep technical detail when it carries meaning; do not make academic prose needlessly difficult.
- Bold only a few terms that genuinely aid scanning, and only on first mention.
- Proofread the final answer for duplicated claims, grammar, malformed words, inconsistent dates, and citation quality. Write entirely in English.

Writing style:
"""

_TONE = {
    "clear": (
        "Clear and accessible. Use plain, confident language for an informed general reader. "
        "Explain technical terms briefly and retain all important nuance and evidence."
    ),
    "academic": (
        "Academic. Use formal scholarly prose and field-appropriate terminology for a specialist reader, "
        "while remaining concise, readable, and free of needless jargon."
    ),
}


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


def write_report(topic: str, notes: str, additional: str, tone: str = "clear") -> str:
    style = _TONE.get(tone, _TONE["clear"])
    return (
        f"{REPORT}{style}\n\n"
        f"Topic:\n{topic}\n\n"
        f"Evidence grouped by coverage question:\n{notes}\n\n"
        "Additional evidence relevant to the topic:\n"
        f"{additional}"
    )
