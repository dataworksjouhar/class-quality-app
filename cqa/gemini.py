"""The one Gemini wrapper (D5). Every model call in the app goes through `interact`.

- Interactions API, store=False on every call (not overridable).
- Inline parts only: media goes as base64 in the request; the Files API is never used.
- Model and SDK version pinned here and in requirements.txt.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import google.genai
from google import genai

MODEL = "gemini-3.8-flash"  # stable; checked against ai.google.dev/gemini-api/docs/models on 2026-10-22
SDK_VERSION = "2.32.0"
# Paid tier, USD per 1M tokens, valid until 2026-12-31 (doubles from 2027-01-01). Output includes thinking.
PRICE_IN = 0.75
PRICE_OUT = 3.75
MAX_INLINE_BYTES = 18 * 1024 * 1024  # keep the whole request under the ~20 MB inline limit
CALL_TIMEOUT_S = 240  # slowest normal call in the evaluation took ~125 s; some calls hang (D21)
# Retries per interact() (D23). A hung call (timeout) is retried once. Connection errors, rate limits and server
# errors are usually short blips, so they get up to 3 retries with growing waits. Worst case stays bounded.
MAX_TIMEOUT_RETRIES = 1
TRANSIENT_BACKOFF_S = (5, 15, 30)

if google.genai.__version__ != SDK_VERSION:
    raise RuntimeError(f"google-genai {google.genai.__version__} installed; this wrapper is pinned to {SDK_VERSION}.")

_client: genai.Client | None = None
_client_lock = threading.Lock()


def client() -> genai.Client:
    """One shared client, created once under a lock. Without the lock, parallel chunk threads each created a client;
    the spare ones were garbage-collected and the SDK closed a connection still in use ("client has been closed"), D23."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            try:
                import streamlit as st

                key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                key = None
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        _client = genai.Client(api_key=key)
    return _client


# ---------------------------------------------------------------- inline parts
def text(t: str) -> dict:
    return {"type": "text", "text": t}


def audio(path: Path, mime: str = "audio/m4a") -> dict:
    return {"type": "audio", "data": base64.b64encode(Path(path).read_bytes()).decode(), "mime_type": mime}


def image(path: Path, mime: str = "image/jpeg", resolution: str = "medium") -> dict:
    return {"type": "image", "data": base64.b64encode(Path(path).read_bytes()).decode(),
            "mime_type": mime, "resolution": resolution}


# ---------------------------------------------------------------- call
@dataclass
class Result:
    data: dict | None  # parsed JSON, or None if it never parsed
    raw_text: str
    status: str
    seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    input_by_modality: dict = field(default_factory=dict)
    attempts: int = 1
    api_errors: int = 0
    calls: list = field(default_factory=list)  # one entry per HTTP attempt: seconds and outcome (never content)

    @property
    def cost_usd(self) -> float:
        # thought tokens are billed at the output rate
        return (self.input_tokens * PRICE_IN + (self.output_tokens + self.thought_tokens) * PRICE_OUT) / 1e6


def interact(system: str, parts: list[dict], schema: dict, *, thinking_level: str = "medium",
             max_output_tokens: int = 32768, seed: int | None = None, timeout_s: float = CALL_TIMEOUT_S) -> Result:
    """One stateless, structured-output call. Retries once on invalid JSON (observer merge rule 6) and once on an
    API error or timeout (D21)."""
    size = sum(len(p.get("data", "")) for p in parts)
    if size > MAX_INLINE_BYTES:
        raise ValueError(f"Inline payload is {size / 1e6:.1f} MB; the limit is {MAX_INLINE_BYTES / 1e6:.0f} MB.")
    gen = {"thinking_level": thinking_level, "max_output_tokens": max_output_tokens}
    if seed is not None:
        gen["seed"] = seed
    total = Result(None, "", "", 0.0, attempts=0)
    parses = timeouts = transient = 0
    while parses < 2:
        t0 = time.time()
        try:
            r = client().interactions.create(
                model=MODEL,
                store=False,
                system_instruction=system,
                input=parts,  # a flat list of content parts is one user turn
                response_format={"type": "text", "mime_type": "application/json", "schema": schema},
                generation_config=gen,
                timeout=timeout_s,
            )
        except Exception as e:
            total.seconds += time.time() - t0
            total.api_errors += 1
            code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
            total.calls.append({"s": round(time.time() - t0, 1), "outcome": f"{type(e).__name__}{f' {code}' if code else ''}"})
            if code is not None and 400 <= int(code) < 500 and int(code) not in (408, 429):
                raise  # a bad request will not get better by retrying
            if "Timeout" in type(e).__name__:
                timeouts += 1
                if timeouts > MAX_TIMEOUT_RETRIES:
                    raise
                continue
            transient += 1
            if transient > len(TRANSIENT_BACKOFF_S):
                raise
            time.sleep(TRANSIENT_BACKOFF_S[transient - 1])
            continue
        parses += 1
        total.seconds += time.time() - t0
        total.calls.append({"s": round(time.time() - t0, 1), "outcome": "ok"})
        total.attempts += 1
        u = r.usage
        if u is not None:
            total.input_tokens += u.total_input_tokens or 0
            total.output_tokens += u.total_output_tokens or 0
            total.thought_tokens += u.total_thought_tokens or 0
            for m in u.input_tokens_by_modality or []:
                key = str(getattr(m.modality, "value", m.modality)).lower()
                total.input_by_modality[key] = total.input_by_modality.get(key, 0) + (m.tokens or 0)
        total.status = str(getattr(r.status, "value", r.status))
        total.raw_text = r.output_text or ""
        try:
            total.data = json.loads(total.raw_text)
            return total
        except json.JSONDecodeError:
            continue
    return total
