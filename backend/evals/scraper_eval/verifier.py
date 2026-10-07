from urllib.parse import urlparse

from app.states import Finding

from evals.scraper_eval.cases import Case


def grade(case: Case, result: dict, calls: list[str], scripts: list[str] | None = None) -> str:
    return "pass" if not failures(case, result, calls, scripts) else "fail"


def in_order(calls: list[str], tools: tuple[str, ...]) -> bool:
    position = -1
    for tool in tools:
        try:
            position = calls.index(tool, position + 1)
        except ValueError:
            return False
    return True


def failures(case: Case, result: dict, calls: list[str], scripts: list[str] | None = None) -> list[str]:
    reasons = []
    if not in_order(calls, case.calls):
        reasons.append(f"calls {calls or 'none'}")
    if case.script:
        body = scripts[-1] if scripts else ""
        if case.url not in body:
            reasons.append("script missing url")

    findings = result.get("findings") or []
    finding = findings[0] if findings else None
    if case.dead:
        if case.url not in result.get("dead_urls", []):
            reasons.append("not dead")
        host = urlparse(case.url).netloc.lower().removeprefix("www.")
        if host not in result.get("blocked_domains", []):
            reasons.append("not blocked")
        if finding is not None:
            reasons.append("unexpected finding")
        return reasons

    if finding is None:
        return reasons + ["missing finding"]
    return reasons + finding_failures(case, finding)


def finding_failures(case: Case, finding: Finding) -> list[str]:
    reasons = []
    note = finding.note.lower()
    additional = finding.additional.lower()
    source = case.source or case.url
    if finding.source != source:
        reasons.append("source")
    if finding.answers_gap != case.answers_gap:
        reasons.append("answers_gap")
    if case.answers_gap and not finding.note.strip():
        reasons.append("empty note")
    if case.additional_must_be_empty and finding.additional.strip():
        reasons.append("additional should be empty")
    for group in case.note_groups:
        if not any(option.lower() in note for option in group):
            reasons.append(f"note missing {group[0]}")
    return reasons
