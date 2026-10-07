import os
from pathlib import Path
import uvicorn
import certifi
import sys

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

if __name__ == "__main__" and sys.argv[1:2]==["--run"]:
    import runpy
    runpy.run_path(sys.argv[2], run_name="__main__")
    raise SystemExit(0)

from main import app

if __name__ == "__main__":
    reports = os.environ.get("DEEP_RESEARCH_REPORTS")
    if reports:
        Path(reports).mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)