"""Class Quality Assessor: Streamlit front end.

Drive link or upload -> pipeline (cqa/pipeline.py) -> report. Nothing is kept after the report is built.
"""
import json
import shutil
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from cqa import devlocal, intake, pipeline, quality

load_dotenv()
st.set_page_config(page_title="Class Quality Assessor", page_icon="♟️", layout="centered")

LABEL_COLOURS = {"Excellent": "green", "Good": "blue", "Average": "orange", "Poor": "red"}
CONF_COLOURS = {"High": "green", "Medium": "orange", "Low": "red"}

st.title("Class Quality Assessor")
st.caption(
    "Grades a recorded online class and points a reviewer to the minutes worth watching. "
    "The video is deleted as soon as the audio and stills are extracted; nothing is kept after the report."
)

# ------------------------------------------------------------------ inputs
tabs = ["Google Drive link", "Upload a file"] + (["Local (dev)"] if devlocal.enabled() else [])
tab_objs = st.tabs(tabs)
with tab_objs[0]:
    link = st.text_input("Drive link to the recording", placeholder="https://drive.google.com/file/d/…/view",
                         help="Share the file with 'Anyone with the link' (Viewer). Up to 1 GB.")
with tab_objs[1]:
    upload = st.file_uploader("Recording (small files only; use a Drive link for full classes)",
                              type=["mp4", "mov", "mkv", "webm", "m4a", "mp3", "wav"])
dev_code = ""
if devlocal.enabled():
    with tab_objs[2]:
        dev_code = st.text_input("Batch code of a local labelled recording", placeholder="B558")
transcript = st.file_uploader("Zoom transcript (.vtt), optional. Used only to catch names before anything is shown.",
                              type=["vtt"])
go = st.button("Analyse", type="primary", disabled=not (link or upload or dev_code))


def fmt_bytes(n: int) -> str:
    return f"{n / 1e6:,.0f} MB"


def run() -> dict:
    job = intake.new_job_dir()
    status = st.status("Working…", expanded=True)
    try:
        with status:
            t0 = time.time()
            vtt_text = transcript.getvalue().decode("utf-8", "replace") if transcript is not None else None
            if dev_code:
                st.write("Copying the local recording…")
                src, dev_vtt = devlocal.fetch(dev_code, job)
                vtt_text = vtt_text or dev_vtt
            elif upload is not None:
                st.write("Saving the upload…")
                src = intake.save_upload(upload, job)
            else:
                st.write("Downloading from Google Drive…")
                bar = st.progress(0.0)

                def dl(got: int, total: int | None) -> None:
                    bar.progress(min(got / total, 1.0) if total else 0.0,
                                 text=f"{fmt_bytes(got)}" + (f" of {fmt_bytes(total)}" if total else " downloaded"))

                src = intake.download_drive(link, job, dl)
            st.write(f"Got {fmt_bytes(src.stat().st_size)} in {time.time() - t0:.0f} s.")

            bars = {step: st.progress(0.0, text=text) for step, text in
                    (("prepare", "Audio and stills"), ("observe", "Observer"), ("judge", "Judge"))}

            def progress(step: str, frac: float, msg: str) -> None:
                bars[step].progress(min(max(frac, 0.0), 1.0), text=msg)

            report = pipeline.run(src, job, vtt_text, progress)
            status.update(label=f"Done in {report['run']['timings_s']['total_s'] // 60:.0f} min "
                                f"{report['run']['timings_s']['total_s'] % 60:.0f} s", state="complete", expanded=False)
        return report
    except Exception:
        status.update(label="Stopped", state="error", expanded=True)
        raise
    finally:
        shutil.rmtree(job, ignore_errors=True)


def export(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "quality"} | {"recording_quality": r["quality"].metrics}


if go:
    try:
        st.session_state["report"] = run()
        if devlocal.enabled():  # dev only: keep the (leak-tested, name-free) report so a reload cannot lose it
            out = devlocal.report_dir() / f"{(dev_code or 'run').strip()}_{time.strftime('%Y%m%d-%H%M%S')}.json"
            out.write_text(json.dumps(export(st.session_state["report"]), indent=1, default=str), encoding="utf-8")
    except (intake.IntakeError, pipeline.PrivacyCheckFailed, FileNotFoundError) as e:
        st.session_state.pop("report", None)
        st.error(str(e))
    except (ValueError, RuntimeError) as e:
        st.session_state.pop("report", None)
        st.error(f"Could not process this recording. {e}")


# ------------------------------------------------------------------ report
def quality_panel(rep: quality.QualityReport) -> None:
    m = rep.metrics
    st.subheader(f"Recording quality: {'OK' if rep.ok else 'Issues'}")
    st.caption("Measured from the audio only (no AI). Reported separately from teaching quality.")
    c = st.columns(4)
    c[0].metric("Length", f"{m['duration_min']:.0f} min")
    c[1].metric("Loudness", "-" if m["integrated_lufs"] is None else f"{m['integrated_lufs']:.1f} LUFS")
    c[2].metric("Clipped", f"{m['clipped_seconds']} s")
    c[3].metric("Silent gaps", f"{m['silent_gaps_per_hour']:.0f} / hour")
    for f in rep.findings:
        spans = ", ".join(f"{quality.ts(s)} ({int(e - s)} s)" for s, e in f.spans)
        st.markdown(f"{'⚠️' if f.is_issue else '✅'} **{f.check.capitalize()}**: {f.message}"
                    + (f"  \n  At: {spans}" if spans else ""))
    chart = pd.DataFrame({"level (dBFS)": rep.minute_db}, index=pd.Index(range(len(rep.minute_db)), name="minute"))
    st.line_chart(chart, height=160)


def cite_md(c: dict) -> str:
    if c["kind"] == "event":
        return f"`{c['at']}` {c['detail']} _({c['type'].replace('_', ' ')}, {c['id']})_"
    return f"metric `{c['id']}` = {json.dumps(c['value'], default=str)}"


def report_view(r: dict) -> None:
    st.divider()
    c1, c2 = st.columns([3, 2])
    c1.markdown(f"## :{LABEL_COLOURS[r['label']]}[{r['label']}]")
    c1.caption(f"Weighted mean M = {r['M']:.2f} · rule: {r['rule']}")
    c2.markdown(f"**Confidence:** :{CONF_COLOURS[r['confidence']]}[{r['confidence']}]")
    if r["confidence_reasons"]:
        c2.caption("; ".join(r["confidence_reasons"]))
    if r["needs_human_review"]:
        st.warning("Needs human review: the inputs are too weak for a confident grade.")
    st.markdown(f"**{r['summary']}**")

    st.markdown("#### Watch these minutes first")
    for w in r["watch"]:
        st.markdown(f"- **{w['at']}**: {w['reason']}")

    st.markdown("#### Scores")
    table = pd.DataFrame([{"Area": f"{a['area']}. {a['name']}", "Score": f"{a['score']} / 4", "Weight": a["weight"],
                           "Evidence": "low" if a["low_evidence"] else "ok"} for a in r["areas"]])
    st.dataframe(table, hide_index=True, width="stretch")
    for a in r["areas"]:
        with st.expander(f"{a['area']}. {a['name']}: {a['score']}/4" + (" · low evidence" if a["low_evidence"] else "")):
            st.write(a["rationale"])
            if a["not_applicable"]:
                st.caption("Not applicable: " + ", ".join(a["not_applicable"]))
            if a["area"] == "F":
                d = a["f_detail"]
                bad = d["bad_teacher_audio_minutes"]
                st.markdown(
                    f"- Frames with the teacher's tile visible: **{d['visible_frames']}** "
                    f"({d['frames_with_tile_hidden']} hidden by a board share count as no data)\n"
                    f"- 8x8 background: {d['8x8_background']} · camera off: {d['camera_off']} · "
                    f"face not visible: {d['face_not_visible']} · dim: {d['dim']} · artefacts: {d['artefacts']}\n"
                    f"- Bad teacher-audio minutes: {len(bad)}" + (f" (minutes {', '.join(map(str, bad))})" if bad else ""))
            for label, key in (("For a higher score", "evidence_for"), ("Against", "evidence_against")):
                if a[key]:
                    st.markdown(f"**{label}**")
                    st.markdown("\n".join(f"- {cite_md(c)}" for c in a[key]))

    c3, c4 = st.columns(2)
    for col, title, key in ((c3, "Strengths", "strengths"), (c4, "Improvements", "improvements")):
        col.markdown(f"#### {title}")
        for s_ in r[key]:
            col.markdown(f"- `{s_['at']}` {s_['text']}")

    st.divider()
    quality_panel(r["quality"])

    with st.expander("How this was measured"):
        run_ = r["run"]
        st.write(f"{run_['chunks']} Observer chunks ({run_['chunks_failed']} failed), model {run_['model']}, "
                 f"Observer prompt v{run_['observer_prompt']}, Judge prompt v{run_['judge_prompt']}. "
                 f"Cost ${run_['total_cost_usd']:.2f}. Time {run_['timings_s']}. Name leak test: {run_['leak_test']}. "
                 f"Judge citations removed by checks: {run_['judge_checks_removed'] or 'none'}.")
        st.json({"judge_metrics": r["judge_metrics"], "all_metrics": r["metrics"]}, expanded=False)
    st.download_button("Download report (JSON)", json.dumps(export(r), indent=1, default=str), "class_report.json",
                       "application/json")


if st.session_state.get("report"):
    report_view(st.session_state["report"])
