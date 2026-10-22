"""Getting a recording onto local disk: Google Drive link (main path) or upload (small files).

Drive downloads stream to disk through gdown, run as a subprocess so a watchdog can
stop it if the file grows past the size limit or the download hangs.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable
from urllib.parse import urlparse

import requests

from . import config


class IntakeError(Exception):
    """A problem the user can fix; the message is shown as is."""


RESTRICTED_MSG = (
    "This Drive file is not shared publicly. In Google Drive, open Share → General access → "
    "'Anyone with the link' (Viewer), then paste the link again."
)
QUOTA_MSG = (
    "Google Drive is refusing downloads of this file for now (too many downloads in 24 hours). "
    "Make a copy in your Drive, share the copy with 'Anyone with the link', and use that link."
)
FOLDER_MSG = "That is a folder link. Open the recording inside the folder and share the link to the file itself."


# ---------------------------------------------------------------- job folders
def new_job_dir() -> Path:
    cleanup_old_jobs()
    d = config.DATA_DIR / uuid.uuid4().hex[:12]
    d.mkdir(parents=True)
    return d


def cleanup_old_jobs(max_age_s: float = 3600) -> None:
    """Remove job folders left behind by crashed or abandoned runs."""
    if not config.DATA_DIR.exists():
        return
    now = time.time()
    for d in config.DATA_DIR.iterdir():
        if d.is_dir() and now - d.stat().st_mtime > max_age_s:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- Drive
_ID_PATTERNS = [re.compile(r"/file/d/([\w-]{20,})"), re.compile(r"[?&]id=([\w-]{20,})")]


def drive_file_id(link: str) -> str:
    link = link.strip()
    if re.fullmatch(r"[\w-]{25,}", link):
        return link
    host = urlparse(link).netloc.lower()
    if not host.endswith(("drive.google.com", "docs.google.com", "drive.usercontent.google.com")):
        raise IntakeError("That does not look like a Google Drive link.")
    if "/folders/" in link:
        raise IntakeError(FOLDER_MSG)
    for pat in _ID_PATTERNS:
        if m := pat.search(link):
            return m[1]
    raise IntakeError("Could not find a file ID in that Drive link.")


@dataclass
class Preflight:
    size: int | None  # bytes, if Drive told us


def preflight(file_id: str) -> Preflight:
    """Ask Drive for the file's headers only, to catch restricted or oversized files early.

    Advisory: if the answer is unclear we let gdown try and rely on its errors and the watchdog.
    """
    try:
        r = requests.get(
            "https://drive.usercontent.google.com/download",
            params={"id": file_id, "export": "download", "confirm": "t"},
            stream=True, timeout=30, allow_redirects=True,
        )
    except requests.RequestException:
        return Preflight(size=None)
    with r:
        if "accounts.google.com" in urlparse(r.url).netloc or r.status_code in (401, 403):
            raise IntakeError(RESTRICTED_MSG)
        if r.status_code == 404:
            raise IntakeError("Drive says this file does not exist. Check the link.")
        ctype = r.headers.get("Content-Type", "")
        if ctype.startswith("text/html"):
            page = r.raw.read(200_000, decode_content=True).decode("utf-8", "replace").lower()
            if "too many users" in page or "quota" in page:
                raise IntakeError(QUOTA_MSG)
            if "sign in" in page or "request access" in page:
                raise IntakeError(RESTRICTED_MSG)
            return Preflight(size=None)
        size = int(r.headers["Content-Length"]) if r.headers.get("Content-Length", "").isdigit() else None
    if size is not None and size > config.MAX_DOWNLOAD_BYTES:
        raise IntakeError(f"The file is {size / 1e9:.2f} GB. The limit is {config.MAX_DOWNLOAD_BYTES / 1e9:.1f} GB.")
    return Preflight(size=size)


def _dir_bytes(d: Path) -> int:
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())


def download_drive(link: str, job_dir: Path, progress: Callable[[int, int | None], None] | None = None) -> Path:
    """Download a public Drive file into job_dir. progress(bytes_so_far, total_or_None)."""
    file_id = drive_file_id(link)
    total = preflight(file_id).size
    dl_dir = job_dir / "download"
    dl_dir.mkdir()
    out = dl_dir / "source.media"
    cmd = [sys.executable, "-m", "gdown", file_id, "-O", str(out), "--no-cookies", "--quiet"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    start = time.time()
    try:
        while proc.poll() is None:
            got = _dir_bytes(dl_dir)
            if progress:
                progress(got, total)
            if got > config.MAX_DOWNLOAD_BYTES:
                proc.kill()
                raise IntakeError(f"The file is larger than {config.MAX_DOWNLOAD_BYTES / 1e9:.1f} GB. Download stopped.")
            if time.time() - start > config.DOWNLOAD_TIMEOUT_S:
                proc.kill()
                raise IntakeError("The download took too long and was stopped. Try again later.")
            time.sleep(0.5)
        err = proc.stderr.read().decode("utf-8", "replace")
    except BaseException:
        proc.kill()
        shutil.rmtree(dl_dir, ignore_errors=True)
        raise
    if proc.returncode != 0 or not out.exists():
        shutil.rmtree(dl_dir, ignore_errors=True)
        low = err.lower()
        if "too many users" in low or "quota" in low:
            raise IntakeError(QUOTA_MSG)
        if "permission" in low or "public link" in low or "access" in low:
            raise IntakeError(RESTRICTED_MSG)
        raise IntakeError("The Drive download failed. Check that the link opens in a private browser window.")
    if progress:
        progress(out.stat().st_size, out.stat().st_size)
    return out


# ---------------------------------------------------------------- upload
def save_upload(fileobj: BinaryIO, job_dir: Path) -> Path:
    out = job_dir / "source.media"
    with open(out, "wb") as f:
        shutil.copyfileobj(fileobj, f, length=4 * 1024 * 1024)
    return out
