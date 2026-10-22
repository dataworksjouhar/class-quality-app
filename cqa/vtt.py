"""Zoom VTT reading. Callers in exploration scripts must only print counts."""
import re
from dataclasses import dataclass
from pathlib import Path

TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})\.(\d{3})")
SPEAKER_RE = re.compile(r"^([^:]{1,60}):\s")


@dataclass
class Cue:
    start: float
    end: float
    speaker: str | None
    text: str


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(path: Path) -> list[Cue]:
    return parse_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def parse_text(raw: str) -> list[Cue]:
    cues: list[Cue] = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        m = TIME_RE.search(lines[i])
        if not m:
            i += 1
            continue
        start, end = _secs(*m.groups()[:4]), _secs(*m.groups()[4:])
        i += 1
        body = []
        while i < len(lines) and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        text = " ".join(body)
        sm = SPEAKER_RE.match(text)
        # Zoom puts "Name: text" on the cue; a long prefix is more likely a colon in speech.
        if sm and len(sm.group(1).split()) <= 5:
            cues.append(Cue(start, end, sm.group(1).strip(), text[sm.end():]))
        else:
            cues.append(Cue(start, end, None, text))
    return cues


def counts(cues: list[Cue]) -> dict:
    speakers = {c.speaker for c in cues if c.speaker}
    return {
        "cues": len(cues),
        "speakers": len(speakers),
        "unlabelled": sum(1 for c in cues if not c.speaker),
    }
