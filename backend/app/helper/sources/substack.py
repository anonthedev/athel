import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

from trafilatura import extract

from app.helper.sources.http import TEXT_LIMIT, Response, get

_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,180}")


def matches(url: str) -> bool:
    host, parts = _split(url)
    if not host:
        return False
    if host == "open.substack.com":
        return len(parts) >= 4 and parts[0] == "pub" and parts[2] == "p" and _slug(parts[3])
    if host.endswith(".substack.com"):
        publication = host.removesuffix(".substack.com")
        return bool(publication) and publication not in {"open", "api", "reader"} and _post_slug(parts) is not None
    # Publications on their own domain still use /p/<slug> and the public API.
    return _post_slug(parts) is not None


def matches_html(html: str) -> bool:
    sample = html[:300_000].lower()
    return (
        "substackcdn.com" in sample
        or "cdn.substack.com" in sample
        or 'content="substack"' in sample
        or "window._preloads" in sample
    )


def load(url: str, question: str, *, fetch=get) -> tuple[str, str] | None:
    del question
    api = api_url(url)
    if not api:
        return None
    response = fetch(api, headers={"Accept": "application/json"})
    payload = _json(response)
    if not isinstance(payload, dict):
        return None
    text = render_post(payload)
    if not text:
        return None
    source = payload.get("canonical_url") or url
    if not str(source).startswith(("http://", "https://")):
        source = url
    return text, str(source).split("?", 1)[0]


def api_url(url: str) -> str | None:
    host, parts = _split(url)
    if host == "open.substack.com" and len(parts) >= 4 and parts[0] == "pub" and parts[2] == "p" and _slug(parts[3]):
        return f"https://{parts[1]}.substack.com/api/v1/posts/{quote(parts[3])}"
    slug = _post_slug(parts)
    if not slug:
        return None
    if host.endswith(".substack.com"):
        publication = host.removesuffix(".substack.com")
        if not publication or publication in {"open", "api", "reader"}:
            return None
        return f"https://{publication}.substack.com/api/v1/posts/{quote(slug)}"
    if host.endswith("substack.com"):
        return None
    return f"https://{host}/api/v1/posts/{quote(slug)}"


def render_post(post: dict) -> str:
    title = " ".join(str(post.get("title") or "").split())
    subtitle = " ".join(str(post.get("subtitle") or "").split())
    audience = str(post.get("audience") or "")
    body_html = str(post.get("body_html") or "")
    preview = str(post.get("truncated_body_text") or "").strip()
    full = html_to_text(body_html)
    paid = audience not in {"", "everyone"}
    if paid and preview:
        body = preview
        notice = "[Paid post. Only the free preview is included.]"
    else:
        body = full or preview
        notice = ""
    if not body:
        return ""

    lines = []
    if title:
        lines.append(f"Title: {title}")
    authors = _authors(post)
    if authors:
        lines.append(f"Author: {authors}")
    published = str(post.get("post_date") or "")[:10]
    if published:
        lines.append(f"Date: {published}")
    if subtitle:
        lines.append(f"Subtitle: {subtitle}")
    if notice:
        lines.append(notice)
    if body:
        lines.append("")
        lines.append(body)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(text) <= TEXT_LIMIT:
        return text
    cut = text.rfind("\n", 0, TEXT_LIMIT)
    if cut < TEXT_LIMIT // 2:
        cut = TEXT_LIMIT
    return text[:cut].rstrip()


def html_to_text(fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment:
        return ""
    extracted = extract(f"<html><body>{fragment}</body></html>") or ""
    if len(extracted.strip()) >= 40:
        return extracted.strip()
    parser = _Text()
    parser.feed(fragment)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "br", "h1", "h2", "h3", "h4", "li", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        if tag in {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "div"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip == 0:
            self.parts.append(data)


def _authors(post: dict) -> str:
    names = []
    for byline in post.get("publishedBylines") or []:
        if isinstance(byline, dict) and byline.get("name"):
            names.append(str(byline["name"]))
    return ", ".join(names)


def _split(url: str) -> tuple[str, list[str]]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    return host, parts


def _post_slug(parts: list[str]) -> str | None:
    if len(parts) >= 2 and parts[0] == "p" and _slug(parts[1]):
        return parts[1]
    return None


def _slug(value: str) -> bool:
    return _SLUG.fullmatch(value) is not None


def _json(response: Response | None):
    if response is None or response.status != 200 or not response.data:
        return None
    try:
        return json.loads(response.data.decode("utf-8"))
    except json.JSONDecodeError:
        return None
