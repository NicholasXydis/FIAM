# FIAM

Market-neutral US equity strategy, McGill-FIAM Asset Management Hackathon 2026.

Read `BRIEF.md` for what we built and why. `RESULTS.md` has the numbers.

## Setup

    python -m pip install -r requirements.txt

Verified on Python 3.14.5. No GPU needed.

Copy the organizer's two Parquet files into `data/` and check them once against the SHA-256s in
their `data/readme.md`:

    sha256sum data/*.parquet

Do not re-save those files in place. Rewriting one changes its hash even when the rows are
identical, so write intermediates under new names.

Benchmark data is already in `data/benchmarks/`, the FRED T-bill rate and Ken French factors.
Neither needs a key. `.env` is optional and the pipeline never reads it.

## Running it

    python run.py

That runs all four steps in order: builds the portfolio, copies the numbers into `RESULTS.md`,
draws the charts, then checks nothing is out of date. Use it instead of calling the scripts by
hand, so the write-up can never disagree with the output.

The pipeline stops if any competition limit breaks, so a clean run means the book is compliant.

## Layout

| | |
|---|---|
| `run.py` | runs everything below in order. This is the one to use |
| `src/pipeline.py` | screen, score, neutralize, optimize, round to whole shares, charge costs |
| `src/report.py` | copies `metrics.json` into `RESULTS.md` |
| `src/charts.py` | the seven required charts |
| `src/check_docs.py` | flags any hand-typed number that no longer matches |
| `src/features.py` | join seam, so a new feature block does not mean rebuilding everything |
| `prompts/` | what we send the local models, word for word. Part of the submission |
| `models/MANIFEST.txt` | model hashes for the research layer. Weights stay out of git |
| `submission/` | generated output |
| `data/`, `cache/`, `notebooks/`, `.venv-gpu/` | gitignored |

## Optional GPU setup

Only the text encoder needs a GPU, and only for whoever runs it. Every submitted number
reproduces on CPU. AMD ships Windows ROCm wheels for Python 3.12 only, so it gets its own
interpreter:

    py -3.12 -m venv .venv-gpu
    .venv-gpu\Scripts\python -m pip install --no-cache-dir --find-links https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/ --extra-index-url https://pypi.org/simple torch==2.9.1+rocm7.2.1

Verified on an RX 9070 XT. A Mac or an NVIDIA box works too.

## Submission

The rules want one file called `MAIN.py`. We build it from `src/` at the end, so there is only
ever one copy to edit while the work is moving.

Everything built from the supplied data runs offline. The benchmark inputs come from outside and
are versioned with their source.

## Working rules

Nicholas commits and pushes through GitHub Desktop. Agents and assistants write files and report
what changed. They never run `git commit`, `git push`, `git merge`, or create branches.

Prompts live in `prompts/` as files. The cache keys off their hash, so `git log prompts/` counts
how many versions we tried without anyone tracking it by hand.

## Team

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
