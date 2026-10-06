import unittest

from app.states import KnowledgeGap, SourcedNote, gap_mark


def gap(**kwargs) -> KnowledgeGap:
    return KnowledgeGap(id=1, question="What year was it published?", **kwargs)


class GapMarkTests(unittest.TestCase):
    def test_a_finished_answer_is_resolved_before_the_loop_stops(self):
        marked = gap_mark(gap(
            status="pending",
            notes=[SourcedNote(note="1923.", source="https://example.test/compton")],
            missing=[],
        ))
        self.assertEqual(marked, "resolved")

    def test_a_partial_answer_stays_visible_while_research_continues(self):
        marked = gap_mark(gap(
            status="pending",
            notes=[SourcedNote(note="Compton published the result.", source="https://example.test/compton")],
            missing=["the year"],
        ))
        self.assertEqual(marked, "partial")

    def test_a_question_with_no_notes_is_unresolved(self):
        marked = gap_mark(gap(status="pending", missing=["What year was it published?"]))
        self.assertEqual(marked, "unresolved")

    def test_a_failed_question_is_unresolved(self):
        self.assertEqual(gap_mark(gap(status="failed")), "unresolved")

    def test_terminal_partial_and_resolved_keep_their_marks(self):
        self.assertEqual(gap_mark(gap(status="resolved")), "resolved")
        self.assertEqual(
            gap_mark(gap(
                status="partial",
                notes=[SourcedNote(note="A date is missing.", source="https://example.test/a")],
                missing=["the year"],
            )),
            "partial",
        )
