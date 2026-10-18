# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "kokoro==0.9.4",
#   "soundfile",
#   "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
# The ad's voice, made locally with Kokoro (Apache-2.0), voice af_heart.
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

# Kokoro's 24 kHz rate, and the set pause between sentences in seconds.
SR = 24000
GAP = 0.2
# Opening, closing and brand lines go slower than 0.9, for weight.
SPEED = {"rise": 0.84, "close": 0.84, "brand": 0.86}
# lines.json holds the script; it spells QUARCC Quark to say it right.
HERE = Path(__file__).parent / "voice"
lines = json.loads((HERE / "lines.json").read_text())
# words.json keeps earlier timings, so one line can be remade alone.
words_file = HERE / "words.json"
words = json.loads(words_file.read_text()) if words_file.exists() else {}
# Kokoro-82M from hexgrad on Hugging Face, in American English.
pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")


# A sentence's audio cut tight to the speech, words timed from the cut.
def say(text, speed):
    audio, timed = [], []
    # Kokoro speaks in chunks; each word shifts by the audio before it.
    for part in pipe(text, voice="af_heart", speed=speed):
        offset = sum(len(a) for a in audio) / SR
        audio.append(np.asarray(part.audio))
        for t in part.tokens or []:
            if t.start_ts is not None and any(c.isalnum() for c in t.text):
                timed.append([t.text, offset + t.start_ts, offset + t.end_ts])
    # Keeps 0.15 s before and 0.12 s after where its 10 ms level tops 0.01.
    audio = np.concatenate(audio)
    loud = np.flatnonzero(np.convolve(np.abs(audio), np.ones(240) / 240, "same") > 0.01)
    a, b = max(0, loud[0] - int(0.15 * SR)), min(len(audio), loud[-1] + int(0.12 * SR))
    return audio[a:b], [[w, s - a / SR, e - a / SR] for w, s, e in timed]


# Each line named, or all: 50 ms lead, sentences with gaps, 100 ms tail.
for key in sys.argv[1:] or list(lines):
    out, timed = [np.zeros(int(0.05 * SR))], []
    for i, sentence in enumerate(lines[key]):
        if i:
            out.append(np.zeros(int(GAP * SR)))
        start = sum(len(a) for a in out) / SR
        audio, spoken = say(sentence, SPEED.get(key, 0.9))
        out.append(audio)
        timed += [[w, round(start + s, 3), round(start + e, 3)] for w, s, e in spoken]
    # Saves the line's wav, and its word times in seconds from its start.
    audio = np.concatenate(out + [np.zeros(int(0.1 * SR))])
    sf.write(HERE / f"{key}.wav", audio, SR)
    words[key] = timed
    print(f"{key}: {len(audio) / SR:.2f}s  {' '.join(lines[key])}")
# Every line's word timings, which the film times its titles by.
words_file.write_text(json.dumps(words, indent=1) + "\n")
