import unittest
from pathlib import Path

from app.nodes.scrape import missing_module, tools_for
from app.states import Finding
from evals.script_eval.cases import CASES
from evals.script_eval.verifier import failures


def case(name):
    return next(item for item in CASES if item.id == name)


def found(note, source):
    return {
        "findings": [
            Finding(gap_id=1, answers_gap=True, note=note, source=source, additional="")
        ]
    }


class ScriptVerifierTests(unittest.TestCase):
    def test_marketplace_passes_when_the_script_prints_the_page(self):
        item = case("marketplace")
        self.assertTrue(item.url.startswith("https://www.ikea.com/"))
        script = f"url = '{item.url}'\nprint(download(url))"
        runs = [{"code": 0, "out": "The BILLY bookcase is a timeless storage solution with adjustable shelves.", "err": ""}]
        result = found("The bookcase has adjustable shelves and is described as timeless storage.", item.url)
        self.assertEqual(
            failures(item, result, ["trafilatura", "python_scraping"], [script], runs),
            [],
        )

    def test_blog_fails_when_the_script_omits_the_page_url(self):
        item = case("blog")
        runs = [{"code": 0, "out": "July 2023. The reader is assumed to be very ambitious.", "err": ""}]
        result = found("July 2023. The essay assumes you are very ambitious.", item.url)
        self.assertIn(
            "script missing url",
            failures(item, result, ["trafilatura", "python_scraping"], ["print('July 2023')"], runs),
        )

    def test_social_fails_when_python_never_runs(self):
        item = case("social")
        self.assertIn("news.ycombinator.com", item.url)
        self.assertIn(
            "script failed",
            failures(item, {"findings": []}, ["trafilatura"], [], []),
        )


class MissingModuleTests(unittest.TestCase):
    def test_names_the_top_level_import(self):
        self.assertEqual(missing_module("ModuleNotFoundError: No module named 'bs4'"), "bs4")
        self.assertEqual(missing_module("No module named 'bs4.element'"), "bs4")
        self.assertIsNone(missing_module("SyntaxError: invalid syntax"))

    def test_reads_import_names_from_the_script(self):
        from app.nodes.scrape import imported_modules
        source = "import requests\nfrom bs4 import BeautifulSoup\nimport urllib.request\n"
        self.assertEqual(imported_modules(source), ["requests", "bs4", "urllib"])


class ScriptRunTests(unittest.TestCase):
    @unittest.skipUnless(Path("/usr/bin/bwrap").exists(), "bwrap is not installed")
    def test_python_tool_reads_a_public_page(self):
        item = case("social")
        source = (
            "import urllib.request\n"
            f"url = {item.url!r}\n"
            "request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})\n"
            "print(urllib.request.urlopen(request, timeout=20).read().decode('utf-8', 'replace'))\n"
        )
        tools = {tool.name: tool for tool in tools_for("thread", item.url)}
        text = tools["python_scraping"].invoke({"source": source})
        self.assertIn("Sandhill Road", text)
        self.assertIn(item.url, text)

    @unittest.skipUnless(Path("/usr/bin/bwrap").exists(), "bwrap is not installed")
    def test_python_tool_installs_a_missing_library_into_the_work_directory(self):
        source = "import bs4\nprint(bs4.__file__)\n"
        tools = {tool.name: tool for tool in tools_for("page", "https://example.com")}
        text = tools["python_scraping"].invoke({"source": source})
        self.assertIn("/bs4/", text.replace("\\", "/"))
        self.assertNotIn("site-packages", text)
