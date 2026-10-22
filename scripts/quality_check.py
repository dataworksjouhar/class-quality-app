"""E5: run the recording-quality check on every labelled recording. Prints numbers only.

Usage: python scripts/quality_check.py [RECORDINGS_DIR] [folder ...]
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from cqa import media, quality  # noqa: E402
from inventory import VIDEO_EXT  # noqa: E402


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    args = sys.argv[1:]
    root = Path(args.pop(0) if args and Path(args[0]).is_dir() else os.environ["RECORDINGS_DIR"])
    only = set(args)
    print(f"{'recording':16} {'min':>5} {'LUFS':>6} {'clip_s':>6} {'clipMax/min':>11} {'gaps/h':>6} "
          f"{'absent_min':>10} {'status':>6} {'secs':>5}  issues")
    with tempfile.TemporaryDirectory() as tmp:
        for folder in sorted(p for p in root.iterdir() if p.is_dir() and (not only or p.name in only)):
            videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT)
            for n, v in enumerate(videos, 1):
                t = time.time()
                _, scan = media.prepare(v, Path(tmp) / "a.m4a")
                rep = quality.assess(scan)
                m = rep.metrics
                issues = ",".join(f.check for f in rep.findings if f.is_issue) or "-"
                lufs = "-" if m["integrated_lufs"] is None else f"{m['integrated_lufs']:.1f}"
                print(f"{folder.name + '-' + str(n):16} {m['duration_min']:5.1f} {lufs:>6} {m['clipped_seconds']:6d} "
                      f"{m['max_clipped_seconds_in_a_minute']:11d} {m['silent_gaps_per_hour']:6.1f} "
                      f"{m['absent_audio_min']:10.1f} {'OK' if rep.ok else 'ISSUES':>6} {time.time() - t:5.0f}  {issues}",
                      flush=True)


if __name__ == "__main__":
    main()
