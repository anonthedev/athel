import json
import unittest
from unittest.mock import patch

from app.helper.sources import load_specialized, load_specialized_html
from app.helper.sources.doi import (
    abstract_text,
    choose_pdf,
    doi_from_html,
    doi_from_url,
    load as load_doi,
)
from app.helper.sources.http import Response
from app.helper.sources.pubmed import identify, load as load_pubmed, parse_record, select_sections
from app.helper.sources.reddit import load as load_reddit, post_id, render
from app.helper.sources.reddit import Comment, Thread
from app.helper.sources.substack import api_url, matches, matches_html, render_post

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>31991704</PMID>
      <Article>
        <Journal>
          <Title>Example Journal</Title>
          <JournalIssue><PubDate><Year>2020</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Sedentary time in adults.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Sitting is common.</AbstractText>
          <AbstractText Label="RESULTS">The mean was 8 hours.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
          <Author><CollectiveName>Example Group</CollectiveName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">31991704</ArticleId>
        <ArticleId IdType="pmc">PMC7037491</ArticleId>
        <ArticleId IdType="doi">10.1000/example</ArticleId>
      </ArticleIdList>
      <ReferenceList>
        <Reference>
          <ArticleIdList>
            <ArticleId IdType="pmc">PMC0000001</ArticleId>
          </ArticleIdList>
        </Reference>
      </ReferenceList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""

JATS = b"""<?xml version="1.0"?>
<article>
  <body>
    <sec><title>1. Introduction</title><p>Intro text.</p></sec>
    <sec><title>3. Results</title><p>Result text about hours.</p></sec>
    <sec><title>References</title><p>Should not appear.</p></sec>
  </body>
</article>
"""


def response(payload, url="https://example.test"):
    if isinstance(payload, bytes):
        data = payload
    else:
        data = json.dumps(payload).encode()
    return Response(200, url, data)


class PubMedTests(unittest.TestCase):
    def test_identify_article_urls_and_ignore_search(self):
        self.assertEqual(identify("https://pubmed.ncbi.nlm.nih.gov/31991704/"), ("pmid", "31991704"))
        self.assertEqual(identify("https://www.ncbi.nlm.nih.gov/pubmed/42"), ("pmid", "42"))
        self.assertEqual(identify("https://pmc.ncbi.nlm.nih.gov/articles/PMC7037491/"), ("pmcid", "PMC7037491"))
        self.assertEqual(identify("https://europepmc.org/article/MED/31991704"), ("pmid", "31991704"))
        self.assertEqual(identify("https://pubmed.ncbi.nlm.nih.gov/?term=sedentary"), ("", ""))

    def test_record_uses_article_ids_not_references(self):
        record = parse_record(PUBMED_XML)
        self.assertEqual(record.pmid, "31991704")
        self.assertEqual(record.pmcid, "PMC7037491")
        self.assertIn("Ada Lovelace, Example Group", record.text)
        self.assertIn("BACKGROUND: Sitting is common.", record.text)
        self.assertIn("DOI: 10.1000/example", record.text)
        self.assertNotIn("PMC0000001", record.text)

    def test_fulltext_prefers_results_and_skips_references(self):
        text = select_sections(JATS, 4000)
        self.assertIn("Result text about hours.", text)
        self.assertNotIn("Should not appear.", text)
        self.assertLess(text.index("Results"), text.index("Introduction"))

    def test_load_chains_id_conversion_abstract_and_full_text(self):
        def fetch(url, headers=None):
            del headers
            if "idconv" in url:
                return response({"records": [{"pmid": "31904595", "pmcid": "PMC7012345"}]})
            if "efetch" in url:
                self.assertIn("id=31904595", url)
                return response(PUBMED_XML.replace(b"31991704", b"31904595"))
            if "fullTextXML" in url:
                self.assertIn("PMC7037491", url)
                return response(JATS)
            return None

        text, source = load_pubmed("https://pmc.ncbi.nlm.nih.gov/articles/PMC7012345/", "hours", fetch=fetch)
        self.assertEqual(source, "https://pubmed.ncbi.nlm.nih.gov/31904595/")
        self.assertIn("Result text about hours.", text)


class RedditTests(unittest.TestCase):
    def test_post_id_from_thread_and_short_link(self):
        self.assertEqual(post_id("https://www.reddit.com/r/python/comments/Ab12cd/title/"), "ab12cd")
        self.assertEqual(post_id("https://redd.it/ab12cd"), "ab12cd")
        self.assertIsNone(post_id("https://www.reddit.com/r/python/"))
        self.assertIsNone(post_id("https://i.redd.it/photo.jpg"))

    def test_render_orders_by_score_and_skips_empty_threads(self):
        thread = Thread(
            title="Database startup",
            subreddit="python",
            author="ada",
            score=10,
            selftext="It takes 30 seconds.",
            external="",
            permalink="/r/python/comments/ab12cd/database_startup/",
            comments=[
                Comment("low", "bob", 1, "same", [Comment("reply", "bea", 4, "index first")]),
                Comment("high", "cy", 8, "measured 4 seconds after the index"),
            ],
        )
        text = render(thread, "low")
        self.assertLess(text.index("u/bob"), text.index("u/cy"))
        self.assertIn("u/bea (4): index first", text)
        self.assertEqual(render(Thread("T", "", "", 0, "", "", "", [])), "")

    def test_archive_fallback_builds_a_thread(self):
        def fetch(url, headers=None):
            del headers
            if "old.reddit.com" in url:
                return Response(403, "https://old.reddit.com/login/?reason=lor2", b"")
            if "/api/posts/ids" in url:
                return response({"data": [{
                    "title": "Database startup",
                    "subreddit": "python",
                    "author": "ada",
                    "score": 3,
                    "selftext": "It takes 30 seconds.",
                    "url": "https://www.reddit.com/r/python/comments/ab12cd/database_startup/",
                    "permalink": "/r/python/comments/ab12cd/database_startup/",
                }]})
            if "/api/comments/search" in url:
                return response({"data": [
                    {"id": "c1", "author": "AutoModerator", "score": 1, "body": "rules", "parent_id": "t3_ab12cd"},
                    {"id": "c5", "author": "BehaveBot", "score": 1, "body": "Please read this entire message", "parent_id": "t3_ab12cd", "stickied": True},
                    {"id": "c2", "author": "bea", "score": 5, "body": "[removed]", "parent_id": "t3_ab12cd"},
                    {"id": "c3", "author": "cy", "score": 9, "body": "An index cut it to 4 seconds.", "parent_id": "t3_ab12cd"},
                    {"id": "c4", "author": "dee", "score": 2, "body": "Which column?", "parent_id": "t1_c3"},
                ]})
            return None

        text, source = load_reddit("https://redd.it/ab12cd", "startup time", fetch=fetch)
        self.assertEqual(source, "https://www.reddit.com/r/python/comments/ab12cd/database_startup/")
        self.assertIn("An index cut it to 4 seconds.", text)
        self.assertIn("u/dee (2): Which column?", text)
        self.assertNotIn("AutoModerator", text)
        self.assertNotIn("BehaveBot", text)
        self.assertNotIn("[removed]", text)

    def test_archive_retries_after_a_timeout(self):
        calls = {"comments": 0}

        def fetch(url, headers=None):
            del headers
            if "old.reddit.com" in url:
                return Response(403, url, b"")
            if "/api/posts/ids" in url:
                return response({"data": [{
                    "title": "Database startup",
                    "subreddit": "python",
                    "author": "ada",
                    "score": 3,
                    "selftext": "It takes 30 seconds.",
                    "permalink": "/r/python/comments/ab12cd/database_startup/",
                }]})
            if "/api/comments/search" in url:
                calls["comments"] += 1
                if calls["comments"] == 1:
                    return Response(422, url, b'{"error":"Timeout"}')
                return response({"data": [{
                    "id": "c3",
                    "author": "cy",
                    "score": 9,
                    "body": "An index helped.",
                    "parent_id": "t3_ab12cd",
                }]})
            return None

        with patch("app.helper.sources.reddit.time.sleep"):
            text, _source = load_reddit("https://redd.it/ab12cd", "startup", fetch=fetch)
        self.assertEqual(calls["comments"], 2)
        self.assertIn("An index helped.", text)


class SubstackTests(unittest.TestCase):
    def test_api_urls(self):
        self.assertEqual(
            api_url("https://astralcodexten.substack.com/p/our-ai-midwife?utm=1"),
            "https://astralcodexten.substack.com/api/v1/posts/our-ai-midwife",
        )
        self.assertEqual(
            api_url("https://open.substack.com/pub/astralcodexten/p/our-ai-midwife"),
            "https://astralcodexten.substack.com/api/v1/posts/our-ai-midwife",
        )
        self.assertEqual(
            api_url("https://www.lennysnewsletter.com/p/summit"),
            "https://lennysnewsletter.com/api/v1/posts/summit",
        )
        self.assertTrue(matches("https://astralcodexten.substack.com/p/our-ai-midwife"))
        self.assertTrue(matches("https://www.lennysnewsletter.com/p/summit"))
        self.assertFalse(matches("https://www.lennysnewsletter.com/"))

    def test_render_full_post_and_paid_preview(self):
        body = "<p>" + ("Sitting time averaged eight hours. " * 4) + "</p>"
        text = render_post({
            "title": "Sedentary hours",
            "subtitle": "A note",
            "audience": "everyone",
            "post_date": "2024-05-01T12:00:00Z",
            "publishedBylines": [{"name": "Ada Lovelace"}],
            "body_html": body,
            "canonical_url": "https://example.substack.com/p/sedentary-hours",
        })
        self.assertIn("Title: Sedentary hours", text)
        self.assertIn("Author: Ada Lovelace", text)
        self.assertIn("Sitting time averaged eight hours.", text)

        paid = render_post({
            "title": "Paid note",
            "audience": "only_paid",
            "body_html": "<p>" + ("secret " * 30) + "</p>",
            "truncated_body_text": "The free preview says the effect was small.",
        })
        self.assertIn("The free preview says the effect was small.", paid)
        self.assertIn("Paid post", paid)
        self.assertNotIn("secret", paid)
        self.assertEqual(render_post({"title": "Product", "audience": "everyone", "body_html": ""}), "")

    def test_html_marker(self):
        self.assertTrue(matches_html('<script src="https://cdn.substack.com/bundle.js"></script>'))
        self.assertFalse(matches_html("<html><body><p>A normal blog.</p></body></html>"))


WORK = {
    "title": "Sedentary time in adults",
    "publication_year": 2020,
    "doi": "https://doi.org/10.3390/example",
    "authorships": [
        {"author": {"display_name": "Ada Lovelace"}},
        {"author": {"display_name": "Alan Turing"}},
    ],
    "primary_location": {"source": {"display_name": "Example Journal"}},
    "abstract_inverted_index": {"Sitting": [0], "is": [1], "common.": [2]},
    "locations": [
        {"version": "submittedVersion", "pdf_url": "https://repo.example/preprint.pdf"},
        {"version": "publishedVersion", "pdf_url": "https://publisher.example/paper.pdf"},
    ],
}


class DoiTests(unittest.TestCase):
    def test_doi_from_resolver_and_publisher_urls(self):
        self.assertEqual(doi_from_url("https://doi.org/10.3390/ijerph17030758"), "10.3390/ijerph17030758")
        self.assertEqual(doi_from_url("https://dx.doi.org/10.1038/nphys1170."), "10.1038/nphys1170")
        self.assertEqual(
            doi_from_url("https://link.springer.com/article/10.1007/s00134-021-06352-4"),
            "10.1007/s00134-021-06352-4",
        )
        self.assertIsNone(doi_from_url("https://www.nature.com/articles/nature12373"))

    def test_doi_from_publisher_meta(self):
        html = '<meta name="citation_doi" content="10.1038/s41586-021-03819-2">'
        self.assertEqual(doi_from_html(html), "10.1038/s41586-021-03819-2")
        self.assertIsNone(doi_from_html('<meta name="dc.identifier" content="PMID:31991704">'))

    def test_abstract_and_published_pdf(self):
        self.assertEqual(abstract_text(WORK["abstract_inverted_index"]), "Sitting is common.")
        self.assertEqual(choose_pdf(WORK["locations"]), "https://publisher.example/paper.pdf")

    def test_load_uses_openalex_record(self):
        def fetch(url, headers=None):
            del headers
            self.assertIn("10.3390%2Fexample", url)
            return response(WORK)

        text, source = load_doi("https://doi.org/10.3390/example", "sitting", fetch=fetch)
        self.assertEqual(source, "https://doi.org/10.3390/example")
        self.assertIn("Title: Sedentary time in adults", text)
        self.assertIn("Ada Lovelace, Alan Turing", text)
        self.assertIn("Sitting is common.", text)
        self.assertIn("Journal: Example Journal (2020)", text)

    def test_publisher_html_resolves_the_doi(self):
        html = '<meta name="citation_doi" content="10.1038/s41586-021-03819-2">'
        with patch("app.helper.sources.doi.load_html", return_value=("Title: A paper\n\nAbstract\nYes.", "https://doi.org/10.1038/s41586-021-03819-2")) as loader:
            loaded = load_specialized_html("https://www.nature.com/articles/s41586-021-03819-2", html, "question")
        self.assertEqual(loaded[1], "https://doi.org/10.1038/s41586-021-03819-2")
        loader.assert_called_once()


class DispatchTests(unittest.TestCase):
    def test_failed_adapter_falls_through(self):
        class Broken:
            def matches(self, url):
                return True

            def load(self, url, question):
                raise RuntimeError("down")

        self.assertIsNone(load_specialized("https://pubmed.ncbi.nlm.nih.gov/1/", "q", sources=(Broken(),)))

    def test_custom_domain_post_uses_the_api(self):
        with patch("app.helper.sources.substack.load", return_value=("Title: Summit\n\nBody", "https://www.lennysnewsletter.com/p/summit")) as loader:
            loaded = load_specialized("https://www.lennysnewsletter.com/p/summit", "summit")
        self.assertEqual(loaded[0], "Title: Summit\n\nBody")
        loader.assert_called_once()

    def test_load_text_prefers_specialized_reader(self):
        import app.nodes.search as search

        with patch.object(search, "load_specialized", return_value=("Abstract alpha", "https://pubmed.ncbi.nlm.nih.gov/1/")):
            with patch.object(search, "fetch_response") as fetch:
                loaded = search.load_text("https://pubmed.ncbi.nlm.nih.gov/1/", "question")
        self.assertEqual(loaded, ("Abstract alpha", "https://pubmed.ncbi.nlm.nih.gov/1/"))
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
