"""ffmpeg helpers: locate the binary, probe a file, and the single prepare pass.

The prepare pass decodes the source once and produces three things:
  1. the mono 16 kHz ~32 kbps audio file for the Observer,
  2. EBU R128 loudness (integrated LUFS, loudness range, true peak) from ffmpeg,
  3. raw PCM on stdout, reduced in numpy to 10 ms energy frames and per-second
     clipping counts, which quality.py turns into findings.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import config


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise RuntimeError("ffmpeg not found. Install it or `pip install imageio-ffmpeg`.") from e


@dataclass
class Probe:
    duration_s: float | None
    width: int | None
    height: int | None
    audio_codec: str | None
    audio_rate: int | None
    audio_channels: int | None
    audio_layout: str | None
    audio_kbps: int | None

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_VID_RE = re.compile(r"Stream #\d+:\d+.*?: Video: .*?(\d{2,5})x(\d{2,5})[\s,\[]")
_AUD_RE = re.compile(r"Stream #\d+:\d+.*?: Audio: (\w+)[^,]*, (\d+) Hz, ([^,]+)(?:, [^,]+)?(?:, (\d+) kb/s)?")
_LAYOUT_CH = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "5.0": 5, "5.1": 6, "7.1": 8}


def probe(path: Path) -> Probe:
    """Parse `ffmpeg -i` output (no ffprobe needed; the pip ffmpeg ships without it)."""
    r = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    err = r.stderr
    dur = w = h = codec = rate = ch = kbps = layout = None
    if m := _DUR_RE.search(err):
        dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    if m := _VID_RE.search(err):
        w, h = int(m[1]), int(m[2])
    if m := _AUD_RE.search(err):
        codec, rate, layout = m[1], int(m[2]), m[3].strip()
        kbps = int(m[4]) if m[4] else None
        ch = _LAYOUT_CH.get(layout.split("(")[0])
        if ch is None and (cm := re.match(r"(\d+) channels", layout)):
            ch = int(cm[1])
    return Probe(dur, w, h, codec, rate, ch, layout, kbps)


@dataclass
class AudioScan:
    """Raw measurements. quality.py interprets them."""
    duration_s: float
    lufs: float | None
    lra: float | None
    true_peak_db: float | None
    frame_s: float  # length of one energy frame (0.01 s)
    frame_ms: np.ndarray  # mean square of the mono mix per 10 ms frame
    sec_clipped: np.ndarray  # clipped samples (any channel) per second
    sec_peak: np.ndarray  # max |sample| per second
    sec_ch_ms: np.ndarray  # mean square per second per channel, shape (seconds, channels)


_LUFS_RE = re.compile(r"Integrated loudness:\s*I:\s*(-?[\d.]+|-inf) LUFS", re.S)
_LRA_RE = re.compile(r"Loudness range:\s*LRA:\s*(-?[\d.]+) LU", re.S)
_TP_RE = re.compile(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf) dBFS", re.S)


def _num(m: re.Match | None) -> float | None:
    if not m or m[1] == "-inf":
        return None
    return float(m[1])


def prepare(src: Path, audio_out: Path, progress: Callable[[float], None] | None = None) -> tuple[Probe, AudioScan]:
    """One decode: write the Observer audio file and measure the recording."""
    info = probe(src)
    if not info.has_audio:
        raise ValueError("The file has no audio track.")
    rate = info.audio_rate or 48000
    ch = info.audio_channels or 2
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-nostats", "-loglevel", "info", "-y", "-i", str(src),
        # 1) Observer audio
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(config.AUDIO_RATE),
        "-c:a", "aac", "-b:a", config.AUDIO_BITRATE, str(audio_out),
        # 2) loudness summary on stderr (per-frame log kept below the log level)
        "-map", "0:a:0", "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-",
        # 3) native-rate PCM for clipping, silence and dropouts
        "-map", "0:a:0", "-ac", str(ch), "-ar", str(rate), "-f", "f32le", "-c:a", "pcm_f32le", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err_chunks: list[bytes] = []
    t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t.start()

    frame_len = rate // 100  # 10 ms
    block_s = 10
    block_bytes = rate * ch * 4 * block_s
    frames, clipped, peaks, ch_ms = [], [], [], []
    done = 0.0
    while True:
        buf = proc.stdout.read(block_bytes)  # blocks until full or EOF
        if not buf:
            break
        x = np.frombuffer(buf[: len(buf) - len(buf) % (4 * ch)], dtype="<f4").reshape(-1, ch)
        # pad the last partial second with zeros so every second has `rate` samples
        secs = -(-len(x) // rate)
        if len(x) < secs * rate:
            x = np.vstack([x, np.zeros((secs * rate - len(x), ch), np.float32)])
        a = np.abs(x).reshape(secs, rate * ch)
        clipped.append((a >= config.CLIP_LEVEL).sum(axis=1))
        peaks.append(a.max(axis=1))
        ch_ms.append((x.reshape(secs, rate, ch) ** 2).mean(axis=1))
        mono = x.mean(axis=1)
        frames.append((mono.reshape(-1, frame_len) ** 2).mean(axis=1).astype(np.float32))
        done += len(buf) / (rate * ch * 4)
        if progress and info.duration_s:
            progress(min(done / info.duration_s, 1.0))
    proc.wait()
    t.join()
    err = b"".join(err_chunks).decode("utf-8", "replace")
    if proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-5:])
        raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")

    summary = err[err.rfind("Summary:"):] if "Summary:" in err else err
    scan = AudioScan(
        duration_s=float(info.duration_s or done),
        lufs=_num(_LUFS_RE.search(summary)),
        lra=_num(_LRA_RE.search(summary)),
        true_peak_db=_num(_TP_RE.search(summary)),
        frame_s=0.01,
        frame_ms=np.concatenate(frames) if frames else np.zeros(0, np.float32),
        sec_clipped=np.concatenate(clipped).astype(np.int64) if clipped else np.zeros(0, np.int64),
        sec_peak=np.concatenate(peaks).astype(np.float32) if peaks else np.zeros(0, np.float32),
        sec_ch_ms=np.concatenate(ch_ms).astype(np.float32) if ch_ms else np.zeros((0, ch), np.float32),
    )
    return info, scan
