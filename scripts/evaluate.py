"""Full evaluation: run the real pipeline on every labelled recording, N at a time. Prints numbers only.

Usage: python scripts/evaluate.py [--parallel 3] [--only B472 B558 ...]
Each run works on a copy of the video (the pipeline deletes its input). Reports (name-free, leak-tested) go to
data/reports/eval/<code>.json and the table to data/reports/eval/table.md, all gitignored.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

from cqa import media, pipeline  # noqa: E402
from inventory import pair_transcripts  # noqa: E402

OUT = ROOT / "data" / "reports" / "eval"
ORGANISER = {"excellent": "Excellent", "good": "Good", "average": "Average", "weak": "Poor (Weak)",
             "quality issue": "(quality issue)", "demo": "(demo)"}
ORDER = {"Excellent": 0, "Good": 1, "Average": 2, "Poor (Weak)": 3, "(quality issue)": 4, "(demo)": 5}
B435_SUFFIX = {"good": "-Jul", "average": "-Aug"}  # rubric.md: B435 appears twice


def recordings() -> list[dict]:
    root = Path(os.environ["RECORDINGS_DIR"])
    out = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        videos = sorted(folder.glob("*.mp4"))
        pairs = pair_transcripts([(v, media.probe(v).duration_s) for v in videos], sorted(folder.glob("*.vtt")))
        for v in videos:
            m = re.search(r"B\s?-?(\d{3})", v.name, re.I)
            if m:
                code = f"B{m[1]}" + (B435_SUFFIX.get(folder.name, "") if m[1] == "435" else "")
            else:
                code = "ML-demo" if "malayalam" in v.name.lower() else "EN-demo"
            out.append({"code": code, "organiser": ORGANISER.get(folder.name, folder.name), "video": v,
                        "vtt": pairs[v][0] if v in pairs else None, "minutes": (media.probe(v).duration_s or 0) / 60})
    return out


def run_one(rec: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="cqa_eval_") as tmp:
        job = Path(tmp)
        src = job / "source.media"
        shutil.copyfile(rec["video"], src)
        vtt_text = rec["vtt"].read_text(encoding="utf-8", errors="replace") if rec["vtt"] else None
        t0 = time.time()
        report = pipeline.run(src, job, vtt_text)
        report["eval"] = {"code": rec["code"], "organiser": rec["organiser"], "wall_s": round(time.time() - t0)}
    (OUT / f"{rec['code']}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


def row(rec: dict, r: dict | None, err: str | None = None) -> dict:
    if r is None:
        return {"code": rec["code"], "organiser": rec["organiser"], "app": f"FAILED ({err})"}
    s = {a["area"]: a["score"] for a in r["areas"]}
    low = set(r["low_evidence"])
    return {"code": rec["code"], "organiser": rec["organiser"], "app": r["label"], "M": f"{r['M']:.2f}",
            **{a: f"{s[a]}{'*' if a in low else ''}" for a in "ABCDEF"},
            "confidence": r["confidence"], "min": f"{r['recording']['duration_min']:.0f}",
            "time": f"{r['run']['timings_s']['total_s'] // 60}:{r['run']['timings_s']['total_s'] % 60:02d}",
            "cost": f"${r['run']['total_cost_usd']:.2f}"}


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-done", action="store_true", help="skip recordings that already have a report")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    recs = [r for r in recordings() if (not args.only or r["code"] in args.only)
            and not (args.skip_done and (OUT / f"{r['code']}.json").exists())]
    recs.sort(key=lambda r: -r["minutes"])  # longest first, to balance the pool
    rows = {}
    t0 = time.time()
    with ThreadPoolExecutor(args.parallel) as pool:
        futs = {pool.submit(run_one, r): r for r in recs}
        for fut in as_completed(futs):
            rec = futs[fut]
            try:
                rep, err = fut.result(), None
            except Exception as e:  # noqa: BLE001 - one failed recording must not stop the evaluation
                rep, err = None, type(e).__name__
                if isinstance(e, pipeline.PrivacyCheckFailed):
                    print(f"   {rec['code']}: {e}", flush=True)  # says where, never the word
            rows[rec["code"]] = row(rec, rep, err)
            print(f"[{time.time() - t0:5.0f}s] {rec['code']}: {rows[rec['code']].get('app')}", flush=True)
    # the table covers every saved report, including runs from earlier invocations
    for f in OUT.glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["eval"]["code"] not in rows or rows[r["eval"]["code"]]["app"].startswith("FAILED"):
            rows[r["eval"]["code"]] = row(r["eval"], r)
    ordered = sorted(rows.values(), key=lambda x: (ORDER.get(x["organiser"], 9), x["code"]))
    cols = ["code", "organiser", "app", "M", "A", "B", "C", "D", "E", "F", "confidence", "min", "time", "cost"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(x.get(c, "")) for c in cols) + " |" for x in ordered]
    table = "\n".join(lines)
    (OUT / "table.md").write_text(table + "\n\n`*` = low evidence. Time is wall time per recording with "
                                  f"{args.parallel} running at once.\n", encoding="utf-8")
    print("\n" + table)
    print(f"\nTotal wall time {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
