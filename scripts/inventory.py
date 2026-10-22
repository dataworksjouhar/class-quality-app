"""Count-only inventory of the labelled recordings.

Prints folder, duration, size, resolution, audio format and transcript counts.
Never prints file names (they can contain teacher names), transcript text or speaker labels.
Recordings are labelled <folder>-<n> in sorted order of their file names.

Usage: python scripts/inventory.py [RECORDINGS_DIR]   (default: RECORDINGS_DIR from .env)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from cqa import media, vtt  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def fmt_dur(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def pair_transcripts(videos: list[tuple[Path, float | None]], vtts: list[Path]) -> dict[Path, tuple[Path, list]]:
    """File stems differ, so pair each video with the VTT whose last cue ends closest to its duration."""
    parsed = [(p, vtt.parse(p)) for p in vtts]
    pairs, used = {}, set()
    for v, dur in sorted(videos, key=lambda t: -(t[1] or 0)):
        best = None
        for i, (p, cues) in enumerate(parsed):
            if i in used or not cues:
                continue
            gap = abs(cues[-1].end - (dur or 0))
            if best is None or gap < best[0]:
                best = (gap, i)
        if best:
            used.add(best[1])
            pairs[v] = parsed[best[1]]
    return pairs


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ["RECORDINGS_DIR"])
    rows, total_s = [], 0.0
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT)
        vtts = sorted(folder.glob("*.vtt"))
        probes = {v: media.probe(v) for v in videos}
        pairs = pair_transcripts([(v, probes[v].duration_s) for v in videos], vtts)
        for n, v in enumerate(videos, 1):
            pr = probes[v]
            total_s += pr.duration_s or 0
            cues = pairs.get(v, (None, []))[1]
            c = vtt.counts(cues) if cues else {"cues": 0, "speakers": 0, "unlabelled": 0}
            vtt_end = cues[-1].end if cues else None
            rows.append({
                "recording": f"{folder.name}-{n}",
                "duration": fmt_dur(pr.duration_s),
                "size_MB": f"{v.stat().st_size / 1e6:.0f}",
                "video": f"{pr.width}x{pr.height}" if pr.width else "none",
                "audio": f"{pr.audio_codec} {pr.audio_rate // 1000 if pr.audio_rate else '?'}k {pr.audio_layout} "
                         f"{pr.audio_kbps or '?'}kb/s",
                "cues": str(c["cues"]),
                "speakers": str(c["speakers"]),
                "no_label": str(c["unlabelled"]),
                "vtt_end_gap_s": f"{vtt_end - pr.duration_s:+.0f}" if vtt_end and pr.duration_s else "-",
            })
    cols = list(rows[0])
    widths = {k: max(len(k), *(len(r[k]) for r in rows)) for k in cols}
    print("  ".join(k.ljust(widths[k]) for k in cols))
    print("  ".join("-" * widths[k] for k in cols))
    for r in rows:
        print("  ".join(r[k].ljust(widths[k]) for k in cols))
    total_h = total_s / 3600
    print(f"\n{len(rows)} recordings, {total_h:.1f} h total. vtt_end_gap_s = last cue end minus video duration.")


if __name__ == "__main__":
    main()
