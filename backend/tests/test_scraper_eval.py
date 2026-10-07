import unittest

from evals.scraper_eval.cases import CASES
from evals.scraper_eval.verifier import failures
from app.states import Finding


def case(name):
    return next(item for item in CASES if item.id == name)


def found(note, source, answers=True):
    return {
        "findings": [
            Finding(gap_id=1, answers_gap=answers, note=note, source=source, additional="")
        ]
    }


class ScraperVerifierTests(unittest.TestCase):
    def test_pubmed_passes_when_that_reader_is_called_first(self):
        item = case("pubmed")
        result = found("The 2021 trial reported a 27% drop.", item.url)
        self.assertEqual(failures(item, result, ["pubmed"]), [])

    def test_fallback_requires_pubmed_before_trafilatura(self):
        item = case("fallback")
        result = found("The 2016 series said the rash lasted 11 days.", item.url)
        self.assertEqual(failures(item, result, ["trafilatura", "pubmed"]), ["calls ['trafilatura', 'pubmed']"])
        self.assertEqual(failures(item, result, ["pubmed", "trafilatura"]), [])

    def test_publisher_keeps_the_doi_source(self):
        item = case("publisher")
        result = found("The 2020 study reported a hazard ratio of 1.34.", item.url)
        self.assertIn("source", failures(item, result, ["doi"]))
        result = found("The 2020 study reported a hazard ratio of 1.34.", item.source)
        self.assertEqual(failures(item, result, ["doi"]), [])

    def test_dead_url_must_block_the_host(self):
        item = case("dead")
        self.assertEqual(
            failures(item, {"findings": [], "dead_urls": [], "blocked_domains": []}, ["trafilatura"]),
            ["not dead", "not blocked"],
        )
        result = {"findings": [], "dead_urls": [item.url], "blocked_domains": ["missing.example"]}
        self.assertEqual(failures(item, result, ["trafilatura"]), [])

    def test_script_page_needs_python_after_trafilatura(self):
        item = case("script_page")
        result = found("The 2023 catalog listed the widget at $18.", item.url)
        script = f"print(open_url('{item.url}'))"
        self.assertEqual(failures(item, result, ["trafilatura"], [script]), ["calls ['trafilatura']"])
        self.assertIn("script missing url", failures(item, result, ["trafilatura", "python_scraping"], ["print('no url')"]))
        self.assertEqual(failures(item, result, ["trafilatura", "python_scraping"], [script]), [])

    def test_script_dead_blocks_the_host_after_python_returns_nothing(self):
        item = case("script_dead")
        result = {"findings": [], "dead_urls": [item.url], "blocked_domains": ["gone.example"]}
        script = f"url = '{item.url}'\nprint('')"
        self.assertEqual(failures(item, result, ["trafilatura", "python_scraping"], [script]), [])
        self.assertIn("script missing url", failures(item, result, ["trafilatura", "python_scraping"], ["print(1)"]))


if __name__ == "__main__":
    unittest.main()
