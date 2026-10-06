from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    notes: tuple[str, ...]
    expect_status: str
    missing_must_be_empty: bool
    missing_groups: tuple[tuple[str, ...], ...] = ()


CASES = (
    Case(
        id="answered",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        notes=(
            "Simner et al. (2006) found grapheme-color synesthesia in 1.1% of a Scottish sample.",
        ),
        expect_status="resolved",
        missing_must_be_empty=True,
    ),
    Case(
        id="vague",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        notes=("Synesthesia is fairly common.",),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(("share", "prevalence", "percent", "%", "1.1", "simner"),),
    ),
    Case(
        id="partial_sample",
        question=(
            "What prevalence of grapheme-color synesthesia did Simner et al. (2006) "
            "report, and how many people were in that sample?"
        ),
        notes=(
            "Simner et al. (2006) reported grapheme-color synesthesia in 1.1% of adults tested in Scotland.",
        ),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(("sample", "how many", "number of", "participants", "headcount"),),
    ),
    Case(
        id="disagreement",
        question="What share of adults have grapheme-color synesthesia?",
        notes=(
            "A Scottish survey found grapheme-color synesthesia in 1.1% of adults.",
            "A second survey found grapheme-color synesthesia in 4% of adults.",
        ),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(("who", "author", "source", "study", "reported"),),
    ),
    Case(
        id="price_complete",
        question="What was the official US list price of the 128 GB model in March 2024?",
        notes=(
            "In March 2024 the official US list price of the 128 GB model was $799. "
            "A retailer later advertised $749, and the 256 GB model was $899 in March 2023.",
        ),
        expect_status="resolved",
        missing_must_be_empty=True,
    ),
    Case(
        id="hedged",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        notes=(
            "Simner et al. (2006) found that about 1.1% of their Scottish sample had "
            "grapheme-color synesthesia, though the authors discuss uncertainty around the estimate.",
        ),
        expect_status="resolved",
        missing_must_be_empty=True,
    ),
    Case(
        id="agreeing",
        question=(
            "What prevalence of grapheme-color synesthesia did Simner et al. (2006) "
            "report in their Scottish sample?"
        ),
        notes=(
            "Simner et al. (2006) found grapheme-color synesthesia in 1.1% of a Scottish sample.",
            "Ward (2013) cites that same Simner et al. (2006) figure of 1.1% for the Scottish sample.",
        ),
        expect_status="resolved",
        missing_must_be_empty=True,
    ),
    Case(
        id="price_wrong_date",
        question="What was the US list price of the 128 GB model, and when was that price listed?",
        notes=(
            "The 128 GB model had a US list price of $799.",
            "The 256 GB model was listed at $899 in March 2023.",
        ),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(
            ("date", "when", "month", "year"),
            ("128", "799"),
        ),
    ),
    Case(
        id="study_not_limit",
        question="What daily caffeine limit do regulators set for healthy non-pregnant adults?",
        notes=(
            "Wikoff et al. (2017) found that a 400 mg caffeine dose lengthened sleep latency in healthy adults.",
        ),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(("limit", "regulat", "maximum", "guideline", "fda", "efsa", "agency"),),
    ),
    Case(
        id="half_sourced",
        question="What share of adults have grapheme-color synesthesia?",
        notes=(
            "Simner et al. (2006) found grapheme-color synesthesia in 1.1% of a Scottish sample.",
            "Another survey put the share at 4%.",
        ),
        expect_status="pending",
        missing_must_be_empty=False,
        missing_groups=(("4%", "4 percent", " 4", "four"),),
    ),
)

BY_ID = {case.id: case for case in CASES}
