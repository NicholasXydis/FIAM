# FIAM

A market-neutral US equity strategy for the McGill-FIAM Hackathon 2026. `BRIEF.md` tells the story,
`RESULTS.md` has every number, `PREREGISTRATION.md` the tests we fixed before running them. The same
code and data give the same numbers on any machine.

## Run it (Windows, macOS, Linux)

1. Install [uv](https://docs.astral.sh/uv/) once; it brings Python 3.14 and every pinned package.
   - macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Put the organizer's three files beside `MAIN.py` (or in `data/`), then run `uv run MAIN.py`.

| what is there | what happens | time |
|---|---|---|
| nothing | checks the submitted holdings and returns against the brief's rules | seconds |
| the organizer's files | builds the data once, rebuilds the book into `out/`, compares it | a few minutes |
| our private bundle, `data/fiam_v1/` | the same, matching the official book exactly | a few minutes |

    uv run run.py --import ~/Downloads     # organizer files, WRDS exports or fiam_v1.zip
    uv run run.py --all --smoke            # every step on a small slice, a quick rehearsal
    uv run run.py --official --all         # everything: models, agents, results
    uv run run.py --export-data            # fiam_v1.zip for a teammate (private, never committed)
    uv run pytest                          # tests, seconds
    uv run tools/build_deck.py             # the deck, from the results
    uv run tools/gpu_probe.py              # what this machine's GPU can run

`uv run run.py --help` lists every option.

## Data

Every step reads `data/fiam_v1/`, built from the organizer's files, plus WRDS extracts we are licensed
to use. It is never committed or submitted. `DATA_CARD.md` inside it lists each file.

## Agents

`--agents` downloads one pinned llama.cpp build and two pinned open models (about 30 GB, checked
by SHA-256). They need a 16 GB GPU or an Apple silicon Mac with 24 GB. A stopped run resumes.

## If something goes wrong

- **macOS, `--ml` or `pytest`:** `brew install libomp`.
- **Intel Mac or macOS 13:** everything but `--ml` runs.
- **Audit says model results are stale:** the code changed since they ran; run
  `uv run run.py --official --ml`.

## Layout

`run.py` the one command · `fiam/data.py`, `build_data.py` the data · `fiam/book.py`, `costs.py`
the book and its costs · `fiam/ml/` the models · `fiam/agents/` the agents · `fiam/exhibits/`,
`fiam/checks/`, `fiam/report/` results, audit and docs · `prompts/agents/` what the models read ·
`submission/` the official results.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
