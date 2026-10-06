import re

from app.states import Finding

from evals.extractor_eval.cases import Case

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def grade(case: Case, finding: Finding | None) -> str:
    return "pass" if not failures(case, finding) else "fail"


def failures(case: Case, finding: Finding | None) -> list[str]:
    if finding is None:
        return [] if not case.expect_finding else ["missing finding"]
    if not case.expect_finding:
        return ["unexpected finding"]

    reasons = []
    note = finding.note.lower()
    additional = finding.additional.lower()
    blob = f"{note}\n{additional}"

    if finding.source != case.url:
        reasons.append("source")
    if finding.answers_gap != case.answers_gap:
        reasons.append("answers_gap")
    if case.answers_gap and not finding.note.strip():
        reasons.append("empty note")
    if case.note_must_be_empty and finding.note.strip():
        reasons.append("note should be empty")
    if case.additional_must_be_empty and finding.additional.strip():
        reasons.append("additional should be empty")
    for group in case.note_groups:
        if not any(option in note for option in group):
            reasons.append(f"note missing {group[0]}")
    for group in case.additional_groups:
        if not any(option in additional for option in group):
            reasons.append(f"additional missing {group[0]}")
    for banned in case.prohibited:
        if banned.lower() in blob:
            reasons.append(f"kept {banned}")
    if case.marker_prefixes:
        stripped = finding.note.lstrip().lower()
        if not any(stripped.startswith(prefix.lower()) for prefix in case.marker_prefixes):
            reasons.append("page marker")
    if case.allowed_numbers:
        allowed = set(case.allowed_numbers)
        extra = [number for number in _NUMBER.findall(note) if number not in allowed]
        if extra:
            reasons.append(f"invented numbers {extra}")
    return reasons
