"""Short-lived report storage so a page reload (e.g. on a phone) can bring a report back (D20).

Only the finished, redacted, leak-tested report is stored: no audio, frames, logs or names. Files live in the
server's temp folder under an unguessable run ID and are deleted after REPORT_TTL_S.
"""
from __future__ import annotations

import json
import re
import secrets
import tempfile
import time
from pathlib import Path

REPORTS_DIR = Path(tempfile.gettempdir()) / "cqa_reports"
REPORT_TTL_S = 24 * 3600
_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _cleanup() -> None:
    if REPORTS_DIR.exists():
        now = time.time()
        for f in REPORTS_DIR.glob("*.json"):
            if now - f.stat().st_mtime > REPORT_TTL_S:
                f.unlink(missing_ok=True)


def save(report: dict) -> str:
    _cleanup()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = secrets.token_urlsafe(16)
    (REPORTS_DIR / f"{run_id}.json").write_text(json.dumps(report, default=str), encoding="utf-8")
    return run_id


def load(run_id: str) -> dict | None:
    if not run_id or not _ID.match(run_id):
        return None
    _cleanup()
    f = REPORTS_DIR / f"{run_id}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
