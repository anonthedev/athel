from app.states import KnowledgeGap

from evals.checklist_eval.cases import Case


def listed(gap: KnowledgeGap) -> str:
    return "\n".join(item.strip() for item in gap.missing if item and item.strip()).lower()


def grade(case: Case, gap: KnowledgeGap) -> str:
    return "pass" if not failures(case, gap) else "fail"


def failures(case: Case, gap: KnowledgeGap) -> list[str]:
    reasons = []
    missing = [item.strip() for item in gap.missing if item and item.strip()]
    if gap.status != case.expect_status:
        reasons.append(f"status {gap.status}")
    if case.missing_must_be_empty and missing:
        reasons.append("missing should be empty")
    if not case.missing_must_be_empty and not missing:
        reasons.append("missing should name the gap")
    text = "\n".join(missing).lower()
    for group in case.missing_groups:
        if not any(option in text for option in group):
            reasons.append(f"missing lacks {group[0]}")
    if len(missing) > 4:
        reasons.append("more than 4 items")
    long = [item for item in missing if len(item.split()) > 10]
    if long:
        reasons.append("item longer than 10 words")
    return reasons
