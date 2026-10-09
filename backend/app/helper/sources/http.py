import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

TEXT_LIMIT = 12_000
USER_AGENT = "deep-research/0.1 (local research app)"

_paces = (
    ("ncbi.nlm.nih.gov", 0.34),
    ("photon-reddit.com", 0.75),
    ("api.openalex.org", 0.1),
)
_pace_locks = {host: threading.Lock() for host, _gap in _paces}
_pace_next = {host: 0.0 for host, _gap in _paces}


@dataclass(frozen=True)
class Response:
    status: int
    url: str
    data: bytes


def get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 25,
    max_bytes: int | None = None,
) -> Response | None:
    _pace(url)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request_url = _ascii_url(url)
    request = urllib.request.Request(request_url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = _body(response, max_bytes)
            if body is None:
                return None
            return Response(response.status, response.geturl(), body)
    except urllib.error.HTTPError as exc:
        try:
            body = _body(exc, max_bytes) or b""
        except Exception:
            body = b""
        return Response(exc.code, getattr(exc, "url", url), body)
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
        return None


def _body(response, max_bytes: int | None) -> bytes | None:
    if max_bytes is None:
        return response.read()
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        return None
    return data


def _ascii_url(url: str) -> str:
    # urllib writes the request line as ASCII. A title such as Mauleón has to
    # be percent-encoded or the download raises and the research run stops.
    parts = urlsplit(url)
    path_safe = "/%:@!$&'()*+,;=~"
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe=path_safe),
        quote(parts.query, safe=path_safe + "?"),
        quote(parts.fragment, safe=path_safe),
    ))


def _pace(url: str) -> None:
    host = urlparse(url).netloc.lower()
    for suffix, gap in _paces:
        if suffix not in host:
            continue
        with _pace_locks[suffix]:
            delay = _pace_next[suffix] - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            _pace_next[suffix] = time.monotonic() + gap
        return
