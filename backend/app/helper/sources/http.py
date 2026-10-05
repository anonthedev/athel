import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

TEXT_LIMIT = 12_000
USER_AGENT = "deep-research/0.1 (local research app)"

_paces = (
    ("ncbi.nlm.nih.gov", 0.34),
    ("photon-reddit.com", 0.75),
)
_pace_locks = {host: threading.Lock() for host, _gap in _paces}
_pace_next = {host: 0.0 for host, _gap in _paces}


@dataclass(frozen=True)
class Response:
    status: int
    url: str
    data: bytes


def get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 25) -> Response | None:
    _pace(url)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Response(response.status, response.geturl(), response.read())
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return Response(exc.code, getattr(exc, "url", url), body)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


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
