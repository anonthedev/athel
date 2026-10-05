from app.helper.sources import doi, pubmed, reddit, substack

# URL adapters run before trafilatura. A site module needs matches(url) and
# load(url, question) -> (text, source) | None. A DOI in publisher HTML, and a
# Substack publication on its own domain, are recognized after the download.
SOURCES = (pubmed, doi, reddit, substack)


def load_specialized(url: str, question: str, sources=SOURCES) -> tuple[str, str] | None:
    for source in sources:
        if not source.matches(url):
            continue
        try:
            loaded = source.load(url, question)
        except Exception:
            return None
        if loaded and loaded[0].strip():
            return loaded[0].strip(), loaded[1]
        return None
    return None


def _text(loaded) -> tuple[str, str] | None:
    if loaded and loaded[0].strip():
        return loaded[0].strip(), loaded[1]
    return None


def load_specialized_html(url: str, html: str, question: str) -> tuple[str, str] | None:
    if not doi.matches(url):
        try:
            found = _text(doi.load_html(url, html, question))
        except Exception:
            found = None
        if found:
            return found
    if substack.matches(url) or not substack.matches_html(html):
        return None
    try:
        return _text(substack.load(url, question))
    except Exception:
        return None
