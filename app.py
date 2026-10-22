"""Class Quality Assessor: Streamlit front end.

Skeleton stage: intake → prepare audio (video deleted) → recording-quality panel.
The Observer and Judge passes slot in after "prepare", before the job folder is removed.
"""
import shutil
import time

import pandas as pd
import streamlit as st

from cqa import config, intake, media, quality, vtt

st.set_page_config(page_title="Class Quality Assessor", page_icon="♟️", layout="centered")

st.title("Class Quality Assessor")
st.caption(
    "Grades a recorded online class and points a reviewer to the minutes worth watching. "
    "The video is deleted as soon as the audio is extracted; nothing is kept after the report."
)

# ------------------------------------------------------------------ inputs
src_tab, up_tab = st.tabs(["Google Drive link", "Upload a file"])
with src_tab:
    link = st.text_input(
        "Drive link to the recording",
        placeholder="https://drive.google.com/file/d/…/view",
        help="Share the file with 'Anyone with the link' (Viewer). Up to 1 GB.",
    )
with up_tab:
    upload = st.file_uploader(
        "Recording (small files only; use a Drive link for full classes)",
        type=["mp4", "mov", "mkv", "webm", "m4a", "mp3", "wav"],
    )
transcript = st.file_uploader("Zoom transcript (.vtt), optional", type=["vtt"])
go = st.button("Analyse", type="primary", disabled=not (link or upload))


def fmt_bytes(n: int) -> str:
    return f"{n / 1e6:,.0f} MB"


def run_pipeline() -> dict:
    job = intake.new_job_dir()
    status = st.status("Working…", expanded=True)
    try:
        with status:
            # 1. intake
            t0 = time.time()
            if upload is not None:
                st.write("Saving the upload…")
                src = intake.save_upload(upload, job)
            else:
                st.write("Downloading from Google Drive…")
                bar = st.progress(0.0)

                def dl_progress(got: int, total: int | None) -> None:
                    if total:
                        bar.progress(min(got / total, 1.0), text=f"{fmt_bytes(got)} of {fmt_bytes(total)}")
                    else:
                        bar.progress(0.0, text=f"{fmt_bytes(got)} downloaded")

                src = intake.download_drive(link, job, dl_progress)
            size = src.stat().st_size
            st.write(f"Got {fmt_bytes(size)} in {time.time() - t0:.0f} s.")

            # 2. prepare: one ffmpeg pass → Observer audio + measurements
            st.write("Extracting audio and measuring the recording…")
            bar2 = st.progress(0.0)
            audio = job / f"audio{config.AUDIO_EXT}"
            t1 = time.time()
            info, scan = media.prepare(src, audio, lambda f: bar2.progress(f, text=f"{f:.0%}"))
            st.write(f"Audio ready: {fmt_bytes(audio.stat().st_size)} in {time.time() - t1:.0f} s.")

            # 3. the video is not needed any more
            src.unlink(missing_ok=True)
            st.write("Video deleted.")

            # 4. recording quality (no AI)
            report = quality.assess(scan)

            tx = None
            if transcript is not None:
                tx = vtt.counts(vtt.parse_text(transcript.getvalue().decode("utf-8", "replace")))

            status.update(label="Done", state="complete", expanded=False)
        return {"info": info, "report": report, "size": size, "transcript": tx}
    except Exception:
        status.update(label="Stopped", state="error", expanded=True)
        raise
    finally:
        # Skeleton: no AI step yet, so the audio goes too.
        shutil.rmtree(job, ignore_errors=True)


if go:
    try:
        st.session_state["result"] = run_pipeline()
    except intake.IntakeError as e:
        st.session_state.pop("result", None)
        st.error(str(e))
    except (ValueError, RuntimeError) as e:
        st.session_state.pop("result", None)
        st.error(f"Could not process this file. {e}")

# ------------------------------------------------------------------ report
res = st.session_state.get("result")
if res:
    info: media.Probe = res["info"]
    rep: quality.QualityReport = res["report"]
    m = rep.metrics

    st.divider()
    st.subheader(f"Recording quality: {'OK' if rep.ok else 'Issues'}")
    st.caption("Measured from the audio only (no AI). Reported separately from teaching quality.")
    c = st.columns(4)
    c[0].metric("Length", f"{m['duration_min']:.0f} min")
    c[1].metric("Loudness", "-" if m["integrated_lufs"] is None else f"{m['integrated_lufs']:.1f} LUFS")
    c[2].metric("Clipped", f"{m['clipped_seconds']} s")
    c[3].metric("Silent gaps", f"{m['silent_gaps_per_hour']:.0f} / hour")

    for f in rep.findings:
        icon = "⚠️" if f.is_issue else "✅"
        spans = ", ".join(f"{quality.ts(s)} ({int(e - s)} s)" for s, e in f.spans)
        st.markdown(f"{icon} **{f.check.capitalize()}**: {f.message}" + (f"  \n  At: {spans}" if spans else ""))

    chart = pd.DataFrame(
        {"level (dBFS)": rep.minute_db, "clipped seconds": rep.minute_clipped},
        index=pd.Index(range(len(rep.minute_db)), name="minute"),
    )
    st.line_chart(chart[["level (dBFS)"]], height=180)
    if rep.minute_clipped.any():
        st.bar_chart(chart[["clipped seconds"]], height=140)

    with st.expander("Technical details"):
        st.write({
            "file size": fmt_bytes(res["size"]),
            "video": f"{info.width}x{info.height}" if info.width else "none",
            "audio": f"{info.audio_codec}, {info.audio_rate} Hz, {info.audio_layout}",
            **m,
        })
        if res["transcript"]:
            st.write({"transcript": res["transcript"]})
