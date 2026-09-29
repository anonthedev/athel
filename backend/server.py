import os
from pathlib import Path

import uvicorn

from main import app

if __name__ == "__main__":
    reports = os.environ.get("DEEP_RESEARCH_REPORTS")
    if reports:
        Path(reports).mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)