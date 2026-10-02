from contextvars import ContextVar, Token
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openrouter import ChatOpenRouter

DEFAULT_PLANNER = "openai/gpt-5-mini"
DEFAULT_EXTRACTOR = "google/gemini-3.1-flash-lite"
DEFAULT_WRITER = "anthropic/claude-sonnet-5"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    api_key: str
    planner: str
    extractor: str
    writer: str
    embedding: str


_selection: ContextVar[ModelSelection | None] = ContextVar("model_selection", default=None)


def use_selection(selection: ModelSelection) -> Token:
    return _selection.set(selection)


def reset_selection(token: Token) -> None:
    _selection.reset(token)


def current_selection() -> ModelSelection:
    selection = _selection.get()
    if selection is None:
        raise RuntimeError("Models were not set for this run")
    return selection


def chat_llm(model: str) -> BaseChatModel:
    selection = current_selection()
    if selection.provider == "ollama":
        return ChatOllama(model=model, base_url=OLLAMA_BASE_URL, reasoning=False)
    return ChatOpenRouter(model=model, api_key=selection.api_key)


def planner_llm() -> BaseChatModel:
    return chat_llm(current_selection().planner)


def extractor_llm() -> BaseChatModel:
    return chat_llm(current_selection().extractor)


def writer_llm() -> BaseChatModel:
    return chat_llm(current_selection().writer)
