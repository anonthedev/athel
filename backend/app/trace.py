from app.states import Finding, KnowledgeGap, ModelCall, PlannedQuery, UrlHit, gap_mark


def _values(snapshot: object) -> dict:
    values = getattr(snapshot, "values", None)
    return values if isinstance(values, dict) else {}


def _next_nodes(snapshot: object) -> list[str]:
    raw = getattr(snapshot, "next", ()) or ()
    return [node for node in raw if isinstance(node, str)]


def _when(snapshot: object) -> str | None:
    created = getattr(snapshot, "created_at", None)
    if isinstance(created, str) and created.strip():
        return created
    if hasattr(created, "isoformat"):
        return created.isoformat()
    return None


def _call(item: object) -> dict | None:
    if isinstance(item, ModelCall):
        data = item.model_dump()
    elif isinstance(item, dict):
        data = item
    else:
        return None
    cost = data.get("cost")
    return {
        "role": str(data.get("role") or ""),
        "model": str(data.get("model") or ""),
        "label": str(data.get("label") or ""),
        "input_tokens": int(data.get("input_tokens") or 0),
        "output_tokens": int(data.get("output_tokens") or 0),
        "cost": float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
    }


def _calls(values: dict) -> list[dict]:
    found = []
    for item in values.get("calls") or []:
        call = _call(item)
        if call is not None:
            found.append(call)
    return found


def _gap_fields(gap: object) -> tuple[str, str, list[str]] | None:
    if isinstance(gap, dict):
        try:
            gap = KnowledgeGap.model_validate(gap)
        except Exception:
            question = gap.get("question")
            if not isinstance(question, str):
                return None
            missing = gap.get("missing")
            if not isinstance(missing, list):
                missing = []
            return question, str(gap.get("status") or "unresolved"), [part for part in missing if isinstance(part, str)]
    if not isinstance(gap, KnowledgeGap):
        return None
    return gap.question, gap_mark(gap), list(gap.missing)


def _gap_rows(values: dict) -> list[tuple[str, str, list[str]]]:
    rows = []
    for gap in values.get("gaps") or []:
        fields = _gap_fields(gap)
        if fields is not None:
            rows.append(fields)
    return rows


def _planned(item: object) -> dict | None:
    if isinstance(item, dict):
        try:
            item = PlannedQuery.model_validate(item)
        except Exception:
            return None
    if not isinstance(item, PlannedQuery):
        return None
    return {"question": item.question, "queries": list(item.queries)}


def _slice(previous: list, current: list) -> list:
    if len(current) < len(previous):
        return current
    return current[len(previous):]


def _urls(values: dict) -> list[str]:
    found = []
    for hit in values.get("hits") or []:
        if isinstance(hit, UrlHit):
            found.append(hit.url)
        elif isinstance(hit, dict) and isinstance(hit.get("url"), str):
            found.append(hit["url"])
    return found


def _findings(values: dict) -> list[dict]:
    found = []
    for item in values.get("findings") or []:
        if isinstance(item, dict):
            try:
                item = Finding.model_validate(item)
            except Exception:
                continue
        if not isinstance(item, Finding):
            continue
        if not item.note.strip() and not item.additional.strip():
            continue
        found.append({"source": item.source, "note": item.note, "answers": item.answers_gap})
    return found


def _queries(values: dict) -> list[dict]:
    found = []
    for item in values.get("planned_queries") or []:
        planned = _planned(item)
        if planned is not None:
            found.append(planned)
    return found


def _dead(values: dict) -> list[str]:
    return [url for url in values.get("dead_urls") or [] if isinstance(url, str)]


def trace_from_history(snapshots: list) -> dict:
    ordered = list(snapshots)
    ordered.reverse()
    latest = _values(ordered[-1]) if ordered else {}
    steps = []
    previous = None
    for snapshot in ordered:
        if previous is None:
            previous = snapshot
            continue
        before = _values(previous)
        after = _values(snapshot)
        calls = _slice(_calls(before), _calls(after))
        queries = _slice(_queries(before), _queries(after))
        urls = _slice(_urls(before), _urls(after))
        findings = _slice(_findings(before), _findings(after))
        dead_urls = _slice(_dead(before), _dead(after))
        before_gaps = _gap_rows(before)
        after_gaps = _gap_rows(after)
        questions_changed = [row[0] for row in before_gaps] != [row[0] for row in after_gaps]
        status_changed = [(row[1], tuple(row[2])) for row in before_gaps] != [
            (row[1], tuple(row[2])) for row in after_gaps
        ]
        report = (after.get("final_report") or "") != (before.get("final_report") or "") and bool(after.get("final_report"))
        questions = [row[0] for row in after_gaps] if questions_changed else []
        gaps = [
            {"question": row[0], "status": row[1], "missing": row[2]}
            for row in after_gaps
        ] if status_changed and not questions_changed else []
        if not any((calls, queries, urls, findings, dead_urls, questions, gaps, report)):
            previous = snapshot
            continue
        steps.append({
            "nodes": _next_nodes(previous),
            "at": _when(snapshot),
            "calls": calls,
            "queries": queries,
            "questions": questions,
            "urls": urls,
            "findings": findings,
            "dead_urls": dead_urls,
            "gaps": gaps,
            "report": report,
        })
        previous = snapshot
    return {
        "topic": latest.get("topic") if isinstance(latest.get("topic"), str) else "",
        "provider": latest.get("provider") if isinstance(latest.get("provider"), str) else "",
        "calls": _calls(latest),
        "steps": steps,
    }
