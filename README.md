# FIAM

Market-neutral US equity strategy, McGill-FIAM Asset Management Hackathon 2026.

Read `BRIEF.md` for what we built and why. `RESULTS.md` has the numbers.

## Setup

    python -m pip install -r requirements.txt

Python 3.14.5, no GPU needed. Copy the organizer's two Parquet files into `data/`.
**Never re-save them in place**, write intermediates under new names instead: rewriting a
Parquet changes its bytes even with identical rows, and `run.py` records a hash of every data
file so a judge can tell the numbers came from the supplied data. Benchmarks are already in
`data/benchmarks/` and need no key.

## Running it

    python run.py          # about twenty seconds
    python run.py --ml     # adds the model comparison and research exhibits, hours

`run.py` builds the portfolio, repairs labels, runs the exhibits, copies numbers into
`RESULTS.md`, draws the charts and re-checks the look-ahead list. Use it instead of calling
scripts by hand, so the write-up can never disagree with the output.

It stops if any competition limit breaks, so a clean run means the book is compliant. The last
step is a reproducibility audit: seventeen look-ahead and survivorship checks that exit
non-zero on failure. Each is a necessary condition, not proof the submission reproduces.

Style is `ruff check` and `ruff format`, configured in `pyproject.toml`.

## Layout

| | |
|---|---|
| `run.py` | runs everything below in order. This is the one to use |
| `src/pipeline.py` | screen, score, neutralize, optimize, round to whole shares, charge costs |
| `src/report.py` | copies `metrics.json` into `RESULTS.md` |
| `src/charts.py` | the eight performance charts, cumulative return through P&L contributors |
| `src/exhibit_charts.py` | the ten research charts, deciles through the placebo lab |
| `src/check_docs.py` | flags any hand-typed number that no longer matches |
| `src/features.py` | join seam, so a new feature block does not mean rebuilding everything |
| `src/exhibits/` | sub-period split, cost ladder, turnover sweep, label repair, rules statistics, baseline freeze, constraint survival, placebo lab |
| `src/ml/` | the four-model comparison, folds through decile tables, plus the NN3 seed sweep |
| `src/agents/` | two deterministic research controls, the reproducibility audit, and the devil's-advocate data pack |
| `prompts/` | what we send the local models, word for word. Part of the submission |
| `models/MANIFEST.txt` | model hashes for the research layer. Weights stay out of git |
| `submission/` | generated output, including `exhibits/` and `figures/` |
| `data/`, `cache/`, `.venv-gpu/` | gitignored |

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
