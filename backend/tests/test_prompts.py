import unittest

from app.prompts import extract_page, followup_queries, gaps, missing_parts, scrape_instructions, search_queries, write_report


class PromptTests(unittest.TestCase):
    def test_inputs_are_appended_after_the_instructions(self):
        self.assertTrue(gaps("best phone under 20000").endswith("best phone under 20000"))
        self.assertIn("5000 mAh", gaps("phones"))
        self.assertIn("daily caffeine limit", gaps("phones"))
        queries = search_queries("battery capacity")
        self.assertTrue(queries.endswith("battery capacity"))
        self.assertIn("Still needed:\nthe price date", followup_queries("q", "known fact", "the price date"))
        self.assertIn("Notes:\n- 400 mg", missing_parts("how much", "- 400 mg"))
        page = extract_page("what is safe", "The trial enrolled 96 adults.")
        self.assertIn("Question:\nwhat is safe", page)
        self.assertTrue(page.endswith("The trial enrolled 96 adults."))
        report = write_report("caffeine", "notes here", "extra here")
        self.assertIn("Topic:\ncaffeine", report)
        self.assertIn("Notes:\nnotes here", report)
        self.assertTrue(report.endswith("extra here"))

    def test_a_page_with_braces_is_not_treated_as_a_template(self):
        page = extract_page("cost", "Price is {18,999}.")
        self.assertIn("Price is {18,999}.", page)

    def test_scrape_instructions_name_the_readers(self):
        instructions = scrape_instructions()
        for reader in ("pubmed", "doi", "reddit", "substack", "trafilatura", "python_scraping"):
            self.assertIn(reader, instructions)
        self.assertIn("markdown fences", instructions)
        self.assertIn("whatever approach", instructions)
        self.assertIn("answers_gap", instructions)
        self.assertFalse(instructions.endswith("Question:\n"))
