import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.helper.sources.http import TEXT_LIMIT, Response, get

_HOSTS = {"reddit.com", "old.reddit.com", "np.reddit.com", "redd.it"}
_REMOVED = {"[removed]", "[deleted]"}
_COMMENT_LIMIT = 12
_REPLY_LIMIT = 2
_COMMENT_CHARS = 1_200


@dataclass
class Comment:
    id: str
    author: str
    score: int
    body: str
    replies: list["Comment"] = field(default_factory=list)


@dataclass
class Thread:
    title: str
    subreddit: str
    author: str
    score: int
    selftext: str
    external: str
    permalink: str
    comments: list[Comment]


def matches(url: str) -> bool:
    return post_id(url) is not None


def load(url: str, question: str, *, fetch=get) -> tuple[str, str] | None:
    del question
    identifier = post_id(url)
    if not identifier:
        return None
    focus = comment_id(url)
    thread = _from_reddit(identifier, fetch) or _from_archive(identifier, fetch)
    if thread is None:
        return None
    text = render(thread, focus)
    if not text:
        return None
    return text, canonical(thread.permalink, identifier)


def post_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in _HOSTS:
        return None
    if host == "redd.it":
        segment = parsed.path.strip("/").split("/", 1)[0]
        if re.fullmatch(r"[a-z0-9]{4,12}", segment, re.I):
            return segment.lower()
        return None
    match = re.search(r"/comments/([a-z0-9]{4,12})(?:/|$)", parsed.path, re.I)
    if match:
        return match.group(1).lower()
    return None


def comment_id(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "comments" not in parts:
        return ""
    index = parts.index("comments")
    if len(parts) > index + 3 and re.fullmatch(r"[a-z0-9]{4,12}", parts[index + 3], re.I):
        return parts[index + 3].lower()
    return ""


def render(thread: Thread, focus: str = "") -> str:
    comments = list(thread.comments)
    if focus:
        comments.sort(key=lambda comment: (comment.id != focus, -comment.score))
    else:
        comments.sort(key=lambda comment: -comment.score)
    comments = comments[:_COMMENT_LIMIT]
    if not thread.selftext and not comments:
        return ""

    lines = [f"Title: {thread.title}"]
    if thread.subreddit:
        lines.append(f"Subreddit: r/{thread.subreddit}")
    if thread.author:
        lines.append(f"Author: u/{thread.author}")
    if thread.score:
        lines.append(f"Score: {thread.score}")
    if thread.external:
        lines.append(f"Link: {thread.external}")
    if thread.selftext:
        lines.append("")
        lines.append(thread.selftext.strip())
    if comments:
        lines.append("")
        lines.append("Comments:")
        for comment in comments:
            lines.append(_render_comment(comment, 0))
    text = "\n".join(lines).strip()
    if len(text) <= TEXT_LIMIT:
        return text
    cut = text.rfind("\n", 0, TEXT_LIMIT)
    if cut < TEXT_LIMIT // 2:
        cut = TEXT_LIMIT
    return text[:cut].rstrip()


def canonical(permalink: str, identifier: str) -> str:
    if permalink.startswith("http"):
        return permalink.split("?", 1)[0]
    if permalink.startswith("/"):
        return "https://www.reddit.com" + permalink.split("?", 1)[0]
    return f"https://www.reddit.com/comments/{identifier}/"


def _from_reddit(identifier: str, fetch) -> Thread | None:
    url = f"https://old.reddit.com/comments/{identifier}.json?raw_json=1&limit=50"
    payload = _json(fetch(url, headers={"Accept": "application/json"}))
    if not isinstance(payload, list) or not payload:
        return None
    try:
        post = payload[0]["data"]["children"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return None
    comments = []
    if len(payload) > 1:
        children = (payload[1].get("data") or {}).get("children") or []
        for child in children:
            if isinstance(child, dict) and child.get("kind") == "t1":
                parsed = _comment(child)
                if parsed:
                    comments.append(parsed)
    return _thread(post, comments)


def _from_archive(identifier: str, fetch) -> Thread | None:
    post_url = f"https://arctic-shift.photon-reddit.com/api/posts/ids?ids={identifier}"
    comment_url = f"https://arctic-shift.photon-reddit.com/api/comments/search?link_id={identifier}&limit=100"
    post_payload = _fetch_json(post_url, fetch)
    if not isinstance(post_payload, dict):
        return None
    rows = [row for row in post_payload.get("data") or [] if isinstance(row, dict)]
    if not rows:
        return None
    comment_payload = _fetch_json(comment_url, fetch)
    flat = []
    if isinstance(comment_payload, dict):
        flat = [row for row in comment_payload.get("data") or [] if isinstance(row, dict)]
    return _thread(rows[0], _tree(flat))


def _thread(post: dict, comments: list[Comment]) -> Thread | None:
    title = " ".join(str(post.get("title") or "").split())
    if not title:
        return None
    selftext = str(post.get("selftext") or "").strip()
    if selftext.lower() in _REMOVED:
        selftext = ""
    outbound = str(post.get("url") or "").strip()
    external = ""
    if outbound and "reddit.com" not in outbound and "redd.it" not in outbound:
        external = outbound
    try:
        score = int(post.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return Thread(
        title=title,
        subreddit=str(post.get("subreddit") or ""),
        author=str(post.get("author") or ""),
        score=score,
        selftext=selftext,
        external=external,
        permalink=str(post.get("permalink") or ""),
        comments=comments,
    )


def _tree(rows: list[dict]) -> list[Comment]:
    nodes: dict[str, Comment] = {}
    parents: dict[str, str] = {}
    for row in rows:
        body = str(row.get("body") or "").strip()
        if not body or body.lower() in _REMOVED:
            continue
        author = str(row.get("author") or "")
        if _bot(author) or row.get("stickied"):
            continue
        identifier = str(row.get("id") or "")
        if not identifier:
            continue
        try:
            score = int(row.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        nodes[identifier] = Comment(identifier, author or "[deleted]", score, _shorten(body))
        parents[identifier] = str(row.get("parent_id") or "")

    roots: list[Comment] = []
    for identifier, comment in nodes.items():
        parent = parents.get(identifier, "")
        parent_id = parent[3:] if parent.startswith("t1_") else ""
        if parent_id and parent_id in nodes:
            nodes[parent_id].replies.append(comment)
        else:
            roots.append(comment)
    return roots


def _comment(child: dict) -> Comment | None:
    data = child.get("data") or {}
    author = str(data.get("author") or "")
    if _bot(author) or data.get("stickied"):
        return None
    body = str(data.get("body") or "").strip()
    if not body or body.lower() in _REMOVED:
        return None
    replies = []
    raw = data.get("replies")
    if isinstance(raw, dict):
        for nested in (raw.get("data") or {}).get("children") or []:
            if isinstance(nested, dict) and nested.get("kind") == "t1":
                parsed = _comment(nested)
                if parsed:
                    replies.append(parsed)
    try:
        score = int(data.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return Comment(str(data.get("id") or ""), author or "[deleted]", score, _shorten(body), replies)


def _render_comment(comment: Comment, depth: int) -> str:
    indent = "  " * depth
    line = f"{indent}- u/{comment.author} ({comment.score}): {comment.body}"
    if depth >= 1:
        return line
    replies = sorted(comment.replies, key=lambda item: -item.score)[:_REPLY_LIMIT]
    return "\n".join([line, *(_render_comment(reply, depth + 1) for reply in replies)])


def _bot(author: str) -> bool:
    name = author.lower()
    return name == "automoderator" or name.endswith("bot")


def _shorten(body: str) -> str:
    body = " ".join(body.split())
    if len(body) <= _COMMENT_CHARS:
        return body
    return body[:_COMMENT_CHARS].rstrip() + "..."


def _fetch_json(url: str, fetch):
    response = fetch(url, headers={"Accept": "application/json"})
    payload = _json(response)
    if payload is not None or response is None or response.status not in {422, 429, 503}:
        return payload
    time.sleep(1.2)
    return _json(fetch(url, headers={"Accept": "application/json"}))


def _json(response: Response | None):
    if response is None or response.status != 200 or not response.data:
        return None
    if "/login" in (response.url or ""):
        return None
    try:
        return json.loads(response.data.decode("utf-8"))
    except json.JSONDecodeError:
        return None
