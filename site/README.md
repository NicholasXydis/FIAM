# QUARCC Purple · FIAM showcase

The final book as an interactive 3D tour in one offline file, `out/site/fiam.html`. Double-click it.
It needs no internet and no server.

## Build

```
uv run tools/build_site.py       # final v3's pack to src/data/fiam.json and crashes.json (needs fiam_results.zip imported)
cd site && pnpm install && pnpm build
```

`uv run pytest tests/test_site.py` checks every number in `fiam.json` against the pack.
`pnpm dev` serves it with live reload, `pnpm check` type-checks and checks formatting, and
`pnpm format` formats.

## Presenting

| Key | Does |
|---|---|
| → ↓ Space | Next scene (Space plays and pauses the month-by-month scenes) |
| ← ↑ | Previous scene |
| 0 to 9 | Jump to a scene |
| O | Every scene as cards |
| P | Guided tour that moves on by itself |
| M | Sound on or off |
| E | Explore freely, drag to orbit and scroll to zoom |
| F | Full screen |

Click anything that glows. Add `?present` to the address to hide the hints, `?tour` to start the
guided tour on open, and `?q=0`, `1` or `2` to fix the quality (it otherwise steps down by itself on
a slow machine).

The QR code at the end holds the text in `src/config.ts`. Put a link there and rebuild.

## The ad

`film.html` is a 62 second ad, "Calm, by design", built from the same data to `out/film/film.html`
with `pnpm film`. AI is becoming part of the market and starting to think alike; QUARCC Purple is
market neutral, has seven AI agents doing its research on its own machines, and studies a crowd of
sixty AI investors as a risk. Everything on screen is a pure function of time, so `?record` hands a recorder
`__draw(t, subframes)` to step it frame by frame; each frame is the average of 16 subframes, which
gives motion blur, depth of field, smooth edges and soft shadows.

```
uv run site/ad/make.py             # page, voice timing, score, both renders, deck/*.mp4, review
uv run site/ad/make.py --preview   # quick half-size copies in out/ad/ (about 3 min)
uv run site/ad/voice.py agents     # remake one voice line from ad/voice/lines.json
```

It writes `deck/QUARCC_Purple_FIAM_trailer.mp4` (16:9) and `deck/QUARCC_Purple_FIAM_trailer_vertical.mp4`
(9:16), 1080p at 60 fps, H.264 with AAC at -14 LUFS. To watch it live with sound, open
`out/film/film.html` after a build and click: space pauses, the arrows skip, the bar along the bottom
seeks.

- **Voice**: Kokoro (Apache-2.0), af_heart, made on this machine by `ad/voice.py`. Each sentence is
  spoken on its own and joined with a set pause; `ad/voice/words.json` times every word, and the
  titles appear on the word they show.
- **Music**: composed in code (`ad/score.py`) on a 120 BPM grid so every cut lands on a beat, played
  on VSCO 2 Community Edition samples (CC0, Versilian Studios; upright piano by Simon Dalzell of Ivy
  Audio), downloaded once into `cache/vsco2`.
- **Review**: `ad/review.py` transcribes the mix with Whisper (run locally) against the script, checks
  every pause, that each cut sits on the beat with an audible accent, and that the picture and the
  camera move without jolts. It writes `out/ad/review/report.md` and pictures of the sound and motion.
- `tests/test_site.py` checks that every number the voice says matches the data. The recorder needs
  puppeteer's Chrome once: `pnpm exec puppeteer browsers install chrome`.
