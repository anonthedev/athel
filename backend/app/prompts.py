"""Instructions for each model call. The graph already chains the steps, so each prompt does one job."""

GAPS = """Split this topic into 10 to 12 short questions a researcher can answer from sources.

These questions are the checklist for the rest of the run. Search, reading, and the final report all follow them, and a person will edit them before research starts. Cover the topic. Each question covers a different part. Write the question itself, so a stranger can tell what a good answer contains.

Each item is one question. One question asks for one fact: one measurement, one limit, one comparison, or one disagreement. End it with a question mark. Leave out a second clause, a colon, and any list of outcomes, populations, routes, or sources. A single page, review, spec sheet, or study should be able to answer it.

Match the questions to the topic. When the topic asks which option to choose, or compares products, give the options, the price, and the deciding difference each their own question. When the topic asks what is true, give what was measured, who reported it, and where sources disagree each their own question. Include history, people, ethics, or uses when the topic asks for them.

The examples show the shape of a question. The subject comes from the topic.

Buying topic: "Which phones sold in India under ₹20,000 list a battery of at least 5000 mAh?"
Factual topic: "What daily caffeine limit do regulators set for healthy non-pregnant adults?"
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

READERS = """Read one URL and extract claims based on the question.

Call the reader that matches the URL. If it returns no text, call trafilatura. Call python_scraping only when trafilatura also returns no text.

pubmed reads a PubMed, PMC, or Europe PMC article.
doi reads a doi.org link or a publisher article page.
reddit reads a Reddit thread.
substack reads a Substack post, including a post on the publication's own domain whose path contains /p/.
trafilatura reads any other page or PDF.
python_scraping runs one Python script you write. It returns only what that script prints.

The source you pass is the whole script.py file. Do not wrap it in markdown fences or add a comment outside the program.

The script gets the text of the URL in the user message and prints that text. Put the URL in the script as a string. The process does not pass it as an argument.

Use whatever approach reaches the content. Send a browser User-Agent. Download the URL. If the response is a 404, a block page, or a shell with no article, request that site's public JSON API for the same item and read the JSON. A crates.io page https://crates.io/crates/<name> is served at https://crates.io/api/v1/crates/<name>. Print the description and the version as plain sentences.

Import whatever library that approach needs. A missing library is installed into the current directory, the only writable place, and the script runs again. Do not install it anywhere else.

print() the article text once, with no log lines, labels, or JSON around it. Do not print the empty shell. The script finishes on its own and does not wait for input.

If the script returns no text, stop. Extract only from text a reader returned.

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


def scrape_instructions() -> str:
    return READERS + EXTRACT.removesuffix("Question:\n")


def write_report(topic: str, notes: str, additional: str) -> str:
    return (
        f"{REPORT}{topic}\n\n"
        f"Notes:\n{notes}\n\n"
        "Additional notes, for a study, mechanism, product, or comparison on this topic:\n"
        f"{additional}"
    )
