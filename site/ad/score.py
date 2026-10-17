# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "soundfile"]
# ///
# The ad's original score and voice mix, made from the film's own cues and played on real recorded
# instruments: string sections, an upright piano, harp, glockenspiel and timpani from VSCO 2
# Community Edition (CC0, Versilian Studios; the piano sampled by Simon Dalzell of Ivy Audio). The
# samples download once into cache/vsco2. Writes mix.wav and music.wav (48 kHz stereo) to the out
# folder.
#
#   uv run site-v2/ad/score.py cues.json voice/ out/
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

SR = 48000
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache" / "vsco2"
REPO = "https://raw.githubusercontent.com/sgossner/VSCO-2-CE/master/"
cues = json.load(open(sys.argv[1]))
VOICE = Path(sys.argv[2])
OUT = Path(sys.argv[3])
LENGTH = float(cues["length"])
N = int(SR * LENGTH)
t = np.arange(N) / SR
rng = np.random.default_rng(3)
sounds = cues["sounds"]
first = {}
for s in sounds:
    first.setdefault(s["kind"], s["at"])
BEAT = 0.5
MUSIC = first["music"]
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def hz(name):
    m = re.fullmatch(r"([A-G]#?)(-?\d)", name)
    return 440 * 2 ** ((NOTES[m[1]] + 12 * (int(m[2]) + 1) - 69) / 12)


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, kind, fs=SR, output="sos"), x, axis=0)


def clock(seconds):
    return np.arange(int(seconds * SR)) / SR


def stereo(x):
    return np.repeat(x[:, None], 2, axis=1)


def fetch(paths):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    for p in paths:
        local = CACHE / p.replace("/", "__")
        if not local.exists():
            urllib.request.urlretrieve(REPO + urllib.parse.quote(p), local)
        out.append(local)
    return out


def library():
    local = CACHE / "tree.json"
    if not local.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        api = "https://api.github.com/repos/sgossner/VSCO-2-CE/git/trees/master?recursive=1"
        urllib.request.urlretrieve(api, local)
    return [e["path"] for e in json.loads(local.read_text())["tree"] if e["path"].endswith(".wav")]


def pick(pattern):
    return sorted(p for p in PATHS if re.search(pattern, p))


def load(path):
    x, rate = sf.read(path, always_2d=True)
    x = x[:, :2] if x.shape[1] > 1 else np.repeat(x, 2, axis=1)
    if rate != SR:
        x = resample_poly(x, SR // 100, rate // 100, axis=0)
    return x / (np.max(np.abs(x)) + 1e-9)


# The pitch a sample actually sounds, from its autocorrelation, so a library's octave naming never
# matters: the named note is moved by octaves to the nearest measured pitch.
def pitch(x, named):
    seg = x[int(0.3 * SR) : int(0.9 * SR), 0]
    if len(seg) < SR // 4:
        return named
    seg = seg - seg.mean()
    ac = np.correlate(seg, seg, "full")[len(seg) - 1 :]
    lo, hi = int(SR / 2000), int(SR / 30)
    measured = SR / (lo + int(np.argmax(ac[lo:hi])))
    return min((named * 2.0**k for k in range(-3, 4)), key=lambda f: abs(np.log2(f / measured)))


# One sampled instrument: picks the recording nearest each note, retunes it, stretches it with a
# crossfaded loop if the note outlasts it, and shapes it with an attack and a release.
class Sampled:
    def __init__(self, files, named, attack=0.02, release=0.6, loop=False, gain=1.0):
        self.samples = [(pitch(x, f), x) for x, f in ((load(p), f) for p, f in zip(files, named))]
        self.attack, self.release, self.loop, self.gain = attack, release, loop, gain

    def __call__(self, freq, length, vel=1.0, attack=None, release=None):
        f0, x = min(self.samples, key=lambda s: abs(np.log2(freq / s[0])))
        ratio = freq / f0
        n = int(length * SR)
        need = int(n * ratio) + 2
        if need > len(x) and self.loop:
            a, b, fade = int(len(x) * 0.3), int(len(x) * 0.8), int(0.15 * SR)
            body = x[a:b]
            ramp = np.linspace(0, 1, fade)[:, None]
            parts = [x[:b].copy()]
            while sum(len(p) for p in parts) < need:
                parts[-1][-fade:] = parts[-1][-fade:] * (1 - ramp) + body[:fade] * ramp
                parts.append(body[fade:].copy())
            x = np.concatenate(parts)
        idx = np.arange(n) * ratio
        idx = idx[idx < len(x) - 1]
        i = idx.astype(int)
        k = (idx - i)[:, None]
        y = x[i] * (1 - k) + x[i + 1] * k
        a = self.attack if attack is None else attack
        r = self.release if release is None else release
        m = len(y)
        env = np.minimum(1, np.arange(m) / max(1, a * SR)) * np.clip((m - np.arange(m)) / max(1, r * SR), 0, 1)
        return np.vstack([y * env[:, None] * vel * self.gain, np.zeros((n - m, 2))])


def named(pattern):
    files = pick(pattern)
    return fetch(files), [hz(re.search(r"_([A-G]#?\d)[_.]", Path(p).name)[1]) for p in files]


PATHS = library()
violins = Sampled(*named(r"Violin Section/susVib/VlnEns_susVib_[A-G]#?\d_v1\.wav$"), attack=0.35, release=1.2, loop=True, gain=0.5)
violas = Sampled(*named(r"Viola Section/susvib/[^/]*_[A-G]#?\d_v1(_1)?\.wav$"), attack=0.4, release=1.2, loop=True, gain=0.45)
celli = Sampled(*named(r"Cello Section/susvib/susvib_[A-G]#?\d_v1_1\.wav$"), attack=0.45, release=1.4, loop=True, gain=0.55)
harp = Sampled(*named(r"Strings/Harp/KSHarp_[A-G]#?\d_mf\.wav$"), attack=0.003, release=1.5, gain=0.5)
glock = Sampled(*named(r"Percussion/Glock/glock_medium_[A-G]#?\d\.wav$"), attack=0.002, release=2.0, gain=0.35)
keys = pick(r"Upright Piano/Player_dyn2_rr1_0\d\d\.wav$")
piano = Sampled(fetch(keys), [440 * 2 ** ((21 + 2 * int(p[-7:-4]) - 69) / 12) for p in keys], 0.003, 1.2, gain=0.6)
timp_hit = load(fetch(pick(r"Percussion/Timpani/Timpani\d_Hit")[:1])[0])
timp_roll = load(fetch(pick(r"Timpani/Rolls/Timpani1_Roll_v5"))[0])
gong = load(fetch(["Percussion/gongHit_mf.wav"])[0])
swell = load(fetch(["Percussion/susCymb1-cresc-Long_v1.wav"])[0])
drum = load(fetch(["Percussion/bassdrum_rub2_v1.wav"])[0])

bus = {k: np.zeros((N, 2)) for k in ("strings", "piano", "harp", "glock", "perc", "fx")}


def put(name, at, x, gain=1.0, pan=0.0):
    a = int(round(at * SR))
    if a >= N or len(x) == 0:
        return
    if a < 0:
        x, a = x[-a:], 0
    n = min(len(x), N - a)
    g = np.array([np.sqrt(1 - pan), np.sqrt(1 + pan)])
    bus[name][a : a + n] += x[:n] * gain * g


def chord(at, length, notes, vel=0.6, attack=None):
    for name in notes:
        f = hz(name)
        inst, pan = (celli, 0.35) if f < 140 else (violas, 0.0) if f < 330 else (violins, -0.35)
        put("strings", at, inst(f, length, vel, attack=attack), pan=pan)


def roll(at, length, gain=0.5):
    x = timp_roll[: int(length * SR)].copy()
    x *= np.linspace(0.2, 1, len(x))[:, None] ** 2
    put("perc", at, x, gain)


# The opening: a low string drone in D minor under the first light, a harp note for every new
# agent, a timpani roll and a rush of air into the panic, a gong and a boom on it, then nothing.
panic, cut = first["panic"], first["cut"]
chord(0.2, cut - 0.2, ["D2", "A2"], 0.5, attack=2.5)
chord(2.6, cut - 2.6, ["F3", "A3"], 0.35, attack=2.0)
chord(4.8, cut - 4.8, ["E5", "A5"], 0.25, attack=1.8)
put("glock", 0.15, glock(hz("A5"), 3, 0.5))
pent = ["D4", "F4", "G4", "A4", "C5", "D5", "F5", "A5"]
when = 1.0
while when < panic - 0.4:
    note = pent[rng.integers(len(pent))]
    put("harp", when, harp(hz(note), 2.5, 0.25 + 0.3 * when / panic), pan=rng.uniform(-0.6, 0.6))
    when += max(0.12, 0.75 - when * 0.07)
roll(panic - 2.0, 2.0, 0.55)
put("perc", panic, gong[: int(4 * SR)], 0.8)
put("perc", panic, timp_hit, 0.9)
put("piano", panic, piano(hz("D1"), 3, 0.9) + piano(hz("A1"), 3, 0.7))
k = clock(3.0)
put("fx", panic, stereo(np.sin(2 * np.pi * (34 * k + 30 * (1 - np.exp(-k * 5)) / 5)) * np.exp(-k * 1.4) * 0.7))
k = clock(2.0)
put("fx", panic - 2.0, stereo(filt(rng.standard_normal(len(k)), "band", [800, 7000]) * (k / k[-1]) ** 3 * 0.12))
for name in bus:
    bus[name][int(cut * SR) :] = 0
put("piano", cut + 0.3, piano(hz("D5"), 5, 0.55) + piano(hz("D4"), 5, 0.25))

# The reveal: a cymbal swell and the strings opening into the first downbeat.
lead = len(swell) / SR
put("perc", MUSIC - min(lead, 3.2), swell[-int(min(lead, 3.2) * SR) :], 0.45)
chord(first["swell"], MUSIC - first["swell"] + 0.6, ["D4", "A4"], 0.4, attack=1.2)

# The body, a bar of four beats each: the chord, how full the voicing is, and how busy the bar is.
PLAN = [
    ("D", 2, 1),
    ("D", 2, 1),
    ("Bm", 2, 2),
    ("G", 2, 2),
    ("A", 2, 2),
    ("Bm", 2, 3),
    ("G", 2, 3),
    ("D", 2, 3),
    ("A", 2, 3),
    ("Bm", 2, 3),
    ("G", 4, 4),
    ("D", 4, 4),
    ("Em", 4, 4),
    ("A", 4, 4),
    ("Bm", 2, 1),
    ("G", 2, 1),
    ("G", 2, 2),
    ("A", 2, 2),
    ("D", 3, 2),
    ("A", 3, 2),
    ("Bm", 3, 2),
    ("G", 3, 2),
]
VOICING = {
    "D": (["D2", "A2"], ["F#3", "A3"], ["D4", "F#4", "A4"], ["D5", "F#5"]),
    "Bm": (["B1", "F#2"], ["D3", "F#3"], ["B3", "D4", "F#4"], ["B4", "D5"]),
    "G": (["G1", "D2"], ["B2", "D3"], ["G3", "B3", "D4"], ["G4", "B4"]),
    "A": (["A1", "E2"], ["C#3", "E3"], ["A3", "C#4", "E4"], ["A4", "C#5"]),
    "Em": (["E2", "B2"], ["G3", "B3"], ["E4", "G4", "B4"], ["E5", "G5"]),
}
MELODY = {10: "A5", 11: "F#5", 12: "G5", 13: "A5", 18: "D5", 19: "C#5", 20: "B4", 21: "A4"}
for i, (name, size, busy) in enumerate(PLAN):
    at = MUSIC + i * 4 * BEAT
    low, mid, high, top = VOICING[name]
    length = 4 * BEAT + 0.6
    chord(at, length, low + mid[: size - 1] + (high if size >= 3 else []), 0.38 + 0.08 * busy, attack=0.5)
    if size >= 4:
        chord(at, length, high, 0.4, attack=0.4)
    notes = high + top
    if busy >= 2:
        step = BEAT / 2 if busy >= 3 else BEAT
        for q in range(int(4 * BEAT / step)):
            put("piano", at + q * step, piano(hz(notes[q % len(notes)]), 1.6, 0.32 + 0.05 * (q % 2 == 0)), pan=0.2)
    else:
        put("piano", at, piano(hz(high[0]), 3, 0.35), pan=0.1)
    if busy >= 3:
        for q in range(8):
            put("strings", at + q * BEAT / 2, celli(hz(low[0]) * 2, 0.32, 0.35, attack=0.01, release=0.18), pan=0.35)
    if busy == 4:
        put("perc", at, timp_hit, 0.45)
    if i in MELODY:
        put("strings", at, violins(hz(MELODY[i]), 4 * BEAT + 0.8, 0.55, attack=0.35), pan=-0.2)

# The close: the last chord blooms on the name, with a glockenspiel and a soft timpani roll.
sting = first["sting"]
chord(sting, LENGTH - sting, ["D2", "A2", "F#3", "A3", "D4", "F#4", "A4", "D5"], 0.55, attack=0.3)
put("glock", sting, glock(hz("D6"), 4, 0.6) + glock(hz("A5"), 4, 0.35))
put("piano", sting, piano(hz("D3"), 5, 0.5) + piano(hz("A3"), 5, 0.4) + piano(hz("F#4"), 5, 0.35))
roll(sting - 1.2, 1.4, 0.3)


def whoosh(at, gain):
    k = clock(1.2)
    w = np.zeros(len(k))
    nz = rng.standard_normal(len(k))
    for p in range(8):
        lo = 300 * 8 ** np.sin(np.pi * (p + 0.5) / 8)
        seg = slice(p * len(k) // 8, (p + 1) * len(k) // 8)
        w[seg] = filt(nz, "band", [lo, min(lo * 2.2, 16000)])[seg]
    put("fx", at - 0.6, stereo(w * np.sin(np.linspace(0, np.pi, len(k))) ** 2 * 0.22 * gain))


ROLES = ["D6", "E6", "F#6", "A6", "B6", "D7", "E7"]
roles = 0
for s in sounds:
    kind, v, at = s["kind"], s.get("strength", 1), s["at"]
    if kind == "herd" and at > MUSIC:
        chord(at - 1.0, 3.2, ["A#4", "A5"], 0.22, attack=1.2)
    elif kind == "knock":
        put("perc", at, timp_hit[: int(1.5 * SR)], 0.35 * v)
        put("glock", at + 0.02, glock(hz("E6"), 1.2, 0.18 * v))
    elif kind == "whoosh":
        whoosh(at, v)
        if at > first["crane"]:
            put("piano", at, piano(hz("B1"), 4, 0.5) + piano(hz("F#3"), 4, 0.25))
            put("perc", at, timp_hit, 0.3)
    elif kind in ("rise", "fall", "count"):
        run = {
            "rise": ["D4", "F#4", "A4", "D5", "F#5", "A5"],
            "fall": ["A4", "F#4", "D4", "A3", "F#3", "D3"],
            "count": ["D4", "F#4", "A4", "D5", "F#5", "A5", "D6"],
        }[kind]
        gap = 0.2 if kind == "count" else 0.06
        for j, n in enumerate(run):
            put("harp", at + j * gap, harp(hz(n), 1.6, 0.3 + 0.02 * j), pan=(j / len(run) - 0.5) * 0.6)
    elif kind == "glass":
        for j, n in enumerate(["A6", "E6", "C#7"]):
            put("glock", at + j * 0.03, glock(hz(n), 1.6, 0.18))
    elif kind == "ping":
        put("glock", at, glock(hz(ROLES[roles % 7]), 1.4, 0.16), pan=rng.uniform(-0.5, 0.5))
        roles += 1
    elif kind == "papers":
        for j in range(18):
            put("harp", at + j * 0.11, harp(hz(["B4", "D5", "F#5", "A5"][j % 4]), 1.0, 0.16), pan=rng.uniform(-0.7, 0.7))
    elif kind == "argue":
        put("strings", at, violins(hz("C#6"), 1.2, 0.18, attack=0.2) + violins(hz("D6"), 1.2, 0.16, attack=0.2))
    elif kind == "chime":
        for n in ["D6", "F#6", "A6"]:
            put("glock", at, glock(hz(n), 3, 0.3))
    elif kind == "crane":
        put("perc", at - min(lead, 2.0), swell[-int(min(lead, 2.0) * SR) :], 0.35)
        put("perc", at, timp_hit, 0.6)
    elif kind == "shock":
        n = int(1.2 * SR)
        put("perc", at, filt(drum[:n] * np.exp(-np.arange(n) / SR * 3)[:, None], "low", 200), 0.25 * v)
    elif kind == "land":
        put("perc", at, timp_hit, 0.6)
        put("glock", at, glock(hz("A5"), 3, 0.4) + glock(hz("D6"), 3, 0.3))
    elif kind == "resolve":
        put("perc", at, timp_hit, 0.35)


def room(x, seconds, decay, bright=7000):
    out = np.zeros_like(x)
    for c in range(2):
        k = clock(seconds)
        ir = filt(rng.standard_normal(len(k)), "low", bright) * np.exp(-k * decay)
        ir /= np.sqrt(np.sum(ir**2))
        out[:, c] = fftconvolve(x[:, c], ir)[: len(x)]
    return out


music = bus["strings"] + bus["piano"] * 0.8 + bus["harp"] * 0.7 + bus["glock"] * 0.6 + bus["perc"] * 0.9
music = music + room(music, 3.2, 1.6) * 0.32 + bus["fx"]

# The voice: up-sampled, cleaned, lightly compressed, a short room on it, and the music ducks under.
vox = np.zeros(N)
for v in cues["voice"]:
    x, rate = sf.read(VOICE / f"{v['key']}.wav")
    x = resample_poly(x, SR // 1000, rate // 1000)
    x = x[int(v.get("from", 0) * SR) : int(v["to"] * SR) if "to" in v else len(x)].copy()
    fade = int(0.01 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    start = int(round(v["at"] * SR))
    n = min(len(x), N - start)
    vox[start : start + n] += x[:n]
vox = filt(vox, "high", 85)
vox = vox + filt(vox, "band", [2800, 6000]) * 0.35 - filt(vox, "band", [250, 500]) * 0.15
level = np.sqrt(filt(vox**2, "low", 12).clip(0)) + 1e-6
vox = vox * np.minimum(1, (0.09 / level) ** 0.4)
presence = np.sqrt(filt(vox**2, "low", 4).clip(0))
vox *= 10 ** (-15 / 20) / np.sqrt(np.mean(vox[presence > 0.25 * presence.max()] ** 2))
vox_wet = room(stereo(vox), 0.9, 7)[:, 0]
duck = 1 - 0.45 * np.clip(presence / (0.4 * presence.max()), 0, 1)

ref = music[int(MUSIC * SR) : int(sting * SR)]
music *= 10 ** (-22 / 20) / np.sqrt(np.mean(ref**2))
tail = np.clip((LENGTH - t) / 0.9, 0, 1)[:, None]
mix = music * duck[:, None] + stereo(vox + vox_wet * 0.08)
OUT.mkdir(parents=True, exist_ok=True)
for name, x in (("mix.wav", mix), ("music.wav", music)):
    sf.write(OUT / name, (np.tanh(x * tail * 1.5) / 1.5).astype(np.float32), SR, subtype="PCM_16")
print(f"wrote {OUT}/mix.wav and music.wav, {LENGTH:.0f}s, {len(cues['voice'])} lines, {len(sounds)} cues")
