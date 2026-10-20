# /// script
# requires-python = ">=3.11"
# dependencies = ["imageio-ffmpeg==0.6.0"]
# ///
# The website's copies of the film, made from the renders behind deck/.
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

# site/, the repo root, the masters, and where each copy goes.
SITE = Path(__file__).resolve().parent.parent
ROOT = SITE.parent
DECK = ROOT / "deck"
MEDIA = ROOT / "out" / "media"
POSTERS = SITE / "public" / "film"
# The captions, and the copies' names, bundled with the player.
CAPTIONS = SITE / "src" / "content" / "captions.vtt"
MANIFEST = SITE / "src" / "content" / "media.json"
VOICE = SITE / "ad" / "voice"
FF = imageio_ffmpeg.get_ffmpeg_exe()
# Each shape's name ending, size, H.264 level and lite size.
SHAPES = {
    "wide": ("", (1920, 1080), "4.2", "1280:720"),
    "tall": ("_vertical", (1080, 1920), "4.2", "720:1280"),
    "side": ("_sideways", (2340, 1080), "5.1", "1560:720"),
}
# The masters' x264 tuning: AQ for dark scenes, BT.709 TV range.
X264 = "aq-mode=3:aq-strength=0.9:colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv"


# Runs ffmpeg quietly, stopping on any failure.
def ff(*args):
    subprocess.run([FF, "-y", "-loglevel", "error", *map(str, args)], check=True)


# Seconds as a WebVTT time, such as 00:01:02.345.
def stamp(t):
    m, s = divmod(max(0.0, t), 60)
    return f"00:{int(m):02d}:{s:06.3f}"


# Each sentence's film time, from the voice cues and the word timings.
def captions():
    cues = json.loads((ROOT / "out" / "ad" / "cues.json").read_text())["voice"]
    words = json.loads((VOICE / "words.json").read_text())
    script = json.loads((VOICE / "lines.json").read_text())
    text = json.loads((VOICE / "captions.json").read_text())
    out = []
    for key, lines in text.items():
        # Each spoken sentence takes as many timed words as the script has.
        said, spans = words[key], []
        for sentence in script[key]:
            n = len(re.findall(r"[\w']+", sentence))
            spans.append(said[:n])
            said = said[n:]
        if said or len(spans) != len(lines) or not all(spans):
            sys.exit(f"web.py: {key} in captions.json does not match lines.json and words.json")
        # Placed by the voice cue whose part of the file holds the sentence.
        for span, line in zip(spans, lines):
            start, end = span[0][1], span[-1][2]
            part = next(
                c for c in cues if c["key"] == key and c.get("from", -1e9) <= start < c.get("to", 1e9)
            )
            shift = part["at"] - part.get("from", 0)
            out.append([start + shift - 0.05, end + shift + 0.35, line])
    out.sort()
    # Each caption stops before the next begins.
    for a, b in zip(out, out[1:]):
        a[1] = min(a[1], b[0] - 0.05)
    return "WEBVTT\n\n" + "\n\n".join(f"{stamp(s)} --> {stamp(e)}\n{line}" for s, e, line in out) + "\n"


# Fingerprints a file into its name, so a copy is never mixed or stale.
def stamped(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    final = path.with_name(f"{path.stem}-{digest}{path.suffix}")
    path.replace(final)
    return final.name


# H.264 with a full frame every half second, so a turn finds one fast.
def encode(source, sound, scale, crf, rate, level, out):
    ff(
        *["-i", source, "-i", sound, "-map", "0:v", "-map", "1:a", "-c:a", "copy"],
        *(["-vf", f"scale={scale}:flags=lanczos"] if scale else []),
        *["-c:v", "libx264", "-preset", "slow", "-crf", crf, "-maxrate", rate, "-bufsize", f"{2 * int(rate[:-1])}M"],
        *["-x264-params", f"{X264}:keyint=30:min-keyint=30"],
        *["-profile:v", "high", "-level", level, "-pix_fmt", "yuv420p"],
        *["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"],
        *["-movflags", "+faststart", "-shortest", out],
    )
    return stamped(out)


# Old copies and posters go, since every name now carries its print.
MEDIA.mkdir(parents=True, exist_ok=True)
POSTERS.mkdir(parents=True, exist_ok=True)
for old in [*MEDIA.glob("film-*.mp4"), *POSTERS.glob("poster-*.jpg")]:
    old.unlink()
files = {}
for shape, (suffix, size, level, lite) in SHAPES.items():
    master = DECK / f"QUARCC_Purple_FIAM_trailer{suffix}.mp4"
    # The near lossless render the master came from, at full size.
    source = ROOT / "out" / "ad" / f"master{suffix}.mp4"
    if not master.is_file() or not source.is_file():
        sys.exit(f"web.py: {shape} needs {master.name} and {source.name}; pnpm media video makes them")
    probe = subprocess.run([FF, "-hide_banner", "-i", source], capture_output=True, text=True).stderr
    if f"{size[0]}x{size[1]}" not in probe:
        sys.exit(f"web.py: {source.name} is a preview, not {size[0]}x{size[1]}; render it again")
    # The full copy at the master's quality, and a lite one for slow links.
    files[shape] = encode(source, master, None, "16", "12M", level, MEDIA / f"film-{shape}.mp4")
    files[f"{shape}-lite"] = encode(source, master, lite, "22", "4M", "4.2", MEDIA / f"film-{shape}-lite.mp4")
    # The first frame, the film's first light, shown while it loads.
    ff("-i", master, "-frames:v", "1", "-q:v", "3", POSTERS / f"poster-{shape}.jpg")
    files[f"poster-{shape}"] = stamped(POSTERS / f"poster-{shape}.jpg")
# The names the player asks for, and the captions it shows.
MANIFEST.write_text(json.dumps(files, indent=1) + "\n")
CAPTIONS.write_text(captions())
for f in sorted(p for p in [*MEDIA.iterdir(), *POSTERS.iterdir(), MANIFEST, CAPTIONS] if p.is_file()):
    print(f"  {f.relative_to(ROOT)}  {f.stat().st_size / 1e6:.2f} MB")
