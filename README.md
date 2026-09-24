# FIAM

Market-neutral US equity strategy, McGill-FIAM Hackathon 2026. `BRIEF.md` is the story,
`RESULTS.md` every number, `FIAM_Plan.md` what is left, `CLAUDE.md` the rules.

## Run it

    python -m pip install -r requirements.txt   # Python 3.14, CPU only
    python run.py              # book, docs, charts, 28-check audit, about a minute
    python run.py --ml         # plus models and controls, 20 min fresh, under a minute if unchanged
    python run.py --agents     # plus the three agents, needs a GPU and models/
    python run.py --official   # refuses a run without the WRDS inputs
    pytest                     # mechanics tests, seconds

Put the organizer's two Parquet files in `data/` and never re-save them. Steps are skipped when
nothing they read changed; `--fresh` reruns all.

## Optional inputs

- **WRDS:** `python src/wrds.py <csvs>` with these exports, shared privately, never committed.

  | export | WRDS dataset | dates | our file's SHA-256 |
  |---|---|---|---|
  | CRSP monthly | Monthly Stock File, CIZ, with security info and delistings | 2010-01 to 2025-12 | `2796c030f9ed6f34…` |
  | S&P 500 index | CRSP index series, S&P 500 universe | 2010-01 to 2025-12 | `382a3f33c2c6b6d6…` |
  | Compustat quarterly | Fundamentals Quarterly (`fundq`) with `rdq`, `dldte`, `dlrsn` | 2010-01 to 2026-08 | `5f943fea4ec4debd…` |

  Columns kept are listed in `src/wrds.py`. Without WRDS the book differs by 0.001 of IR.
- **Labels:** `python src/exhibits/labels.py --fetch`, once, with `SEC_CONTACT` in `.env`.
- **Live score:** `python src/exhibits/live_score.py --fetch`, with `TIINGO_API_KEY` in `.env`.
- **Benchmarks:** pinned in `data/benchmarks/`; `python src/benchmarks.py --refresh <file>` updates one.

## Agents

    python src/agents/harness.py verify     # model files against models/MANIFEST.txt
    python src/agents/harness.py register   # sets up this machine's Hermes
    python src/agents/harness.py serve qwen # a model for the Hermes app

Windows: llama.cpp's Vulkan build in `models/llama.cpp/`. Linux or Lightning AI:
`bash src/agents/setup_lightning.sh` (steps in `FIAM_Plan.md`).

## Layout

`src/pipeline.py` the book and shared maths · `src/exhibits/` and `src/controls/` exhibits and the
audit · `src/ml/` the model comparison · `src/agents/` Hermes runner, tool server, agents ·
`prompts/agents/` what the models are sent · `submission/` output · `data/`, `cache/` gitignored.

Offline and reproducible for supplied data; benchmarks versioned with sources. Nicholas commits;
assistants only write files.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
