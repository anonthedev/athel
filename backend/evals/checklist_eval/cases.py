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
)

BY_ID = {case.id: case for case in CASES}
