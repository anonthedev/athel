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
    additional_must_be_empty: bool = False
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
    Case(
        id="both_present",
        question="What median backbone accuracy did Jumper et al. (2021) report for AlphaFold on CASP14?",
        page=_page("both_present.md"),
        url=_url("both_present"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("0.96",), ("jumper", "2021"), ("casp14",)),
        additional_must_be_empty=True,
        prohibited=("senior", "2020", "casp13"),
        allowed_numbers=("0.96", "2021", "14"),
    ),
    Case(
        id="bibliography",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        page=_page("bibliography.md"),
        url=_url("bibliography"),
        expect_finding=False,
    ),
    Case(
        id="gallery",
        question=(
            "What share of a Scottish sample did Simner et al. (2006) "
            "find had grapheme-color synesthesia?"
        ),
        page=_page("gallery.md"),
        url=_url("gallery"),
        expect_finding=False,
    ),
    Case(
        id="survival",
        question=(
            "What 5-year survival rate did the 2018 velpanib trial report, "
            "and how many patients did that trial enroll?"
        ),
        page=_page("survival.md"),
        url=_url("survival"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("62%", "62 percent"), ("velpanib",), ("2018",)),
        additional_must_be_empty=True,
        prohibited=("840", "71", "2014"),
        allowed_numbers=("62", "2018", "5"),
    ),
    Case(
        id="handset",
        question="What was the official US list price of the 128 GB model in March 2024?",
        page=_page("handset.md"),
        url=_url("handset"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("$799", "799 dollars", "799 us dollars"), ("128",), ("2024",)),
        additional_must_be_empty=True,
        prohibited=("769", "749", "899", "699"),
    ),
    Case(
        id="retracted",
        question="What response rate did the published intention-to-treat analysis of the nelvotinib study report?",
        page=_page("retracted.md"),
        url=_url("retracted"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("9.1%", "9.1 percent"),),
        additional_must_be_empty=True,
        prohibited=("4.2", "12.4", "86"),
    ),
    Case(
        id="regimen",
        question=(
            "In what year did the WHO recommend the 6-month tuberculosis regimen, "
            "and what cure rate did it report for that regimen?"
        ),
        page=_page("regimen.md"),
        url=_url("regimen"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("85%", "85 percent"), ("6-month", "6 month")),
        additional_must_be_empty=True,
        prohibited=("2018", "91", "4-month", "4 month"),
        allowed_numbers=("85", "6"),
    ),
    Case(
        id="dose_units",
        question="What maximum daily dose does the European label list for adults, in the units printed on that label?",
        page=_page("dose_units.md"),
        url=_url("dose_units"),
        expect_finding=True,
        answers_gap=True,
        note_groups=(("1.1 g", "1.1g", "1.1 gram"),),
        additional_must_be_empty=True,
        prohibited=("1100", "400", "2012", "mg/kg"),
    ),
)

BY_ID = {case.id: case for case in CASES}
