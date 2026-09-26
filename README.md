# FIAM

Market-neutral US equity strategy, McGill-FIAM Hackathon 2026. `BRIEF.md` is the story,
`RESULTS.md` every number.

## Run it

    python -m pip install -r requirements.txt   # Python 3.14, CPU only
    python run.py --ml         # first run on a new machine: everything, 28-check audit, 20 min
    python run.py              # after that: book, docs, charts and audit, about a minute
    python run.py --agents     # plus the three agents, needs a GPU and models/
    python run.py --official   # refuses a run without the WRDS inputs
    pytest                     # mechanics tests, seconds

Put the organizer's two Parquet files and `factor_char_list.csv` in `data/` and never re-save
them. The benchmarks are already in `data/benchmarks/`. The first run needs `--ml`: the model
exhibits' run records live in the gitignored `cache/`, so a plain run fails two audit checks until
they are rebuilt. Steps are skipped when nothing they read changed; `--fresh` reruns all.

## Optional inputs

- **WRDS:** `python src/wrds.py <csvs>` with these exports, shared privately, never committed.

  | export | WRDS dataset | dates | our file's SHA-256 |
  |---|---|---|---|
  | CRSP monthly | Monthly Stock File, CIZ, with security info and delistings | 2010-01 to 2025-12 | `2796c030f9ed6f34…` |
  | S&P 500 index | CRSP index series, S&P 500 universe | 2010-01 to 2025-12 | `382a3f33c2c6b6d6…` |
  | Compustat quarterly | Fundamentals Quarterly (`fundq`) with `rdq`, `dldte`, `dlrsn` | 2010-01 to 2026-08 | `5f943fea4ec4debd…` |

  Columns kept are listed in `src/wrds.py`. Without WRDS the numbers move in the third decimal,
  so the stale-number check stops the build: the committed results need `data/wrds/`.
- **Labels:** once after cloning, `Expand-Archive data/edgar_cache.zip -DestinationPath cache`
  (or `unzip data/edgar_cache.zip -d cache`): the SEC records the labels were checked against.
  `python src/exhibits/labels.py --fetch` with `SEC_CONTACT` in `.env` fetches only missing
  filers; SEC's current records can differ, which changes the labels.
- **Live score:** `python src/exhibits/live_score.py --fetch`, with `TIINGO_API_KEY` in `.env`.
- **Benchmarks:** pinned in `data/benchmarks/`; `python src/benchmarks.py --refresh <file>` updates one.

## Agents

    python src/agents/harness.py verify     # model files against models/MANIFEST.txt
    python src/agents/harness.py register   # sets up the dedicated fiam-runs Hermes profile
    python src/agents/harness.py serve qwen # a model for the Hermes app

Windows: llama.cpp's Vulkan build in `models/llama.cpp/`. Lightning AI: create a Studio on a 24 GB
GPU, clone the repo, upload `data/`, run `bash src/agents/setup_lightning.sh` once, then
`python run.py --agents`. Stop the Studio when done.

## Layout

`src/pipeline.py` the book and shared maths · `src/exhibits/` and `src/controls/` exhibits and the
audit · `src/ml/` the model comparison · `src/agents/` Hermes runner, tool server, agents ·
`prompts/agents/` what the models are sent · `submission/` output · `data/`, `cache/` gitignored.

Offline and reproducible for supplied data; benchmarks versioned with sources. Nicholas commits;
assistants only write files.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
