"""The one Gemini wrapper (D5). Every model call in the app goes through `interact`.

- Interactions API, store=False on every call (not overridable).
- Inline parts only: media goes as base64 in the request; the Files API is never used.
- Model and SDK version pinned here and in requirements.txt.
"""
from __future__ import annotations

import base64
import json
import os
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

if google.genai.__version__ != SDK_VERSION:
    raise RuntimeError(f"google-genai {google.genai.__version__} installed; this wrapper is pinned to {SDK_VERSION}.")

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
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

    @property
    def cost_usd(self) -> float:
        # thought tokens are billed at the output rate
        return (self.input_tokens * PRICE_IN + (self.output_tokens + self.thought_tokens) * PRICE_OUT) / 1e6


def interact(system: str, parts: list[dict], schema: dict, *, thinking_level: str = "medium",
             max_output_tokens: int = 32768, seed: int | None = None, timeout_s: float = 600) -> Result:
    """One stateless, structured-output call. Retries once on invalid JSON (observer merge rule 6)."""
    size = sum(len(p.get("data", "")) for p in parts)
    if size > MAX_INLINE_BYTES:
        raise ValueError(f"Inline payload is {size / 1e6:.1f} MB; the limit is {MAX_INLINE_BYTES / 1e6:.0f} MB.")
    gen = {"thinking_level": thinking_level, "max_output_tokens": max_output_tokens}
    if seed is not None:
        gen["seed"] = seed
    total = Result(None, "", "", 0.0, attempts=0)
    for _ in range(2):
        t0 = time.time()
        r = client().interactions.create(
            model=MODEL,
            store=False,
            system_instruction=system,
            input=parts,  # a flat list of content parts is one user turn
            response_format={"type": "text", "mime_type": "application/json", "schema": schema},
            generation_config=gen,
            timeout=timeout_s,
        )
        total.seconds += time.time() - t0
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
