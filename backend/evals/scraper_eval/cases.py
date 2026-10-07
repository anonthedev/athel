from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    url: str
    calls: tuple[str, ...]
    text: str = ""
    source: str = ""
    via: str = ""
    decoy: str = ""
    fetch: bool = False
    dead: bool = False
    script: bool = False
    answers_gap: bool = True
    note_groups: tuple[tuple[str, ...], ...] = ()
    additional_must_be_empty: bool = True


CASES = (
    Case(
        id="pubmed",
        question="What drop in weekly migraine days did the 2021 trial report?",
        url="https://pubmed.ncbi.nlm.nih.gov/35918411/",
        calls=("pubmed",),
        via="pubmed",
        text="The 2021 migraine trial enrolled 412 adults. Weekly migraine days fell by 27%.",
        note_groups=(("27%", "27 percent"), ("2021",)),
    ),
    Case(
        id="doi",
        question="What median daily sitting time did Lovelace and Turing measure in 2019?",
        url="https://doi.org/10.1038/s41586-021-03819-2",
        calls=("doi",),
        via="doi",
        text="Lovelace and Turing (2019) measured a median daily sitting time of 9.4 hours in office workers.",
        note_groups=(("9.4",), ("2019",)),
    ),
    Case(
        id="reddit",
        question="After the 3 March 2024 firmware update, how many seconds did startup take?",
        url="https://www.reddit.com/r/hardware/comments/ab12cd/firmware_notes/",
        calls=("reddit",),
        via="reddit",
        text="The original poster said the firmware update on 3 March 2024 cut startup from 40 seconds to 12 seconds.",
        note_groups=(("12 seconds", "12s"),),
    ),
    Case(
        id="substack",
        question="What price did the 12 May 2025 letter give for the summit ticket?",
        url="https://www.lennysnewsletter.com/p/summit",
        calls=("substack",),
        via="substack",
        text="The 12 May 2025 letter priced the summit ticket at $640.",
        note_groups=(("640",),),
    ),
    Case(
        id="page",
        question="What adult ferry fare did the city registry list for 2022?",
        url="https://example.com/registry/ferry",
        calls=("trafilatura",),
        via="trafilatura",
        text="The city registry lists the 2022 adult ferry fare as €4.50.",
        note_groups=(("4.50", "4,50"), ("2022",)),
    ),
    Case(
        id="publisher",
        question="What hazard ratio did the 2020 cohort study report?",
        url="https://www.nature.com/articles/s41586-021-03819-2",
        calls=("doi",),
        via="doi",
        fetch=True,
        source="https://doi.org/10.1038/s41586-021-03819-2",
        text="The 2020 cohort study reported a hazard ratio of 1.34 for the primary outcome.",
        decoy="This article requires a subscription.",
        note_groups=(("1.34",), ("2020",)),
    ),
    Case(
        id="fallback",
        question="How many days did the rash last in the 2016 clinic series?",
        url="https://pubmed.ncbi.nlm.nih.gov/27000001/",
        calls=("pubmed", "trafilatura"),
        via="trafilatura",
        text="A 2016 clinic series found the rash lasted 11 days.",
        note_groups=(("11",), ("2016",)),
    ),
    Case(
        id="dead",
        question="What response rate did the missing report give?",
        url="https://missing.example/report",
        calls=("trafilatura",),
        dead=True,
        answers_gap=False,
    ),
    Case(
        id="script_page",
        question="What price did the 2023 catalog list for the widget?",
        url="https://catalog.example/widget",
        calls=("trafilatura", "python_scraping"),
        via="python_scraping",
        script=True,
        text="The 2023 catalog lists the widget at $18.",
        note_groups=(("18",), ("2023",)),
    ),
    Case(
        id="script_pubmed",
        question="What dose did the 2014 trial give each morning?",
        url="https://pubmed.ncbi.nlm.nih.gov/24400001/",
        calls=("pubmed", "trafilatura", "python_scraping"),
        via="python_scraping",
        script=True,
        text="The 2014 trial gave 40 mg each morning.",
        note_groups=(("40 mg", "40mg"), ("2014",)),
    ),
    Case(
        id="script_doi",
        question="What sample size did the 2018 methods section report?",
        url="https://doi.org/10.1000/script-2018",
        calls=("doi", "trafilatura", "python_scraping"),
        via="python_scraping",
        script=True,
        text="The 2018 methods section reported a sample of 86 adults.",
        note_groups=(("86",), ("2018",)),
    ),
    Case(
        id="script_dead",
        question="What yield did the missing lab note report?",
        url="https://gone.example/lab-note",
        calls=("trafilatura", "python_scraping"),
        dead=True,
        script=True,
        answers_gap=False,
    ),
)
