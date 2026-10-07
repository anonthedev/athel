import os
import re
import shutil
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from app.helper.sources import doi as doi_source
from app.helper.sources import pubmed as pubmed_source
from app.helper.sources import reddit as reddit_source
from app.helper.sources import substack as substack_source
from app.llm import extractor_llm, scraper_llm
from app.nodes.search import HTML_LIMIT, fetch_response, host_of, is_pdf, landed_url, load_text, response_html
from app.progress import announce
from app.prompts import extract_page, scrape_instructions
from app.states import Finding

DOWNLOAD_FAILED = "Download failed."
NO_TEXT = "The script returned no text."
_MISSING_MODULE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_IMPORTED = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_PIP_NAME = {
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "yaml": "pyyaml",
    "sklearn": "scikit-learn",
    "dateutil": "python-dateutil",
    "Crypto": "pycryptodome",
}


def imported_modules(source: str) -> list[str]:
    return list(dict.fromkeys(_IMPORTED.findall(source)))


def missing_module(stderr: str) -> str | None:
    found = _MISSING_MODULE.search(stderr)
    if found is None:
        return None
    name = found.group(1).split(".", 1)[0]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return None
    return name


def interpreter() -> tuple[list[str], list[Path]]:
    if getattr(sys, "frozen", False):
        return [sys.executable], [Path(sys.executable).resolve().parent]
    exe = Path(sys.executable)
    roots = [exe.resolve().parent.parent]
    if exe.is_symlink():
        roots.insert(0, exe.parent.parent)
    return [str(exe)], roots


def jail_command(work: Path, program: list[str]) -> list[str]:
    _, roots = interpreter()
    resolv = Path("/etc/resolv.conf").resolve()
    command = [
        "/usr/bin/bwrap",
        "--unshare-all", "--share-net", "--die-with-parent", "--clearenv",
        "--setenv", "HOME", str(work),
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "TMPDIR", str(work),
        "--setenv", "PIP_TARGET", str(work),
        "--setenv", "PIP_DISABLE_PIP_VERSION_CHECK", "1",
        "--ro-bind", "/usr", "/usr",
    ]
    for lib in ("/lib", "/lib64", "/etc/ssl", "/etc/ca-certificates"):
        if Path(lib).exists():
            command += ["--ro-bind", lib, lib]
    command += ["--ro-bind", str(resolv), "/etc/resolv.conf"]
    bound = set()
    for root in roots:
        if root in bound:
            continue
        bound.add(root)
        command += ["--ro-bind", str(root), str(root)]
    command += [
        "--bind", str(work), str(work),
        "--proc", "/proc",
        "--dev", "/dev",
        "--chdir", str(work),
        "--",
        *program,
    ]
    return command


def install_package(work: Path, package: str) -> bool:
    uv = shutil.which("uv")
    if uv is None:
        return False
    program, _roots = interpreter()
    try:
        proc = subprocess.run(
            [uv, "pip", "install", "--python", program[0], "--target", str(work), package],
            cwd=str(work),
            env={**os.environ, "UV_NO_CONFIG": "1"},
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def run_jailed(command: list[str], timeout: int) -> tuple[int, str, str] | None:
    proc = subprocess.Popen(
        command,
        env={},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.communicate()
        return None
    return proc.returncode or 0, _text(stdout), _text(stderr)


def _text(data) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


class PageResult(BaseModel):
    answers_gap: bool
    note: str
    additional: str = ""


def deliver(loaded: tuple[str, str] | None, miss: str) -> str:
    if not loaded or not str(loaded[0]).strip():
        return miss
    text = str(loaded[0]).strip()[:HTML_LIMIT]
    source = str(loaded[1] or "").strip()
    return f"Source: {source}\n\n{text}"


def _html(url: str) -> tuple[str, str] | None:
    response = fetch_response(url, decode=True)
    if response is None or response.status != 200 or not response.data or is_pdf(response.data):
        return None
    html = response_html(response)
    if not html.strip():
        return None
    return html, landed_url(url, response.url)


def tools_for(question: str, url: str):
    @tool
    def pubmed(url: str) -> str:
        """Read a PubMed, PMC, or Europe PMC article.

        Args:
            url: Article URL, such as pubmed.ncbi.nlm.nih.gov or pmc.ncbi.nlm.nih.gov.
        """
        announce("Reading PubMed")
        try:
            loaded = pubmed_source.load(url, question)
        except Exception:
            loaded = None
        return deliver(loaded, "No PubMed record at this URL.")

    @tool
    def doi(url: str) -> str:
        """Read a paper from its DOI or from a publisher article page.

        Args:
            url: A doi.org link or the publisher page for the paper.
        """
        announce("Reading the paper")
        try:
            if doi_source.matches(url):
                loaded = doi_source.load(url, question)
            else:
                fetched = _html(url)
                if fetched is None:
                    loaded = None
                else:
                    html, source = fetched
                    loaded = doi_source.load_html(source, html, question)
        except Exception:
            loaded = None
        return deliver(loaded, "No DOI record at this URL.")

    @tool
    def reddit(url: str) -> str:
        """Read a Reddit thread, including the post and the top comments.

        Args:
            url: A reddit.com, old.reddit.com, or redd.it link.
        """
        announce("Reading Reddit")
        try:
            loaded = reddit_source.load(url, question)
        except Exception:
            loaded = None
        return deliver(loaded, "No Reddit thread at this URL.")

    @tool
    def substack(url: str) -> str:
        """Read a Substack post, including a post on the publication's own domain.

        Args:
            url: A substack.com post, or a post whose path contains /p/<slug>.
        """
        announce("Reading Substack")
        try:
            if substack_source.matches(url):
                loaded = substack_source.load(url, question)
            else:
                fetched = _html(url)
                if fetched is None:
                    loaded = None
                else:
                    html, source = fetched
                    loaded = substack_source.load(source, question) if substack_source.matches_html(html) else None
        except Exception:
            loaded = None
        return deliver(loaded, "No Substack post at this URL.")

    @tool
    def trafilatura(url: str) -> str:
        """Read an ordinary web page or PDF.

        Use this when the URL is not a PubMed article, a DOI, a Reddit thread, or a Substack post, and when a more specific reader returned nothing.

        Args:
            url: Page or PDF URL.
        """
        announce("Reading the page")
        try:
            loaded = load_text(url, question)
        except Exception:
            return DOWNLOAD_FAILED
        if loaded is None:
            return DOWNLOAD_FAILED
        return deliver(loaded, "No page text at this URL.")

    @tool
    def python_scraping(source: str) -> str:
        """Run a custom Python script to read this page when the other readers return no text.
        Args:
            source: A script that prints the page text to stdout.
        """
        announce("Reading the page")

        work = Path(tempfile.mkdtemp())
        path = work / "script.py"
        path.write_text(source, encoding="utf-8")
        program, _roots = interpreter()
        script_args = ["--run", str(path)] if getattr(sys, "frozen", False) else [str(path)]
        script_cmd = jail_command(work, program + script_args)
        installed: set[str] = set()
        for module in imported_modules(source):
            if module in sys.stdlib_module_names or module in installed:
                continue
            try:
                __import__(module)
            except Exception:
                installed.add(module)
                install_package(work, _PIP_NAME.get(module, module))
        for _ in range(4):
            result = run_jailed(script_cmd, 30)
            if result is None:
                return NO_TEXT
            code, text, err = result
            if code == 0:
                return deliver((text, url), NO_TEXT)
            module = missing_module(err)
            if module is None or module in installed:
                return NO_TEXT
            installed.add(module)
            if not install_package(work, _PIP_NAME.get(module, module)):
                return NO_TEXT
        return NO_TEXT

    return [pubmed, doi, reddit, substack, trafilatura, python_scraping]

def reads_from(messages) -> tuple[list[tuple[str, str]], bool]:
    found = []
    failed = False
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        content = message.content if isinstance(message.content, str) else ""
        if content == DOWNLOAD_FAILED:
            failed = True
            continue
        if not content.startswith("Source: "):
            continue
        header, _, body = content.partition("\n\n")
        source = header.removeprefix("Source: ").strip()
        if body.strip():
            found.append((body.strip(), source))
    return found, failed


def extract_text(question: str, text: str) -> PageResult | None:
    try:
        result = extractor_llm().with_structured_output(PageResult, include_raw=True).invoke(
            extract_page(question, text)
        )
    except Exception:
        return None
    if result["parsing_error"] or result["parsed"] is None:
        return None
    return result["parsed"]


def finding_from(gap_id: int, parsed: PageResult, source: str) -> dict:
    if not parsed.note.strip() and not parsed.additional.strip():
        return {"findings": []}
    return {
        "findings": [
            Finding(
                gap_id=gap_id,
                answers_gap=parsed.answers_gap and bool(parsed.note.strip()),
                note=parsed.note.strip(),
                source=source,
                additional=parsed.additional.strip(),
            )
        ]
    }


def scrape(state: dict) -> dict:
    question = state["question"]
    url = state["url"]

    agent = create_agent(
        model=scraper_llm(),
        tools=tools_for(question, url),
        system_prompt=scrape_instructions(),
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Question:\n{question}\n\nURL:\n{url}"}]},
            {"recursion_limit": 12},
        )
    except GraphRecursionError:
        result = {}

    reads, failed = reads_from(result.get("messages"))
    if not reads:
        if failed:
            return {"dead_urls": [url], "blocked_domains": [host_of(url)], "findings": []}
        return {"findings": []}

    text, source = reads[-1]
    parsed = extract_text(question, text)
    if parsed is None:
        return {"findings": []}
    return finding_from(state["gap_id"], parsed, source or url)
