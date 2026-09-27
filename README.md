# FIAM

Market-neutral US equity strategy, McGill-FIAM Hackathon 2026. `BRIEF.md` is the story,
`RESULTS.md` every number.

## Run it: Windows, macOS or Linux

1. Install [uv](https://docs.astral.sh/uv/) once. It brings Python 3.14 and the pinned packages.
   - macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. In this folder: `uv run run.py`

What it does depends on what is in `data/`. Only `--official` changes the committed results:

| in `data/` | what `uv run run.py` does | time |
|---|---|---|
| nothing | checks `submission/holdings.csv` and `returns.csv` against the brief; recomputes IR, Sharpe and beta | seconds |
| the organizer's files | rebuilds the book into `out/` and compares it with the official results | 1 min |
| plus the WRDS exports | the same, and the book matches the official one exactly | 1 min |

To add data, point it at the folder holding it: `uv run run.py --import ~/Downloads`. It copies
the organizer's files by their names and converts WRDS exports, recognised by their columns;
everything else in the folder is ignored.

    uv run run.py --ml          # plus the model comparison, 20 min
    uv run run.py --official    # the team's run: rewrites submission/ and RESULTS.md, needs WRDS
    uv run pytest               # mechanics tests, seconds

Without uv: in a Python 3.14 virtual environment, `python -m pip install -r requirements.txt`,
then `python run.py`.

## If something goes wrong

- **macOS, `--ml` or `pytest`:** `brew install libomp` (LightGBM needs it).
- **Intel Mac, or macOS 13 and older:** everything except `--ml` runs; PyTorch 2.14 has no
  build there.
- **Windows on ARM:** pyarrow has no ARM build; use x64 Python:
  `uv run --python cpython-3.14-windows-x86_64-none run.py`.
- **No WRDS:** the book moves in the third decimal (IR 0.833 against 0.834) and the run says
  provisional, as `RESULTS.md` records.
- **Audit: "model exhibits were built from the current code" fails:** code changed after the last
  official model run. Rerun `uv run run.py --official --ml` on the team's machine.

## Optional inputs

- **WRDS:** these exports, shared privately and never committed. Columns kept are in `src/wrds.py`.

  | export | WRDS dataset | dates | our file's SHA-256 |
  |---|---|---|---|
  | CRSP monthly | Monthly Stock File, CIZ, with security info and delistings | 2010-01 to 2025-12 | `2796c030f9ed6f34…` |
  | S&P 500 index | CRSP index series, S&P 500 universe | 2010-01 to 2025-12 | `382a3f33c2c6b6d6…` |
  | Compustat quarterly | Fundamentals Quarterly (`fundq`) with `rdq`, `dldte`, `dlrsn` | 2010-01 to 2026-08 | `5f943fea4ec4debd…` |

- **Labels:** the SEC records they were checked against are in `data/edgar_cache.zip`, unpacked
  by the first rebuild. `uv run src/exhibits/labels.py --fetch` with `SEC_CONTACT` in `.env`
  fetches missing filers; SEC's current records can differ, which changes the labels.
- **Live score:** `uv run src/exhibits/live_score.py --fetch`, with `TIINGO_API_KEY` in `.env`.
- **Benchmarks:** pinned in `data/benchmarks/`; `uv run src/benchmarks.py --refresh <file>`
  updates one.

## Agents

    uv run src/agents/harness.py verify     # model files against models/MANIFEST.txt
    uv run src/agents/harness.py register   # sets up the dedicated fiam-runs Hermes profile
    uv run src/agents/harness.py serve qwen # a model for the Hermes app

Windows: llama.cpp's Vulkan build in `models/llama.cpp/`. Lightning AI: create a Studio on a 24 GB
GPU, clone the repo, upload `data/`, run `bash src/agents/setup_lightning.sh` once, then
`python run.py --official --agents`. Stop the Studio when done.

## MAIN.py

The brief asks for one file. `uv run tools/build_main.py` (in this git checkout) writes `MAIN.py`,
which carries every file the run needs except the tests and the EDGAR archive. `uv run MAIN.py` in
an empty folder unpacks them and runs `run.py`: the same results and 28-check audit, except the
labels, which need the archive (`--with-edgar` adds it: 21 MB instead of 3 MB).

## Layout

`run.py` the one command · `src/pipeline.py` the book and shared maths · `src/exhibits/` and
`src/controls/` exhibits and the audit · `src/verify.py` the brief's rules · `src/compare.py` a run
against the official results · `src/paths.py` where outputs go · `src/ml/` the model comparison ·
`src/agents/` Hermes runner, tool server, agents · `prompts/agents/` what the models are sent ·
`submission/` the official results · `out/`, `data/`, `cache/` gitignored.

Offline and reproducible for supplied data; benchmarks versioned with sources. Nicholas commits;
assistants only write files.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
