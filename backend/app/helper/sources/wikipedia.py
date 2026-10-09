import json
import re
from html import unescape
from urllib.parse import quote, urljoin, urlparse

from app.helper.sources.http import Response, get

LINK_LIMIT = 8
_SKIP_HOSTS = (".wikipedia.org", ".wikimedia.org", ".wikidata.org", ".mediawiki.org")


def matches(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    if not host.endswith(".wikipedia.org"):
        return False
    return parsed.path.startswith("/wiki/") and not parsed.path.startswith("/wiki/Special:")


def citation_links(html: str, page_url: str) -> list[str]:
    ordered = _hrefs(_section(html, "Further_reading"), page_url)
    ordered.extend(link for link in _hrefs(_references(html), page_url) if link not in ordered)
    return ordered[:LINK_LIMIT]


def article_url(topic: str, fetch=get) -> str | None:
    query = " ".join(topic.split())
    if not query:
        return None
    url = (
        "https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&namespace=0&format=json&search="
        + quote(query)
    )
    payload = _json(fetch(url, headers={"Accept": "application/json"}))
    if not isinstance(payload, list) or len(payload) < 4 or not isinstance(payload[3], list):
        return None
    for item in payload[3]:
        if isinstance(item, str) and matches(item):
            return item
    return None


def _section(html: str, heading_id: str) -> str:
    match = re.search(rf'id="{re.escape(heading_id)}"', html, re.I)
    if not match:
        return ""
    rest = html[match.end() :]
    end = re.search(r"<h2\b", rest, re.I)
    return rest[: end.start()] if end else rest


def _references(html: str) -> str:
    blocks = []
    for match in re.finditer(r"<ol\b([^>]*)>(.*?)</ol>", html, re.I | re.S):
        if re.search(r'class="[^"]*\breferences\b', match.group(1), re.I):
            blocks.append(match.group(2))
    return "\n".join(blocks)


def _hrefs(block: str, page_url: str) -> list[str]:
    found = []
    for match in re.finditer(r"""href\s*=\s*["']([^"'>\s]+)""", block, re.I):
        absolute = urljoin(page_url, unescape(match.group(1)))
        if absolute in found or not _keep(absolute):
            continue
        found.append(absolute)
    return found


def _keep(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower().removeprefix("www.")
    return not host.endswith(_SKIP_HOSTS)


def _json(response: Response | None):
    if response is None or response.status != 200 or not response.data:
        return None
    try:
        return json.loads(response.data.decode("utf-8"))
    except json.JSONDecodeError:
        return None
