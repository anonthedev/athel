import unittest
from unittest.mock import patch

from langchain_core.messages import ToolMessage

from app.nodes.scrape import (
    DOWNLOAD_FAILED,
    PageResult,
    deliver,
    finding_from,
    reads_from,
    scrape,
    tools_for,
)


class DeliverTests(unittest.TestCase):
    def test_formats_a_source_and_text(self):
        text = deliver(("Abstract", "https://pubmed.ncbi.nlm.nih.gov/1/"), "miss")
        self.assertTrue(text.startswith("Source: https://pubmed.ncbi.nlm.nih.gov/1/\n\nAbstract"))

    def test_empty_text_is_a_miss(self):
        self.assertEqual(deliver(("", "https://example.com"), "miss"), "miss")
        self.assertEqual(deliver(None, "miss"), "miss")


class ReadTests(unittest.TestCase):
    def test_keeps_the_last_reader_and_a_failed_download(self):
        messages = [
            ToolMessage(content="No PubMed record at this URL.", tool_call_id="1"),
            ToolMessage(content=DOWNLOAD_FAILED, tool_call_id="2"),
            ToolMessage(content="Source: https://doi.org/10.1/abc\n\nTitle: A paper", tool_call_id="3"),
        ]
        reads, failed = reads_from(messages)
        self.assertTrue(failed)
        self.assertEqual(reads, [("Title: A paper", "https://doi.org/10.1/abc")])

    def test_pubmed_tool_returns_the_record(self):
        tools = {item.name: item for item in tools_for("caffeine", "https://example.com/page")}
        with patch("app.nodes.scrape.pubmed_source.load", return_value=("Abstract", "https://pubmed.ncbi.nlm.nih.gov/1/")) as load:
            text = tools["pubmed"].invoke({"url": "https://pubmed.ncbi.nlm.nih.gov/1/"})
        load.assert_called_once_with("https://pubmed.ncbi.nlm.nih.gov/1/", "caffeine")
        self.assertIn("Abstract", text)

    def test_trafilatura_reports_a_failed_download(self):
        tools = {item.name: item for item in tools_for("caffeine", "https://example.com/page")}
        with patch("app.nodes.scrape.load_text", return_value=None):
            text = tools["trafilatura"].invoke({"url": "https://example.com/missing"})
        self.assertEqual(text, DOWNLOAD_FAILED)


class ScrapeTests(unittest.TestCase):
    def test_finding_uses_the_reader_source(self):
        def invoke(payload, config=None):
            return {
                "messages": [
                    ToolMessage(
                        content="Source: https://pubmed.ncbi.nlm.nih.gov/1/\n\nAbstract",
                        tool_call_id="1",
                    )
                ],
                "structured_response": PageResult(answers_gap=True, note="A fact.", additional=""),
            }

        parsed = PageResult(answers_gap=True, note="A fact.", additional="")
        with patch("app.nodes.scrape.scraper_llm"), patch("app.nodes.scrape.create_agent") as factory, patch("app.nodes.scrape.extract_text", return_value=parsed):
            factory.return_value.invoke.side_effect = invoke
            result = scrape({"gap_id": 3, "question": "q", "url": "https://pubmed.ncbi.nlm.nih.gov/9/"})

        finding = result["findings"][0]
        self.assertEqual(finding.source, "https://pubmed.ncbi.nlm.nih.gov/1/")
        self.assertEqual(finding.gap_id, 3)
        self.assertTrue(finding.answers_gap)
        self.assertEqual(finding.note, "A fact.")

    def test_a_note_without_a_read_is_dropped(self):
        def invoke(payload, config=None):
            return {
                "messages": [],
                "structured_response": PageResult(answers_gap=True, note="Invented.", additional=""),
            }

        with patch("app.nodes.scrape.scraper_llm"), patch("app.nodes.scrape.create_agent") as factory:
            factory.return_value.invoke.side_effect = invoke
            result = scrape({"gap_id": 1, "question": "q", "url": "https://example.com/a"})
        self.assertEqual(result, {"findings": []})

    def test_failed_download_blocks_the_host(self):
        def invoke(payload, config=None):
            return {"messages": [ToolMessage(content=DOWNLOAD_FAILED, tool_call_id="1")]}

        with patch("app.nodes.scrape.scraper_llm"), patch("app.nodes.scrape.create_agent") as factory:
            factory.return_value.invoke.side_effect = invoke
            result = scrape({"gap_id": 1, "question": "q", "url": "https://www.example.com/missing"})
        self.assertEqual(result["dead_urls"], ["https://www.example.com/missing"])
        self.assertEqual(result["blocked_domains"], ["example.com"])
        self.assertEqual(result["findings"], [])

    def test_empty_notes_are_not_a_finding(self):
        result = finding_from(1, PageResult(answers_gap=True, note="  ", additional=""), "https://example.com")
        self.assertEqual(result, {"findings": []})

    def test_extractor_reads_the_page_text(self):
        def invoke(payload, config=None):
            return {
                "messages": [
                    ToolMessage(content="Source: https://example.com/p\n\nPage body", tool_call_id="1")
                ]
            }

        parsed = PageResult(answers_gap=False, note="", additional="A related result.")
        with patch("app.nodes.scrape.scraper_llm"), patch("app.nodes.scrape.create_agent") as factory, patch("app.nodes.scrape.extract_text", return_value=parsed) as extract:
            factory.return_value.invoke.side_effect = invoke
            result = scrape({"gap_id": 2, "question": "q", "url": "https://example.com/p"})
        extract.assert_called_once_with("q", "Page body")
        finding = result["findings"][0]
        self.assertFalse(finding.answers_gap)
        self.assertEqual(finding.additional, "A related result.")
        self.assertEqual(finding.source, "https://example.com/p")


if __name__ == "__main__":
    unittest.main()
