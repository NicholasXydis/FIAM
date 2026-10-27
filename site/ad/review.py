# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "faster-whisper", "numpy", "scipy", "soundfile", "matplotlib", "librosa",
#   "opencv-python-headless",
# ]
# ///
# Checks the finished ad like a viewer: words, pauses, beats, motion.
import json
import re
import sys
from pathlib import Path

import cv2
import librosa
import matplotlib

# Agg draws to PNG files with no window, set before pyplot loads.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

# site/, the repo, out/ad's files and the review/ folder this fills.
SITE = Path(__file__).resolve().parent.parent
ROOT = SITE.parent
AD = ROOT / "out" / "ad"
OUT = AD / "review"
OUT.mkdir(parents=True, exist_ok=True)


# Stops, saying what makes it, when a file this script reads is missing.
def need(path):
    if not path.is_file():
        sys.exit(f"review.py: {path} is missing; pnpm media video makes it")
    return path


# The film, deck/'s 16:9 one by default, with its cues and its script.
video = need(
    Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "deck" / "QUARCC_Purple_FIAM_trailer.mp4"
)
cues = json.loads(need(AD / "cues.json").read_text())
lines = json.loads((SITE / "ad" / "voice" / "lines.json").read_text())
# The report as Markdown lines, saved as review/report.md at the end.
report = ["# Ad review", ""]


# A text's words in lower case, with the spoken Quark read as QUARCC.
def words(text):
    return re.findall(r"[a-z0-9']+", text.lower().replace("quark", "quarcc"))


# The voice over the music: what Whisper hears, against the script.
audio, sr = sf.read(need(AD / "audio.wav"))
mono = audio.mean(axis=1)
# Whisper small.en on the CPU in int8, fed the mix as 16 kHz mono.
model = WhisperModel("small.en", device="cpu", compute_type="int8")
segments, _ = model.transcribe(
    resample_poly(mono, 1, sr // 16000).astype(np.float32), word_timestamps=True, language="en"
)
heard = [w for s in segments for w in s.words]
script = words(" ".join(" ".join(v) for v in lines.values()))
said = words(" ".join(w.word for w in heard))
# Word-level edit distance from script to hearing, for the error rate.
d = np.zeros((len(script) + 1, len(said) + 1), int)
d[:, 0], d[0, :] = range(len(script) + 1), range(len(said) + 1)
for i in range(1, len(script) + 1):
    for j in range(1, len(said) + 1):
        d[i, j] = min(
            d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (script[i - 1] != said[j - 1])
        )
report += [
    "## Voice",
    f"- Word error rate against the script: {d[-1, -1] / len(script):.1%} "
    f"({d[-1, -1]} of {len(script)} words)",
    f"- Heard: {' '.join(w.word.strip() for w in heard)}",
]
# Pauses from words.json: over 0.3 s is a sentence break or a stumble.
timing = json.loads((SITE / "ad" / "voice" / "words.json").read_text())
gaps = [
    f"{key}: {a[0]} / {b[0]} {b[1] - a[2]:.2f}s"
    for key, spoken in timing.items()
    for a, b in zip(spoken, spoken[1:])
    if b[1] - a[2] > 0.3
]
sentences = sum(len(v) - 1 for v in lines.values())
report.append(
    f"- Gaps over 0.3 s between words ({sentences} sentence breaks by design): "
    f"{'; '.join(gaps) or 'none'}"
)

# sound.png: a spectrogram, then the mix and music levels over time.
music, _ = sf.read(need(AD / "music.wav"))
fig, ax = plt.subplots(2, 1, figsize=(16, 7), sharex=True)
ax[0].specgram(mono, NFFT=2048, Fs=sr, noverlap=1536, cmap="magma", vmin=-120)
ax[0].set_ylim(0, 12000)
ax[0].set_ylabel("Hz")
hop = sr // 20


# A signal's level in decibels, one value every twentieth of a second.
def level(x):
    return 20 * np.log10(np.sqrt(np.convolve(x**2, np.ones(hop) / hop, "same")[::hop]) + 1e-6)


# Levels with voice cues in gold; sound cues in cyan on the spectrogram.
time = np.arange(len(mono[::hop])) / 20
ax[1].plot(time, level(mono), label="mix", lw=0.8)
ax[1].plot(time, level(music.mean(axis=1)), label="music under the voice", lw=0.8)
ax[1].set_ylim(-60, 0)
ax[1].set_ylabel("dBFS")
for v in cues["voice"]:
    ax[1].axvline(v["at"], color="gold", lw=0.6)
for s in cues["sounds"]:
    if s["kind"] in ("cut", "music", "whoosh", "crane", "resolve", "sting"):
        ax[0].axvline(s["at"], color="cyan", lw=0.6)
ax[1].legend()
fig.tight_layout()
fig.savefig(OUT / "sound.png", dpi=110)

# Beats: each cut after the music starts should sit on the 120 BPM grid.
start = next(s["at"] for s in cues["sounds"] if s["kind"] == "music")
cuts = [
    s["at"]
    for s in cues["sounds"]
    if s["kind"] in ("cut", "swell", "music", "whoosh", "crane", "resolve", "sting")
]
bars = [c for c in cuts if c >= start]
off = [abs((c - start) / 0.5 - round((c - start) / 0.5)) * 0.5 for c in bars]
# An audible accent is a music onset, by librosa, within 60 ms of it.
onsets = librosa.onset.onset_detect(y=music.mean(axis=1).astype(np.float32), sr=sr, units="time")
heard_at = [min(abs(onsets - c)) for c in bars]
report += [
    "",
    "## Music",
    f"- Cuts on a beat of the 120 BPM grid: {sum(o < 0.01 for o in off)} of {len(bars)}",
    f"- Cuts with an audible accent within 60 ms: {sum(h < 0.06 for h in heard_at)} of {len(bars)}"
    + "".join(f" (missing at {c:.2f}s)" for c, h in zip(bars, heard_at) if h >= 0.06),
]

# The picture: median optical flow per frame, and jumps away from cuts.
cap = cv2.VideoCapture(str(video))
fps = cap.get(cv2.CAP_PROP_FPS)
if not cap.isOpened() or fps <= 0:
    sys.exit(f"review.py: OpenCV cannot read {video}")
flow, prev = [], None
# Farneback flow between 320x180 grey frames, its median per frame.
while True:
    ok, frame = cap.read()
    if not ok:
        break
    gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
    if prev is not None:
        f = cv2.calcOpticalFlowFarneback(prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        flow.append(float(np.median(np.linalg.norm(f, axis=2))))
    prev = gray
# Fewer than two frames leave no motion to measure.
if not flow:
    sys.exit(f"review.py: {video} has no frames to compare")
# A jump: over 0.6 px and 6x the median change, 4+ frames from a cut.
flow = np.array(flow)
jumps = np.abs(np.diff(flow))
cut_frames = {int(c * fps) for c in cuts}
spikes = [
    i
    for i in np.where(jumps > max(0.6, 6 * np.median(jumps)))[0]
    if not any(abs(i - c) < 4 for c in cut_frames)
]
# motion.png, with each jump marked in red.
fig, ax = plt.subplots(figsize=(16, 3))
ax.plot(np.arange(len(flow)) / fps, flow, lw=0.7)
for i in spikes:
    ax.axvline(i / fps, color="red", lw=0.6)
ax.set_ylabel("motion (px per frame)")
fig.tight_layout()
fig.savefig(OUT / "motion.png", dpi=110)
report += [
    "",
    "## Picture",
    f"- Frames: {len(flow) + 1} at {fps:.0f} fps",
    "- Sudden jumps in motion away from cuts: "
    f"{', '.join(f'{i / fps:.2f}s' for i in spikes) or 'none'}",
]

# The camera's path from the recorder: its speed and the jolts in it.
path = AD / "camera.json"
if path.exists():
    pos = np.array(json.loads(path.read_text()))
    # Logged at 60 fps; speed is relative to distance from origin plus 5.
    rate = 60
    speed = np.linalg.norm(np.diff(pos, axis=0), axis=1) * rate
    rel = speed / (np.linalg.norm(pos[1:], axis=1) + 5)
    # A jolt: a change over 0.02 and 8x the median, 4+ frames from a cut.
    jolt = np.abs(np.diff(rel))
    seams = {int(c * rate) for c in cuts}
    hard = [
        i
        for i in np.where(jolt > max(0.02, 8 * np.median(jolt)))[0]
        if not any(abs(i - c) < 4 for c in seams)
    ]
    # camera.png, with each jolt marked in red.
    fig, ax = plt.subplots(figsize=(16, 3))
    ax.plot(np.arange(len(rel)) / rate, rel, lw=0.7)
    ax.set_ylim(0, np.percentile(rel, 98) * 1.5)
    for i in hard:
        ax.axvline(i / rate, color="red", lw=0.6)
    ax.set_ylabel("camera speed, relative")
    fig.tight_layout()
    fig.savefig(OUT / "camera.png", dpi=110)
    report.append(
        f"- Camera jolts away from cuts: {', '.join(f'{i / rate:.2f}s' for i in hard) or 'none'}"
    )

# The report to review/report.md and the terminal.
(OUT / "report.md").write_text("\n".join(report) + "\n")
print("\n".join(report))
