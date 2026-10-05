from dataclasses import dataclass
from pathlib import Path

_PAGES = Path(__file__).with_name("pages")


def _page(name: str) -> str:
    return (_PAGES / name).read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    page: str
    url: str
    expect_finding: bool
    answers_gap: bool = False
    note_groups: tuple[tuple[str, ...], ...] = ()
    additional_groups: tuple[tuple[str, ...], ...] = ()
    note_must_be_empty: bool = False
    prohibited: tuple[str, ...] = ()
    marker_prefixes: tuple[str, ...] = ()
    allowed_numbers: tuple[str, ...] = ()


def _url(case_id: str) -> str:
    return f"https://fixture.test/{case_id}"


CASES = (
    Case(
        id="simner_decoy",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        page=_page("simner_decoy.md"),
        url=_url("simner_decoy"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(
            ("simner",),
            ("2006",),
            ("1.1%", "1.1 percent"),
            ("scotland", "scottish"),
        ),
        prohibited=("18%",),
    ),
    Case(
        id="partial_sample",
        question=(
            "What prevalence of grapheme-color synesthesia did Simner et al. (2006) "
            "report, and how many people were in that sample?"
        ),
        page=_page("partial_sample.md"),
        url=_url("partial_sample"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(
            ("simner",),
            ("2006",),
            ("1.1%", "1.1 percent"),
        ),
        allowed_numbers=("1.1", "2006"),
    ),
    Case(
        id="related_study",
        question="What daily caffeine limit do regulators set for healthy non-pregnant adults?",
        page=_page("related_study.md"),
        url=_url("related_study"),
        expect_finding=True,
        answers_gap=False,
        note_must_be_empty=True,
        additional_groups=(("wikoff",), ("2017",)),
        prohibited=("400", "mg", "milligram"),
    ),
    Case(
        id="paywall",
        question="What daily caffeine limit do regulators set for healthy non-pregnant adults?",
        page=_page("paywall.md"),
        url=_url("paywall"),
        expect_finding=False,
    ),
    Case(
        id="page_marker",
        question="What reduction in systolic blood pressure did the 12-week trial find?",
        page=_page("page_marker.md"),
        url=_url("page_marker"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("14%", "14 percent"),),
        marker_prefixes=("(p. 4)", "(p.4)"),
    ),
)

BY_ID = {case.id: case for case in CASES}
