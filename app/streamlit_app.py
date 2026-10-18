"""Streamlit app backward-compatible entry point — delegates to app/main.py."""

import sys
from pathlib import Path

# Ensure repo root and app directory are in sys.path
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.main import main

if __name__ == "__main__":
    main()
