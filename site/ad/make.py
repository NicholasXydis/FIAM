# /// script
# requires-python = ">=3.11"
# dependencies = ["imageio-ffmpeg==0.6.0"]
# ///
# Builds the whole ad, from its page to the films in deck/ and a review.
import os
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

# site/, the repo root above it, and out/ad for the ad's working files.
SITE = Path(__file__).resolve().parent.parent
ROOT = SITE.parent
OUT = ROOT / "out" / "ad"
# ffmpeg from the imageio-ffmpeg wheel, so no system install is needed.
FF = imageio_ffmpeg.get_ffmpeg_exe()
# --preview: half size, 30 fps, 1 subframe, into out/ad, not deck/.
PREVIEW = "--preview" in sys.argv or "--smooth" in sys.argv
# --smooth: a preview at 60 fps with 4 subframes, to judge the motion.
SMOOTH = "--smooth" in sys.argv
# Each film's name ending, size and H.264 level; side is 2.17:1.
SHAPES = {
    "wide": ("", (1920, 1080), "4.2"),
    "tall": ("_vertical", (1080, 1920), "4.2"),
    "side": ("_sideways", (2340, 1080), "5.1"),
}
# --shape NAME renders that one alone, leaving the others as they are.
ONLY = sys.argv[sys.argv.index("--shape") + 1] if "--shape" in sys.argv else None
if ONLY and ONLY not in SHAPES:
    sys.exit(f"make.py: --shape is one of {', '.join(SHAPES)}")


# Runs a command in site/, stopping the whole build on any failure.
def run(*cmd, env=None):
    subprocess.run([str(c) for c in cmd], cwd=SITE, check=True, env=env)


# A file's integrated LUFS and true peak in dBFS, from ffmpeg's ebur128.
def loudness(path):
    if not Path(path).is_file():
        sys.exit(f"make.py: {path} is missing, so its loudness cannot be measured")
    result = subprocess.run(
        [FF, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    # The last Summary block holds the totals; without it ffmpeg failed.
    at = result.stderr.rfind("Summary:")
    summary = result.stderr[at:] if at >= 0 else ""
    level = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+)", summary)
    if result.returncode or not level or not peak:
        sys.exit(f"make.py: ffmpeg could not measure {path}:\n{result.stderr[-800:]}")
    return float(level[1]), float(peak[1])


# The page, its cues, then the score and voice mix from those cues.
OUT.mkdir(parents=True, exist_ok=True)
run("pnpm", "media", "page")
run("node", "ad/record.mjs", "cues", OUT / "cues.json")
run("uv", "run", "ad/score.py", OUT / "cues.json", "ad/voice", OUT)
# Gained to -14 LUFS, then a 4x oversampled limiter caps peaks at 0.84.
level, _ = loudness(OUT / "mix.wav")
limiter = "aresample=192000,alimiter=limit=0.84:attack=2:release=80:level=disabled,aresample=48000"
run(
    FF,
    "-y",
    "-loglevel",
    "error",
    "-i",
    OUT / "mix.wav",
    "-af",
    f"volume={-14 - level:.2f}dB,{limiter}",
    OUT / "audio.wav",
)
# Measured again, to print the final loudness and true peak.
level, peak = loudness(OUT / "audio.wav")
print(f"audio: {level} LUFS, true peak {peak} dBFS")
# film.m4a beside the film's page, for watching it live with sound.
run(
    FF,
    "-y",
    "-loglevel",
    "error",
    "-i",
    OUT / "audio.wav",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    ROOT / "out" / "film" / "film.m4a",
)
# The camera's path at 60 fps, for review.py's jolt check.
run("node", "ad/record.mjs", "camera", 60, OUT / "camera.json")

# record.mjs pipes its frames into this same ffmpeg.
env = {**os.environ, "FFMPEG": FF}
# Each render: a silent master, then muxed with audio.
made = []
for shape, (suffix, size, level) in SHAPES.items():
    if ONLY and shape != ONLY:
        continue
    w, h = (v // 2 for v in size) if PREVIEW else size
    master = OUT / f"master{suffix}.mp4"
    run(
        "node",
        "ad/record.mjs",
        "video",
        f"{w}x{h}",
        30 if PREVIEW and not SMOOTH else 60,
        4 if SMOOTH else 1 if PREVIEW else 16,
        master,
        env=env,
    )
    # The film goes to deck/, a preview to out/ad.
    name = f"QUARCC_Purple_FIAM_trailer{suffix}"
    final = OUT / f"{name}_preview.mp4" if PREVIEW else ROOT / "deck" / f"{name}.mp4"
    # x264 AQ biased to dark scenes, colour tagged BT.709 TV range.
    x264 = "aq-mode=3:aq-strength=0.9:colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv"
    # H.264 High 4.2 at CRF 16, at most 10 Mb/s, 192 kb/s AAC at 48 kHz.
    run(
        *[
            FF,
            "-y",
            "-loglevel",
            "error",
            "-i",
            master,
            "-i",
            OUT / "audio.wav",
            "-map",
            "0:v",
            "-map",
            "1:a",
        ],
        *["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "10M", "-bufsize", "20M"],
        *["-x264-params", x264, "-profile:v", "high", "-level", level, "-pix_fmt", "yuv420p"],
        *[
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_range",
            "tv",
        ],
        *["-g", "120", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"],
        *["-metadata", "title=QUARCC Purple · Calm, by design", "-shortest", final],
    )
    print(f"wrote {final}, {final.stat().st_size / 1e6:.1f} MB")
    made.append(final)
# Reviews the first film made, 16:9 when it is: voice, beats, motion.
run("uv", "run", "ad/review.py", made[0])
