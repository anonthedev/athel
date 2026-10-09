import json
import unittest
from unittest.mock import Mock, patch

from app.helper.sources.doi import load_work, search_works, work_urls
from app.helper.sources.http import Response
from app.helper.sources.wikipedia import article_url, citation_links, matches
from app.nodes.planning import collapse_empty_wave, collapse_question, topic_of_collapse
from app.nodes.search import fan_out_scrapes, reset_tavily_key, scrape, search, tavily_urls, use_tavily_key
from app.states import Finding, KnowledgeGap, SourcedNote, UrlHit

WORK = {
    "title": "Sedentary time in adults",
    "publication_year": 2020,
    "doi": "https://doi.org/10.3390/example",
    "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
    "primary_location": {"source": {"display_name": "Example Journal"}},
    "abstract_inverted_index": {"Sitting": [0], "is": [1], "common.": [2]},
    "locations": [
        {"version": "publishedVersion", "pdf_url": "https://publisher.example/paper.pdf"},
    ],
}


def response(payload, url="https://example.test"):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return Response(200, url, data)

WIKI = """
<html><body>
<p>The encyclopedia says sitting is universal.</p>
<h2 id="Further_reading">Further reading</h2>
<ul>
<li><a href="https://press.example/book">A book</a></li>
<li><a href="/wiki/Sitting">Sitting</a></li>
</ul>
<h2 id="See_also">See also</h2>
<ul><li><a href="https://later.example/skip">Skip</a></li></ul>
<ol class="references">
<li><a href="https://doi.org/10.1000/xyz">doi</a></li>
<li><a href="https://en.wikipedia.org/wiki/Other">wiki</a></li>
<li><a href="https://journal.example/paper.pdf">pdf</a></li>
</ol>
</body></html>
"""


def gap(index: int, *, notes: bool = False, attempts: int = 0) -> KnowledgeGap:
    item = KnowledgeGap(id=index, question=f"Question {index}?")
    item.attempts = attempts
    if notes:
        item.notes = [SourcedNote(note="A fact.", source="https://example.test")]
    return item


class OpenAlexTests(unittest.TestCase):
    def test_search_keeps_works_with_abstracts(self):
        seen = []

        def fetch(url, headers=None):
            del headers
            seen.append(url)
            return response({
                "results": [
                    {**WORK, "id": "https://openalex.org/W1"},
                    {"id": "https://openalex.org/W2", "title": "No abstract here"},
                ]
            })

        works = search_works("sitting time", fetch=fetch)
        self.assertEqual(len(works), 1)
        self.assertIn("search=sitting%20time", seen[0])
        self.assertEqual(work_urls("sitting time", {"10.3390/example"}, fetch=fetch), [])
        self.assertEqual(
            work_urls("sitting time", set(), fetch=fetch),
            ["https://openalex.org/W1"],
        )

    def test_load_work_returns_the_abstract_without_fetching_the_pdf(self):
        def fetch(url, headers=None):
            del headers
            self.assertIn("/works/W1", url)
            self.assertNotIn(".pdf", url)
            return response({**WORK, "id": "https://openalex.org/W1"})

        text, source, pdf_url = load_work("https://openalex.org/W1", "sitting", fetch=fetch)
        self.assertEqual(source, "https://doi.org/10.3390/example")
        self.assertIn("Sitting is common.", text)
        self.assertEqual(pdf_url, "https://publisher.example/paper.pdf")


class WikipediaTests(unittest.TestCase):
    def test_citation_links_skip_the_article_and_later_sections(self):
        self.assertTrue(matches("https://en.wikipedia.org/wiki/Sedentary_lifestyle"))
        self.assertFalse(matches("https://en.wikipedia.org/wiki/Special:Search"))
        links = citation_links(WIKI, "https://en.wikipedia.org/wiki/Sedentary_lifestyle")
        self.assertEqual(
            links,
            [
                "https://press.example/book",
                "https://doi.org/10.1000/xyz",
                "https://journal.example/paper.pdf",
            ],
        )

    def test_citation_links_stop_at_eight(self):
        items = "\n".join(f'<li><a href="https://journal.example/{index}">x</a></li>' for index in range(12))
        html = f'<ol class="references">{items}</ol>'
        links = citation_links(html, "https://en.wikipedia.org/wiki/Topic")
        self.assertEqual(len(links), 8)
        self.assertEqual(links[0], "https://journal.example/0")
        self.assertEqual(links[-1], "https://journal.example/7")

    def test_article_url(self):
        payload = ["sitting", ["Sedentary lifestyle"], [""], ["https://en.wikipedia.org/wiki/Sedentary_lifestyle"]]
        found = article_url("sitting", fetch=lambda url, headers=None: response(payload))
        self.assertEqual(found, "https://en.wikipedia.org/wiki/Sedentary_lifestyle")
        special = ["sitting", ["Search"], [""], ["https://en.wikipedia.org/wiki/Special:Search"]]
        self.assertIsNone(article_url("sitting", fetch=lambda url, headers=None: response(special)))


class CollapseTests(unittest.TestCase):
    def test_most_empty_questions_become_one(self):
        gaps = [gap(1, notes=True), gap(2), gap(3), gap(4)]
        collapsed = collapse_empty_wave(gaps, "sitting", first_wave=True)
        self.assertEqual([item.id for item in collapsed], [1, 5])
        self.assertEqual(collapsed[1].question, collapse_question("sitting"))
        self.assertEqual(topic_of_collapse(collapsed[1].question + "\nStill needed:\nA number"), "sitting")

    def test_half_empty_or_a_later_wave_stays_split(self):
        half = [gap(1, notes=True), gap(2, notes=True), gap(3), gap(4)]
        self.assertEqual(collapse_empty_wave(half, "sitting", first_wave=True), half)
        empty = [gap(1), gap(2), gap(3)]
        self.assertEqual(collapse_empty_wave(empty, "sitting", first_wave=False), empty)
        self.assertEqual(collapse_empty_wave([gap(1)], "sitting", first_wave=True), [gap(1)])
        all_empty = collapse_empty_wave([gap(1), gap(2), gap(3)], "sitting", first_wave=True)
        self.assertEqual([item.question for item in all_empty], [collapse_question("sitting")])


class ScrapeTests(unittest.TestCase):
    def test_irrelevant_abstract_does_not_download_the_pdf(self):
        state = {"url": "https://openalex.org/W1", "question": "Is sitting common?", "gap_id": 1}
        with patch("app.nodes.search.load_work", return_value=("Abstract\nSitting.", "https://doi.org/10.1/x", "https://pub.example/p.pdf")):
            with patch("app.nodes.search.read_page", return_value=None):
                with patch("app.nodes.search.excerpt_pdf") as pdf:
                    result = scrape(state)
        pdf.assert_not_called()
        self.assertEqual(result["findings"][0].source, "https://openalex.org/W1")
        self.assertEqual(result["findings"][0].note, "")
        self.assertEqual(
            fan_out_scrapes({"findings": result["findings"], "hits": [UrlHit(gap_id=1, question="q", url=state["url"])], "dead_urls": [], "blocked_domains": []}),
            "update_checklist",
        )

    def test_relevant_abstract_then_downloads_the_pdf(self):
        state = {"url": "https://openalex.org/W1", "question": "Is sitting common?", "gap_id": 1}
        abstract = Finding(gap_id=1, answers_gap=True, note="Sitting is common.", source="https://doi.org/10.1/x")
        fuller = Finding(gap_id=1, answers_gap=True, note="(p. 4) Sitting is common in 40%.", source="https://doi.org/10.1/x")
        with patch("app.nodes.search.load_work", return_value=("Abstract\nSitting.", "https://doi.org/10.1/x", "https://pub.example/p.pdf")):
            with patch("app.nodes.search.read_page", side_effect=[abstract, fuller]) as read:
                with patch("app.nodes.search.excerpt_pdf", return_value="[p.4]\n40%") as pdf:
                    result = scrape(state)
        pdf.assert_called_once()
        self.assertIn("[p.4]", read.call_args_list[1].args[1])
        self.assertEqual(result["findings"][0].note, fuller.note)
        self.assertEqual(result["findings"][1].note, "")

    def test_wikipedia_scrapes_citations_instead_of_the_article(self):
        state = {"url": "https://en.wikipedia.org/wiki/Sedentary_lifestyle", "question": "Is sitting common?", "gap_id": 1}
        page = Mock(status=200, data=WIKI.encode(), url=state["url"])
        finding = Finding(gap_id=1, answers_gap=True, note="The study measured 8 hours.", source="https://press.example/book")

        def load(url, question):
            del question
            self.assertNotIn("wikipedia.org", url)
            return f"Text from {url}", url

        with patch("app.nodes.search.fetch_page", return_value=page):
            with patch("app.nodes.search.load_text", side_effect=load):
                with patch("app.nodes.search.read_page", return_value=finding) as read:
                    result = scrape(state)
        texts = [call.args[1] for call in read.call_args_list]
        self.assertTrue(texts)
        self.assertTrue(all("encyclopedia" not in text for text in texts))
        self.assertTrue(all(item.note != "The encyclopedia says sitting is universal." for item in result["findings"]))
        self.assertEqual(result["findings"][0].source, state["url"])
        self.assertEqual(result["findings"][0].note, "")

    def test_rewritten_citation_marks_the_requested_url_visited(self):
        state = {
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1271596/",
            "question": "Was the 1973 study an experiment?",
            "gap_id": 3,
        }
        finding = Finding(
            gap_id=3,
            answers_gap=True,
            note="It was an experiment.",
            source="https://pubmed.ncbi.nlm.nih.gov/4783416/",
        )
        with patch("app.nodes.search.load_text", return_value=("Abstract and passages.", finding.source)):
            with patch("app.nodes.search.read_page", return_value=finding):
                result = scrape(state)
        self.assertEqual([item.source for item in result["findings"]], [finding.source, state["url"]])
        self.assertEqual(result["findings"][1].note, "")
        self.assertEqual(
            fan_out_scrapes({
                "findings": result["findings"],
                "hits": [UrlHit(gap_id=3, question=state["question"], url=state["url"])],
                "dead_urls": [],
                "blocked_domains": [],
            }),
            "update_checklist",
        )

    def test_rewritten_url_stays_visited_when_the_page_adds_nothing(self):
        state = {"url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234254/", "question": "mechanism", "gap_id": 4}
        with patch("app.nodes.search.load_text", return_value=("Abstract only.", "https://pubmed.ncbi.nlm.nih.gov/838624/")):
            with patch("app.nodes.search.read_page", return_value=None):
                result = scrape(state)
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0].source, state["url"])
        self.assertEqual(result["findings"][0].note, "")

    def test_failed_download_does_not_block_the_rest_of_the_host(self):
        dead = "https://doi.org/10.1136/bmj.310.6992.1455"
        sibling = "https://doi.org/10.1136/bmj.310.6992.1456"
        state = {"url": dead, "question": "rete", "gap_id": 1}
        with patch("app.nodes.search.load_text", return_value=None):
            result = scrape(state)
        self.assertEqual(result["dead_urls"], [dead])
        self.assertNotIn("blocked_domains", result)
        sends = fan_out_scrapes({
            "findings": [],
            "hits": [
                UrlHit(gap_id=1, question="rete", url=dead),
                UrlHit(gap_id=1, question="rete", url=sibling),
            ],
            "dead_urls": [dead],
            "blocked_domains": [],
        })
        self.assertEqual([item.arg["url"] for item in sends], [sibling])

    def test_search_drops_researchgate_and_sciencedirect(self):
        state = {
            "gap_id": 1,
            "query": "rete ovarii",
            "question": "What is the rete ovarii?",
            "search_engine": "duckduckgo",
            "blocked_domains": [],
        }
        found = [
            "https://www.researchgate.net/publication/1",
            "https://www.sciencedirect.com/science/article/pii/S1",
            "https://pdf.sciencedirect.com/paper.pdf",
            "https://journal.example/paper",
        ]
        with patch("app.nodes.search.duckduckgo_urls", return_value=found):
            with patch("app.nodes.search.work_urls", return_value=[]):
                hits = search(state)["hits"]
        self.assertEqual([hit.url for hit in hits], ["https://journal.example/paper"])

    def test_tavily_excludes_researchgate_and_sciencedirect(self):
        client = Mock()
        client.search.return_value = {"results": []}
        token = use_tavily_key("token")
        try:
            with patch("app.nodes.search.TavilyClient", return_value=client):
                tavily_urls("rete ovarii", set())
        finally:
            reset_tavily_key(token)
        excluded = set(client.search.call_args.kwargs["exclude_domains"])
        self.assertIn("researchgate.net", excluded)
        self.assertIn("sciencedirect.com", excluded)

    def test_search_adds_openalex_works_and_a_wikipedia_map(self):
        state = {
            "gap_id": 1,
            "query": "sitting time",
            "question": "Is sitting common?",
            "search_engine": "duckduckgo",
            "blocked_domains": [],
        }
        with patch("app.nodes.search.duckduckgo_urls", return_value=["https://doi.org/10.3390/example"]):
            with patch("app.nodes.search.work_urls", return_value=["https://openalex.org/W9"]) as works:
                with patch("app.nodes.search.article_url", return_value="https://en.wikipedia.org/wiki/Sitting") as wiki:
                    hits = search(state)["hits"]
        works.assert_called_once()
        self.assertEqual(works.call_args.args[1], {"10.3390/example"})
        wiki.assert_not_called()
        self.assertEqual([hit.url for hit in hits], ["https://doi.org/10.3390/example", "https://openalex.org/W9"])

        state["question"] = collapse_question("sitting")
        with patch("app.nodes.search.duckduckgo_urls", return_value=[]):
            with patch("app.nodes.search.work_urls", return_value=[]):
                with patch("app.nodes.search.article_url", return_value="https://en.wikipedia.org/wiki/Sitting") as wiki:
                    hits = search(state)["hits"]
        wiki.assert_called_once_with("sitting")
        self.assertEqual(hits[0].url, "https://en.wikipedia.org/wiki/Sitting")


if __name__ == "__main__":
    unittest.main()
