# Deep Research

A desktop app that turns one question into a sourced Markdown report. You ask a topic in an Electron window. A LangGraph pipeline on a local FastAPI server breaks the topic into questions, lets you edit them, searches the web, reads HTML and PDFs, and writes the report. Finished reports stay on disk and show up in the sidebar.

## Install

Download a build from the [releases](https://github.com/anonthedev/deep-research/releases) page. `<version>` below is the release number without the leading `v`, so tag `v0.0.3` uses `0.0.3` in the filename. After the app opens, enter an OpenRouter API key. It stays on this computer.

### macOS

1. Download `Athel-<version>.dmg`.
2. Move the file to `/Applications`.
3. The build is not notarized, so macOS may refuse to open it. Clear the quarantine flag:

```bash
xattr -cr /Applications/Athel-<version>.dmg
```

4. Open the disk image and drag Athel into the Applications folder.
5. Open Athel from Applications.

### Windows

1. Download `Athel-<version>-setup.exe`.
2. Run the installer.
3. Open Athel from the desktop shortcut or the Start menu.

### Linux

AppImage:

```bash
chmod +x Athel-<version>.AppImage
./Athel-<version>.AppImage
```

Debian and Ubuntu:

```bash
sudo apt install ./athel_<version>_amd64.deb
```

## How it works

The Electron main process starts the Python backend if `http://127.0.0.1:8000/health` is not already up, then opens the React window. Submitting a topic posts to `POST /research`. The server runs the graph in a background thread and streams progress as server-sent events. After the questions are drafted, the graph pauses. You edit them in the window, and `POST /research/{thread_id}/resume` continues the run. When the writer finishes, the report is saved and the window switches from the live trace to the rendered Markdown. Aborting posts to `POST /research/{thread_id}/abort` and the stream ends with `aborted`.

```mermaid
flowchart TD
  UI["Electron + React"] -->|"POST /research (SSE)"| API["FastAPI"]
  API --> Graph["LangGraph"]
  Graph --> Gaps["generate_gaps"]
  Gaps --> Review["review_gaps (pause)"]
  Review -->|"POST /resume with edited questions"| Draft["draft_queries"]
  Draft --> Search["search (Tavily or DuckDuckGo)"]
  Search --> Hits["collect_hits"]
  Hits --> Scrape["scrape"]
  Scrape --> Fetch["download the URL"]
  Fetch --> Kind{"response is a PDF?"}
  Kind -->|yes| Pdf["pdf_excerpt: PyMuPDF, then rank passages"]
  Kind -->|no| Html["trafilatura"]
  Html --> Cite{"citation_pdf_url with a usable excerpt?"}
  Cite -->|yes| Pdf
  Cite -->|no| Extract["extractor"]
  Pdf -->|"non-empty excerpt"| Extract
  Extract --> Check["update_checklist"]
  Check -->|"pending gaps remain"| Draft
  Check -->|"nothing left to chase"| Write["write_final_report"]
  Write --> Disk["reports directory"]
  Disk --> UI
```

The diagram below is the path through the app. [Architecture](ARCHITECTURE.md) is the full pipeline, including how a PDF is split, ranked, and sent to the extractor. If you prefer excalidraw then [Architecture PNG](Architecture.png) or [Excalidraw File](Architecture.excalidraw)

Each pass fans out. Pending gaps are drafted in parallel, each query is searched in parallel, and each new URL is scraped in parallel. `collect_hits` and `update_checklist` are deferred nodes: they wait until every branch of that wave has finished before the graph continues.

A download whose bytes are a PDF goes through `pdf_excerpt` in `backend/app/helper/pdf.py`. PyMuPDF reads the pages, the text is split into overlapping passages, and the run’s embedding model ranks those passages against the gap question. The highest-scoring passages, up to twelve and within a character budget, are what the extractor sees, each marked with its page. An empty excerpt is dropped and the extractor is not called. An HTML page that publishes a `citation_pdf_url` is followed to that PDF when the download returns a non-empty excerpt. Otherwise the HTML text is kept.

A gap is **resolved** when notes cover the question. It stays **pending** and is searched again, this time only for the missing parts, until it has been tried `max_iterations` times. That limit is 1–10 and defaults to 3. After that, a gap with notes is **partial** and a gap with none is **failed**. The writer states what a partial gap established and what is still missing, and says briefly that a failed gap was not established. Hosts that fail to download are added to a blocked-domain list and skipped on later loops. Search defaults to DuckDuckGo. Tavily is used only when that engine is selected and a Tavily API key is set.

## Models

Each run uses an OpenRouter key and five models you choose in the window. The catalog comes from [OpenRouter](https://openrouter.ai/). The key stays in the browser’s local storage on this computer and is sent only to the local server, which uses it for that run and does not write it to disk. A Tavily key, when you add one, is stored the same way and is required only when the search engine is Tavily.

Planner, scraper, and extractor choices are limited to models that accept tool calls, because those steps return structured data. The writer can be any text model. The embedding model is chosen from OpenRouter’s embedding catalog and is used only to rank passages inside a PDF.

| Role | Default | Job |
| --- | --- | --- |
| Planner | `openai/gpt-5-mini` | Split the topic into 5–7 questions, write search queries, and list what a gap still lacks |
| Scraper | `openai/gpt-5-mini` | Choose a reader for each URL, and write a Python script when those readers return nothing |
| Extractor | `google/gemini-3.1-flash-lite` | Read a scraped page and keep only the facts that answer the question, or useful side notes |
| Writer | `anthropic/claude-sonnet-5` | Turn the evidence dossier into one Markdown report with inline source links |
| Embedding | `openai/text-embedding-3-small` | Rank PDF passages against the gap question so the extractor sees the relevant pages |

The writer is instructed to use only facts from the dossier, keep specific names, dates, and numbers, and cite the URL attached to the note the sentence came from.

## Repository layout

```
deep-research/
├── backend/
│   ├── main.py                 # FastAPI app, SSE stream, report files
│   ├── app/
│   │   ├── graph.py            # LangGraph wiring
│   │   ├── states.py           # Shared state and models
│   │   ├── llm.py              # OpenRouter clients
│   │   ├── helper/
│   │   │   └── pdf.py          # PDF text, passage ranking
│   │   └── nodes/
│   │       ├── planning.py     # gaps, review, queries, checklist
│   │       ├── search.py       # search, HTML scrape, PDF hop
│   │       └── report.py       # final Markdown
│   ├── reports/                # saved reports (gitignored)
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── main/               # Electron: window + backend process
        ├── preload/
        └── renderer/           # React UI
```

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Node.js with [pnpm](https://pnpm.io/)
- An [OpenRouter](https://openrouter.ai/keys) API key, entered in the app

## Setup

From the repo root:

```bash
cd backend
uv sync

cd ../frontend
pnpm install
pnpm dev
```

`pnpm dev` starts Electron. On launch the main process spawns `backend/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload` when that port is not already healthy, and kills that process when the app quits. A packaged build starts the bundled `server` binary instead.

To run the API on its own:

```bash
cd backend
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The desktop UI talks to `http://127.0.0.1:8000`. CORS allows the Vite dev origin `http://localhost:5173`.

Packaged builds:

```bash
cd frontend
pnpm build:linux   # or build:win / build:mac
```

## Using the app

1. Enter an OpenRouter API key. Pick a planner, extractor, writer, and embedding model. Choose DuckDuckGo or Tavily, and how many times a gap may be searched. Tavily asks for its own key when none is saved. Type a question or pick a suggestion. Submit with the button or Ctrl/⌘+Enter.
2. The planner drafts the questions and the run pauses. Edit, add, or remove them, then choose **Start research**. At least one question is required. **Abort** returns to the question form.
3. The sidebar lists the run under **Ongoing research**. The main pane shows questions, search hits, findings, dead URLs, and gap status as they arrive. **Abort** is available on that trace as well.
4. When the stream finishes, the Markdown report opens and the run is filed under **Reports**. The folder button beside that heading opens the reports directory.
5. Earlier reports load from disk. On startup the most recently updated report opens automatically.

Report filenames use the first 40 characters of the topic slug. In development that file is `backend/reports/<slug>.md`. A packaged build writes to the app user-data `reports` directory, set with `DEEP_RESEARCH_REPORTS`. Asking the same topic again overwrites that file.

## HTTP API

| Method | Path | Response |
| --- | --- | --- |
| `GET` | `/health` | `{ "status": "ok" }` |
| `GET` | `/models` | OpenRouter catalog: `{ id, name, tools }`. `tools` is true when the model can fill the planner or extractor role |
| `POST` | `/openrouter/key` | Checks a key. Body: `{ "api_key": "..." }`. `{ "ok": true }`, or 401 if OpenRouter rejects it |
| `POST` | `/embedding-models` | OpenRouter embedding catalog. Body: `{ "api_key": "..." }` |
| `POST` | `/research` | SSE stream. Body: `{ "topic", "thread_id", "api_key", "planner_model", "extractor_model", "writer_model", "embedding_model", "max_iterations", "search_engine", "tavily_api_key" }`. `max_iterations` is 1–10 and defaults to 3. `search_engine` is `duckduckgo` (the default) or `tavily`. `tavily_api_key` is required when the engine is Tavily |
| `POST` | `/research/{thread_id}/resume` | SSE stream that continues a paused run. Body: `{ "questions", "api_key", "planner_model", "extractor_model", "writer_model", "embedding_model", "tavily_api_key" }`. `questions` is 1–7 non-empty strings. 404 if that thread is not paused |
| `POST` | `/research/{thread_id}/abort` | Stops that run. `{ "ok": true }` |
| `GET` | `/reports` | JSON list of `{ slug, title, updated_at }`, newest first |
| `GET` | `/reports/{slug}` | Raw Markdown |

SSE payloads are `data: {json}\n\n` lines. A comment ping (`: ping`) is sent if a graph step is quiet for 15 seconds.

| `type` | When | Fields |
| --- | --- | --- |
| `gaps` | Questions are drafted | `questions` |
| `review` | The graph pauses so you can edit the questions | `thread_id`, `questions`, optional `error` |
| `search` | A query returns URLs | `gap_id`, `urls` |
| `finding` | A page yields a note | `gap_id`, `source`, `answers`, `note` |
| `dead_url` | A download fails | `url` |
| `gap` | Checklist updates | `id`, `question`, `status`, `missing` |
| `activity` | A long step has started. The trace shows this until the next event | `message` |
| `report` | The writer finishes | `markdown` |
| `done` | The graph finished. A review pause sends `review` instead | |
| `aborted` | The run was aborted | |
| `error` | The graph raised | `message` |

`status` on a gap is `pending`, `resolved`, `partial`, or `failed`.

## Graph state

`OverallState` in `backend/app/states.py` is the shared blackboard:

- `topic` — the question from the UI
- `gaps` — checklist items (`id`, `question`, `status`, `notes`, `missing`, `attempts`)
- `hits` — search URLs, appended across branches
- `findings` — extracted notes, appended across scrapes
- `additional_info` — useful facts that did not answer their question
- `dead_urls` and `blocked_domains` — failed fetches, appended across scrapes
- `final_report` — the Markdown the writer returned
- `max_iterations` — how many times a pending gap may be searched
- `search_engine` — `duckduckgo` or `tavily`
- `research_loops` — set to 0 when the run starts and left unchanged

`hits`, `findings`, `dead_urls`, and `blocked_domains` use a list reducer so parallel branches accumulate instead of overwriting each other.

## Evals
`excerpt_pages` in `backend/app/helper/pdf.py` ranks passages from a PDF against the question and keeps up to twelve. The eval in `backend/evals/pdf_eval/` downloads 25 papers, runs that ranking with `openai/text-embedding-3-small`, and checks three things: every page that contains a known fact is among the pages passed on, that fact’s text is in the excerpt, and bibliography pages are left out. The IPCC summary has no bibliography, so it is left out of the last score.
From `backend/`, with `OPENROUTER_API_KEY` in `backend/.env`:
```bash
uv run python evals/extractor_eval/run_eval.py
uv run python evals/checklist_eval/run_eval.py
uv run python evals/pdf_eval/run_eval.py
uv run python evals/scraper_eval/run_eval.py
uv run python evals/script_eval/run_eval.py
```

### Scraper

`scrape` is the reader agent, using `openai/gpt-5-mini`. Claim extraction still uses `google/gemini-3.1-flash-lite`. Each case stubs the readers, so the run never downloads a page. The Python tool is stubbed the same way: the script is recorded, and the tool returns the case text instead of running it. The grader checks that the agent calls the reader the URL needs, in that order, and that the note comes from the text that reader returned. A publisher page must be read with `doi`, and the finding keeps that tool’s DOI link. A PubMed URL whose record is missing must fall through to `trafilatura`. When every reader returns nothing, the agent must call `python_scraping`, and the script must contain the page URL. A failed download must block the host. Run on 7 Oct 2026: 12/12 passed.

| Case | Result | Reader calls |
| --- | --- | --- |
| pubmed | pass | pubmed |
| doi | pass | doi |
| reddit | pass | reddit |
| substack | pass | substack |
| page | pass | trafilatura |
| publisher | pass | doi, and the note kept the DOI link |
| fallback | pass | pubmed, then trafilatura |
| dead | pass | trafilatura, and the host was blocked |
| script_page | pass | trafilatura, then python_scraping |
| script_pubmed | pass | pubmed, trafilatura, then python_scraping |
| script_doi | pass | doi, trafilatura, then python_scraping |
| script_dead | pass | trafilatura, then python_scraping, and the host was blocked |

### Script

This eval runs the script the scraper writes against public pages. The other readers are stubbed so the agent has to write the script; the script itself is executed and downloads the real URL. A library the script imports that is not already installed is installed into the script’s directory before it runs. The grader checks that the script contains that URL, that its output includes a fact from the live page, and that the extractor’s note does too. Run on 7 Oct 2026: 3/5 passed.

| Case | Page | Result |
| --- | --- | --- |
| marketplace | IKEA BILLY bookcase | fail. The script ran and described the bookcase, but not with the phrases the grader required |
| blog | Paul Graham, “How to Do Great Work” | pass |
| social | Hacker News item 1 | fail. The site answered 419 to the script’s user agent |
| recipe | Allrecipes chocolate chip cookies | pass |
| reference | Wikipedia, French press | pass |

### Extractor

`scrape` reads a fixed page with `google/gemini-3.1-flash-lite`. The grader checks required spans, banned numbers, and whether a finding should exist at all. Run on 6 Oct 2026: 12/13 passed.

| Case | Result | What came back |
| --- | --- | --- |
| simner_decoy | pass | Note kept Simner, 2006, 1.1%, and Scotland, and left out 18% |
| partial_sample | pass | Note kept 1.1% and did not invent a sample size |
| related_study | pass | Empty note. Additional: Wikoff et al. (2017) on caffeine and sleep latency |
| paywall | pass | No finding |
| page_marker | pass | Note starts with `(p. 4)` and keeps the 14% reduction |
| both_present | pass | Note kept 0.96 Å on CASP14 and left out the CASP13 system |
| bibliography | pass | No finding. The citation list states no result |
| gallery | pass | No finding. The installation caption was left out |
| survival | pass | Note kept 62% for the 2018 velpanib trial and did not use 840 patients |
| handset | pass | Note kept the March 2024 US list price of $799 |
| retracted | pass | Note kept the 9.1% intention-to-treat rate |
| regimen | fail | No finding. Note and additional were both empty |
| dose_units | pass | Note kept 1.1 g and did not convert it to 1100 mg |

### Checklist

`update_checklist` reads the notes with `openai/gpt-5-mini` and decides whether the gap is finished. Run on 6 Oct 2026: 10/10 passed.

| Case | Result | Status | Still missing |
| --- | --- | --- | --- |
| answered | pass | resolved | nothing |
| vague | pass | pending | Simner et al. (2006) Scottish sample percentage |
| partial_sample | pass | pending | Simner et al. 2006 sample size |
| disagreement | pass | pending | Consensus estimate, study name and date for the 1.1% survey, study name and date for the 4% survey |
| price_complete | pass | resolved | nothing |
| hedged | pass | resolved | nothing |
| agreeing | pass | resolved | nothing |
| price_wrong_date | pass | pending | Date $799 listed, who reported $799, source page publication date |
| study_not_limit | pass | pending | Regulatory daily caffeine limit, plus FDA, EFSA, and UK NHS limits |
| half_sourced | pass | pending | Simner 2006 sample age, 4% estimate source, 4% estimate sample age |

### PDF eval

Run on 6 Oct 2026: recall 52/72 (0.72), relevant text included 24/25 (0.96), no irrelevant pages 15/24 (0.62).

| Paper | Recall | Fact in excerpt | Bibliography pages included |
| --- | --- | --- | --- |
| attention | 1/1 | yes | none |
| bert | 1/1 | yes | none |
| resnet | 1/1 | yes | none |
| adam | 3/3 | yes | none |
| batchnorm | 4/4 | yes | none |
| yolo | 1/1 | yes | none |
| gan | 1/2 | no | 9 |
| gnn | 2/3 | yes | 12, 13 |
| dropout | 4/5 | yes | 7 |
| ligo | 5/7 | yes | 10 |
| higgs | 1/3 | yes | 24, 25 |
| planck | 1/4 | yes | none |
| alphafold | 1/1 | yes | none |
| crispr | 3/3 | yes | none |
| pubchem | 1/1 | yes | 12 |
| mpnn | 1/1 | yes | none |
| zhang | 2/2 | yes | 54 |
| greentao | 3/4 | yes | 56 |
| perelman | 3/7 | yes | none |
| kepler | 1/1 | yes | 19, 20 |
| reproducibility | 1/1 | yes | none |
| henrich | 3/8 | yes | none |
| chexnet | 5/5 | yes | none |
| economist | 2/2 | yes | none |
| ipcc | 1/1 | yes | n/a |

## License

MIT. See [LICENSE](LICENSE).
