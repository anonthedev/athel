import json
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from app.helper.sources.http import TEXT_LIMIT, Response, get

_SKIP_SECTION = (
    "reference",
    "supplement",
    "author contribution",
    "funding",
    "conflict",
    "acknowledgment",
    "acknowledgement",
    "data availability",
    "associated data",
    "abbreviation",
    "ethics",
)
_SECTION_RANK = (
    ("result", 0),
    ("conclusion", 1),
    ("discussion", 2),
    ("method", 3),
    ("material", 3),
    ("introduction", 4),
    ("background", 4),
)
_BROWSER = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def matches(url: str) -> bool:
    kind, value = identify(url)
    return bool(kind and value)


def load(url: str, question: str, *, fetch=get) -> tuple[str, str] | None:
    kind, value = identify(url)
    if not kind:
        return None

    pmcid = value if kind == "pmcid" else ""
    pmid = value if kind == "pmid" else ""
    if pmcid and not pmid:
        pmid = _pmid_for_pmc(pmcid, fetch)
        if not pmid:
            return None

    record_xml = _efetch(pmid, fetch)
    if record_xml is None:
        return None
    record = parse_record(record_xml)
    if record is None:
        return None
    pmcid = record.pmcid or pmcid

    fulltext = ""
    if pmcid:
        full_xml = _fulltext(pmcid, fetch)
        room = TEXT_LIMIT - len(record.text) - 2
        if full_xml is not None and room > 400:
            fulltext = select_sections(full_xml, room)
        if not fulltext and room > 400:
            excerpt = _pmc_pdf(pmcid, question, fetch)
            fulltext = excerpt[:room].rstrip() if excerpt else ""

    text = record.text if not fulltext else f"{record.text}\n\n{fulltext}"
    text = clip(text)
    if not text:
        return None
    return text, f"https://pubmed.ncbi.nlm.nih.gov/{record.pmid}/"


def identify(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]

    if host == "pubmed.ncbi.nlm.nih.gov" and parts and parts[0].isdigit():
        return "pmid", parts[0]
    if host == "ncbi.nlm.nih.gov" and len(parts) >= 2 and parts[0] == "pubmed" and parts[1].isdigit():
        return "pmid", parts[1]
    if host == "pmc.ncbi.nlm.nih.gov" and len(parts) >= 2 and parts[0] == "articles":
        pmcid = _pmcid(parts[1])
        if pmcid:
            return "pmcid", pmcid
    if host == "ncbi.nlm.nih.gov" and len(parts) >= 3 and parts[0] == "pmc" and parts[1] == "articles":
        pmcid = _pmcid(parts[2])
        if pmcid:
            return "pmcid", pmcid
    if host == "europepmc.org" and len(parts) >= 3 and parts[0] == "article" and parts[1].upper() == "MED" and parts[2].isdigit():
        return "pmid", parts[2]
    if host == "europepmc.org" and len(parts) >= 3 and parts[0] == "article" and parts[1].upper() == "PMC":
        pmcid = _pmcid(parts[2])
        if pmcid:
            return "pmcid", pmcid
    if host == "europepmc.org" and len(parts) >= 2 and parts[0] == "articles":
        pmcid = _pmcid(parts[1])
        if pmcid:
            return "pmcid", pmcid
    return "", ""


class Record:
    def __init__(self, pmid: str, pmcid: str, text: str):
        self.pmid = pmid
        self.pmcid = pmcid
        self.text = text


def parse_record(xml: bytes) -> Record | None:
    root = _xml(xml)
    if root is None:
        return None
    article = _first(root, "PubmedArticle")
    if article is None:
        return None
    medline = _child(article, "MedlineCitation")
    paper = _child(medline, "Article") if medline is not None else None
    if paper is None:
        return None

    pmid = _text(_child(medline, "PMID"))
    if not pmid.isdigit():
        return None

    pmcid, doi = _ids(_child(article, "PubmedData"))
    title = _text(_child(paper, "ArticleTitle"))
    journal = _journal(paper)
    authors = _authors(paper)
    abstract = _abstract(paper)
    if not title and not abstract:
        return None

    lines = []
    if title:
        lines.append(f"Title: {title}")
    if authors:
        lines.append(f"Authors: {authors}")
    if journal:
        lines.append(f"Journal: {journal}")
    if doi:
        lines.append(f"DOI: {doi}")
    lines.append(f"PMID: {pmid}")
    if pmcid:
        lines.append(f"PMCID: {pmcid}")
    if abstract:
        lines.append("")
        lines.append("Abstract")
        lines.append(abstract)
    return Record(pmid, pmcid, "\n".join(lines).strip())


def select_sections(xml: bytes, budget: int) -> str:
    if budget < 200:
        return ""
    root = _xml(xml)
    if root is None:
        return ""
    body = _first(root, "body")
    if body is None:
        return ""

    ranked: list[tuple[int, int, str]] = []
    for index, section in enumerate(_children(body, "sec")):
        title = _direct_title(section)
        if _skipped(title):
            continue
        paragraphs = _section_paragraphs(section)
        if not paragraphs:
            continue
        block = f"{title}\n\n{paragraphs}".strip() if title else paragraphs
        ranked.append((_rank(title), index, block))
    ranked.sort()

    chosen: list[str] = []
    used = 0
    for _score, _index, block in ranked:
        if used + len(block) > budget and chosen:
            remaining = budget - used
            if remaining > 300:
                chosen.append(block[:remaining].rstrip())
            break
        chosen.append(block)
        used += len(block) + 2
        if used >= budget:
            break
    return "\n\n".join(chosen).strip()


def clip(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= TEXT_LIMIT:
        return text
    cut = text.rfind("\n", 0, TEXT_LIMIT)
    if cut < TEXT_LIMIT // 2:
        cut = TEXT_LIMIT
    return text[:cut].rstrip()


def _pmid_for_pmc(pmcid: str, fetch) -> str:
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={pmcid}&format=json&tool=deep-research"
    response = fetch(url, headers={"Accept": "application/json"})
    payload = _json(response)
    if not isinstance(payload, dict):
        return ""
    for record in payload.get("records") or []:
        if isinstance(record, dict) and str(record.get("pmid") or "").isdigit():
            return str(record["pmid"])
    return ""


def _efetch(pmid: str, fetch) -> bytes | None:
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={pmid}&retmode=xml&tool=deep-research"
    )
    response = fetch(url, headers={"Accept": "text/xml"})
    if response is None or response.status != 200 or not response.data:
        return None
    return response.data


def _fulltext(pmcid: str, fetch) -> bytes | None:
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    response = fetch(url, headers={"Accept": "application/xml"})
    if response is None or response.status != 200 or not response.data:
        return None
    return response.data


def _pmc_pdf(pmcid: str, question: str, fetch) -> str:
    from app.helper.pdf import embedding_configured, pdf_excerpt

    if not question.strip() or not embedding_configured():
        return ""
    url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
    response = fetch(url, headers={"User-Agent": _BROWSER, "Accept": "application/pdf"})
    if response is None or response.status != 200 or not response.data or not _is_pdf(response.data):
        return ""
    return pdf_excerpt(response.data, question)


def _is_pdf(data: bytes) -> bool:
    head = data[:1024]
    stripped = head.lstrip(b"\xef\xbb\xbf\x00 \t\r\n")
    return stripped.startswith(b"%PDF-") or b"%PDF-" in head


def _ids(pubmed_data) -> tuple[str, str]:
    if pubmed_data is None:
        return "", ""
    listing = _child(pubmed_data, "ArticleIdList")
    pmcid = ""
    doi = ""
    for node in _children(listing, "ArticleId"):
        kind = (node.attrib.get("IdType") or "").lower()
        value = _text(node)
        if kind == "pmc" and not pmcid:
            pmcid = _pmcid(value) or ""
        elif kind == "doi" and not doi:
            doi = value
    return pmcid, doi


def _journal(paper) -> str:
    journal = _child(paper, "Journal")
    if journal is None:
        return ""
    title = _text(_child(journal, "Title"))
    year = ""
    issue = _child(journal, "JournalIssue")
    pubdate = _child(issue, "PubDate") if issue is not None else None
    if pubdate is not None:
        year = _text(_child(pubdate, "Year")) or _text(_child(pubdate, "MedlineDate"))[:4]
    if title and year:
        return f"{title} ({year})"
    return title


def _authors(paper) -> str:
    listing = _child(paper, "AuthorList")
    names = []
    for author in _children(listing, "Author"):
        collective = _text(_child(author, "CollectiveName"))
        if collective:
            names.append(collective)
            continue
        fore = _text(_child(author, "ForeName")) or _text(_child(author, "Initials"))
        last = _text(_child(author, "LastName"))
        name = f"{fore} {last}".strip()
        if name:
            names.append(name)
    if len(names) > 8:
        return ", ".join(names[:8]) + ", et al."
    return ", ".join(names)


def _abstract(paper) -> str:
    abstract = _child(paper, "Abstract")
    parts = []
    for node in _children(abstract, "AbstractText"):
        text = " ".join(_text(node).split())
        if not text:
            continue
        label = (node.attrib.get("Label") or "").strip()
        parts.append(f"{label}: {text}" if label else text)
    return "\n\n".join(parts)


def _section_paragraphs(section) -> str:
    blocks: list[str] = []

    def walk(node, nested: bool) -> None:
        for child in list(node):
            name = _local(child.tag)
            if name == "title":
                if nested:
                    title = " ".join(_text(child).split())
                    if title:
                        blocks.append(title)
            elif name == "p":
                paragraph = " ".join(_text(child).split())
                if paragraph:
                    blocks.append(paragraph)
            elif name == "caption":
                caption = " ".join(_text(child).split())
                if caption:
                    blocks.append(caption)
            elif name == "sec":
                walk(child, True)

    walk(section, False)
    return "\n\n".join(blocks)


def _skipped(title: str) -> bool:
    lowered = title.lower()
    return any(phrase in lowered for phrase in _SKIP_SECTION)


def _rank(title: str) -> int:
    lowered = title.lower()
    for key, score in _SECTION_RANK:
        if key in lowered:
            return score
    return 5


def _direct_title(section) -> str:
    title = _child(section, "title")
    return " ".join(_text(title).split())


def _pmcid(value: str) -> str | None:
    match = re.fullmatch(r"(?:PMC)?(\d+)", value.strip(), re.I)
    if not match:
        return None
    return f"PMC{match.group(1)}"


def _json(response: Response | None):
    if response is None or response.status != 200 or not response.data:
        return None
    try:
        return json.loads(response.data.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _xml(data: bytes):
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node, name: str):
    if node is None:
        return None
    for child in list(node):
        if _local(child.tag) == name:
            return child
    return None


def _children(node, name: str) -> list:
    if node is None:
        return []
    return [child for child in list(node) if _local(child.tag) == name]


def _first(node, name: str):
    if node is None:
        return None
    for child in node.iter():
        if _local(child.tag) == name:
            return child
    return None


def _text(node) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()
