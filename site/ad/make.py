# /// script
# requires-python = ">=3.11"
# dependencies = ["imageio-ffmpeg==0.6.0"]
# ///
# Builds the ad from scratch: the page, its cues, the score and voice mix at -14 LUFS, the soundtrack
# the live page plays, both renders, the two finished films in deck/, and a review of the result
# (out/ad/review/). About twelve minutes on an M-series Mac; --preview makes quick half-size copies in
# out/ad/ instead.
#
#   uv run site-v2/ad/make.py
#   uv run site-v2/ad/make.py --preview
import os
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

SITE = Path(__file__).resolve().parent.parent
ROOT = SITE.parent
OUT = ROOT / "out" / "ad"
FF = imageio_ffmpeg.get_ffmpeg_exe()
PREVIEW = "--preview" in sys.argv


def run(*cmd, env=None):
    subprocess.run([str(c) for c in cmd], cwd=SITE, check=True, env=env)


def loudness(path):
    report = subprocess.run(
        [FF, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    summary = report[report.rindex("Summary:") :]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary)[1]), float(re.search(r"Peak:\s+(-?[\d.]+)", summary)[1])


OUT.mkdir(parents=True, exist_ok=True)
run("pnpm", "film")
run("node", "ad/record.mjs", "cues", OUT / "cues.json")
run("uv", "run", "ad/score.py", OUT / "cues.json", "ad/voice", OUT)
level, _ = loudness(OUT / "mix.wav")
limiter = "aresample=192000,alimiter=limit=0.84:attack=2:release=80:level=disabled,aresample=48000"
run(FF, "-y", "-loglevel", "error", "-i", OUT / "mix.wav", "-af", f"volume={-14 - level:.2f}dB,{limiter}", OUT / "audio.wav")
level, peak = loudness(OUT / "audio.wav")
print(f"audio: {level} LUFS, true peak {peak} dBFS")
run(FF, "-y", "-loglevel", "error", "-i", OUT / "audio.wav", "-c:a", "aac", "-b:a", "192k", ROOT / "out" / "film" / "film.m4a")
run("node", "ad/record.mjs", "camera", 60, OUT / "camera.json")

env = {**os.environ, "FFMPEG": FF}
for suffix, size in (("", (1920, 1080)), ("_vertical", (1080, 1920))):
    w, h = (v // 2 for v in size) if PREVIEW else size
    master = OUT / f"master{suffix}.mp4"
    run("node", "ad/record.mjs", "video", f"{w}x{h}", 30 if PREVIEW else 60, 1 if PREVIEW else 16, master, env=env)
    name = f"QUARCC_Purple_FIAM_trailer{suffix}"
    final = OUT / f"{name}_preview.mp4" if PREVIEW else ROOT / "deck" / f"{name}.mp4"
    x264 = "aq-mode=3:aq-strength=0.9:colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv"
    run(
        *[FF, "-y", "-loglevel", "error", "-i", master, "-i", OUT / "audio.wav", "-map", "0:v", "-map", "1:a"],
        *["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "10M", "-bufsize", "20M"],
        *["-x264-params", x264, "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p"],
        *["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"],
        *["-g", "120", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"],
        *["-metadata", "title=QUARCC Purple · Calm, by design", "-shortest", final],
    )
    print(f"wrote {final}, {final.stat().st_size / 1e6:.1f} MB")
    if not suffix:
        wide = final
run("uv", "run", "ad/review.py", wide)
