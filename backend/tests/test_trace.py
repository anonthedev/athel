import operator
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from app.graph import open_checkpointer
from app.states import Finding, KnowledgeGap, ModelCall, UrlHit
from app.trace import trace_from_history
from app.usage import call_from_message, collect_calls, note_embedding


class Message:
    usage_metadata = {"input_tokens": 11, "output_tokens": 7}
    response_metadata = {"cost": 0.0025}


class UsageTests(unittest.TestCase):
    def test_message_usage_includes_openrouter_cost(self):
        call = call_from_message(Message(), role="writer", model="anthropic/claude-sonnet-5", label="Write the report")
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual(call.input_tokens, 11)
        self.assertEqual(call.output_tokens, 7)
        self.assertEqual(call.cost, 0.0025)

    def test_embedding_usage_is_kept_for_the_node_that_asked(self):
        note_embedding({"usage": {"prompt_tokens": 4, "cost": 0.0001}})
        with collect_calls() as recorded:
            note_embedding({"usage": {"prompt_tokens": 9, "cost": 0.0002}})
            self.assertEqual(len(recorded), 1)
            self.assertEqual(recorded[0].role, "embedding")
            self.assertEqual(recorded[0].input_tokens, 9)
            self.assertEqual(recorded[0].cost, 0.0002)


def snapshot(values: dict, nxt: tuple[str, ...] = (), created_at: str | None = None):
    return SimpleNamespace(values=values, next=nxt, created_at=created_at)


class HistoryTests(unittest.TestCase):
    def test_newest_first_history_becomes_steps(self):
        call = ModelCall(
            role="planner",
            model="openai/gpt-5-mini",
            label="Draft questions",
            input_tokens=20,
            output_tokens=10,
            cost=0.01,
        )
        empty = {
            "topic": "Cities",
            "provider": "openrouter",
            "calls": [],
            "planned_queries": [],
            "gaps": [],
            "hits": [],
            "findings": [],
            "dead_urls": [],
            "final_report": "",
        }
        drafted = {
            **empty,
            "calls": [call],
            "gaps": [KnowledgeGap(id=1, question="Why do cities flood?")],
        }
        searched = {
            **drafted,
            "hits": [UrlHit(gap_id=1, question="Why do cities flood?", url="https://example.com/floods")],
            "findings": [
                Finding(
                    gap_id=1,
                    answers_gap=True,
                    note="Pavement sheds rain faster than soil.",
                    source="https://example.com/floods",
                )
            ],
        }
        trace = trace_from_history([
            snapshot(searched, ("update_checklist",), "2026-10-07T12:00:04+00:00"),
            snapshot(drafted, ("search",), "2026-10-07T12:00:02+00:00"),
            snapshot(empty, ("generate_gaps",), "2026-10-07T12:00:00+00:00"),
        ])
        self.assertEqual(trace["topic"], "Cities")
        self.assertEqual(trace["provider"], "openrouter")
        self.assertEqual(trace["calls"][0]["output_tokens"], 10)
        self.assertEqual(trace["steps"][0]["nodes"], ["generate_gaps"])
        self.assertEqual(trace["steps"][0]["questions"], ["Why do cities flood?"])
        self.assertEqual(trace["steps"][1]["urls"], ["https://example.com/floods"])
        self.assertEqual(trace["steps"][1]["findings"][0]["note"], "Pavement sheds rain faster than soil.")
        self.assertEqual(len(trace["steps"]), 2)

    def test_sqlite_checkpoint_keeps_usage_after_the_run(self):
        class State(TypedDict):
            topic: str
            provider: str
            calls: Annotated[list[ModelCall], operator.add]

        def add(_state: State) -> dict:
            return {
                "calls": [
                    ModelCall(
                        role="extractor",
                        model="google/gemini-3.1-flash-lite",
                        label="https://example.com",
                        input_tokens=30,
                        output_tokens=8,
                        cost=0.004,
                    )
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            checkpointer = open_checkpointer(Path(directory) / "checkpoints.sqlite")
            graph = (
                StateGraph(State)
                .add_node("add", add)
                .add_edge(START, "add")
                .add_edge("add", END)
                .compile(checkpointer=checkpointer)
            )
            config = {"configurable": {"thread_id": "run-1"}}
            graph.invoke({"topic": "Cities", "provider": "openrouter", "calls": []}, config)
            trace = trace_from_history(list(graph.get_state_history(config)))
            checkpointer.conn.close()

        self.assertEqual(trace["calls"][0]["input_tokens"], 30)
        self.assertEqual(trace["calls"][0]["cost"], 0.004)
        self.assertEqual(trace["steps"][0]["nodes"], ["add"])
        self.assertEqual(trace["steps"][0]["calls"][0]["role"], "extractor")


if __name__ == "__main__":
    unittest.main()
