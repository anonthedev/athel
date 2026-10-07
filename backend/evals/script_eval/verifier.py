from app.states import Finding

from evals.script_eval.cases import Case


def grade(case: Case, result: dict, calls: list[str], scripts: list[str], runs: list[dict]) -> str:
    return "pass" if not failures(case, result, calls, scripts, runs) else "fail"


def in_order(calls: list[str], tools: tuple[str, ...]) -> bool:
    position = -1
    for tool in tools:
        try:
            position = calls.index(tool, position + 1)
        except ValueError:
            return False
    return True


def failures(case: Case, result: dict, calls: list[str], scripts: list[str], runs: list[dict]) -> list[str]:
    reasons = []
    if not in_order(calls, ("trafilatura", "python_scraping")):
        reasons.append(f"calls {calls or 'none'}")
    script = scripts[-1] if scripts else ""
    if case.url not in script:
        reasons.append("script missing url")
    printed = next((run["out"] for run in reversed(runs) if run["code"] == 0 and run["out"].strip()), "")
    if not printed:
        crashed = not runs or any(run["code"] != 0 for run in runs)
        reasons.append("script failed" if crashed else "stdout empty")
    elif "Traceback (most recent call last)" in printed:
        reasons.append("traceback")
    for group in case.note_groups:
        if not any(option.lower() in printed.lower() for option in group):
            reasons.append(f"stdout missing {group[0]}")

    findings = result.get("findings") or []
    finding = findings[0] if findings else None
    if finding is None:
        return reasons + ["missing finding"]
    return reasons + note_failures(case, finding)


def note_failures(case: Case, finding: Finding) -> list[str]:
    reasons = []
    note = finding.note.lower()
    if finding.source != case.url:
        reasons.append("source")
    if not finding.answers_gap or not finding.note.strip():
        reasons.append("answers_gap")
    for group in case.note_groups:
        if not any(option.lower() in note for option in group):
            reasons.append(f"note missing {group[0]}")
    return reasons
