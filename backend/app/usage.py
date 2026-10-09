from contextlib import contextmanager
from contextvars import ContextVar

from app.llm import current_selection
from app.states import ModelCall

_bucket: ContextVar[list[ModelCall] | None] = ContextVar("model_calls", default=None)


class UnreadableModel(Exception):
    pass


def model_for(role: str) -> str:
    try:
        selection = current_selection()
    except RuntimeError:
        return ""
    return {
        "planner": selection.planner,
        "extractor": selection.extractor,
        "writer": selection.writer,
        "embedding": selection.embedding,
    }.get(role, "")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _first_int(*values: object) -> int:
    for value in values:
        number = _number(value)
        if number is not None:
            return int(number)
    return 0


def _cost(payload: object) -> float | None:
    if not isinstance(payload, dict):
        return None
    return _number(payload.get("cost"))


def call_from_message(message: object, *, role: str, model: str, label: str) -> ModelCall | None:
    if message is None:
        return None
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        usage = {}
    meta = getattr(message, "response_metadata", None)
    if not isinstance(meta, dict):
        meta = {}
    token_usage = meta.get("token_usage")
    if not isinstance(token_usage, dict):
        token_usage = {}
    cost = _cost(meta)
    if cost is None:
        cost = _cost(token_usage)
    if cost is None:
        cost = _cost(usage)
    return ModelCall(
        role=role,  # type: ignore[arg-type]
        model=model,
        label=label[:200],
        input_tokens=_first_int(
            usage.get("input_tokens"),
            token_usage.get("prompt_tokens"),
            token_usage.get("input_tokens"),
        ),
        output_tokens=_first_int(
            usage.get("output_tokens"),
            token_usage.get("completion_tokens"),
            token_usage.get("output_tokens"),
        ),
        cost=cost,
    )


def note_call(call: ModelCall) -> None:
    bucket = _bucket.get()
    if bucket is not None:
        bucket.append(call)


def note_embedding(body: object) -> None:
    if not isinstance(body, dict):
        return
    usage = body.get("usage")
    if not isinstance(usage, dict):
        count = body.get("prompt_eval_count")
        if not isinstance(count, int):
            return
        usage = {"prompt_tokens": count, "completion_tokens": 0}
    note_call(
        ModelCall(
            role="embedding",
            model=model_for("embedding"),
            label="Rank PDF passages",
            input_tokens=_first_int(usage.get("prompt_tokens"), usage.get("input_tokens")),
            output_tokens=_first_int(usage.get("completion_tokens"), usage.get("output_tokens")),
            cost=_cost(usage),
        )
    )


@contextmanager
def collect_calls():
    recorded: list[ModelCall] = []
    token = _bucket.set(recorded)
    try:
        yield recorded
    finally:
        _bucket.reset(token)


def structured(llm, schema, prompt: str, *, role: str, label: str):
    result = llm.with_structured_output(schema, include_raw=True).invoke(prompt)
    raw = result.get("raw") if isinstance(result, dict) else None
    call = call_from_message(raw, role=role, model=model_for(role), label=label)
    if call is not None:
        note_call(call)
    parsed = result.get("parsed") if isinstance(result, dict) else None
    error = result.get("parsing_error") if isinstance(result, dict) else None
    if error or parsed is None:
        raise UnreadableModel("The model returned an unreadable answer")
    return parsed


def complete(llm, prompt: str, *, role: str, label: str):
    message = llm.invoke(prompt)
    call = call_from_message(message, role=role, model=model_for(role), label=label)
    if call is not None:
        note_call(call)
    return message
