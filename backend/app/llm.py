from contextvars import ContextVar, Token
from dataclasses import dataclass

from langchain_openrouter import ChatOpenRouter

DEFAULT_PLANNER = "openai/gpt-5-mini"
DEFAULT_EXTRACTOR = "google/gemini-3.1-flash-lite"
DEFAULT_WRITER = "anthropic/claude-sonnet-5"


@dataclass(frozen=True)
class ModelSelection:
    api_key: str
    planner: str
    extractor: str
    writer: str


_selection: ContextVar[ModelSelection | None] = ContextVar("model_selection", default=None)


def use_selection(selection: ModelSelection) -> Token:
    return _selection.set(selection)


def reset_selection(token: Token) -> None:
    _selection.reset(token)


def _require() -> ModelSelection:
    selection = _selection.get()
    if selection is None:
        raise RuntimeError("OpenRouter key and models were not set for this run")
    return selection


def planner_llm() -> ChatOpenRouter:
    selection = _require()
    return ChatOpenRouter(model=selection.planner, api_key=selection.api_key)


def extractor_llm() -> ChatOpenRouter:
    selection = _require()
    return ChatOpenRouter(model=selection.extractor, api_key=selection.api_key)


def writer_llm() -> ChatOpenRouter:
    selection = _require()
    return ChatOpenRouter(model=selection.writer, api_key=selection.api_key)
