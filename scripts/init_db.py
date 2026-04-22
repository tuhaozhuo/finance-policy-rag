#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print("database initialized")
