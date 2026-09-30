# FIAM

Market-neutral US equity strategy, McGill-FIAM Hackathon 2026: neutral by construction, with the
realized beta measured monthly and daily. `BRIEF.md` is the story, `RESULTS.md` every number,
`PREREGISTRATION.md` the next tests, fixed before they ran. The same code and data give the same
numbers on any machine.

## Run it: Windows, macOS, Linux or Lightning AI

1. Install [uv](https://docs.astral.sh/uv/) once. It brings Python 3.14 and the pinned packages.
   - macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. In this folder: `uv run run.py`

| in `data/` | what `uv run run.py` does | time |
|---|---|---|
| nothing | checks `submission/holdings.csv` and `returns.csv` against the brief | seconds |
| the organizer's files | builds the data bundle once, rebuilds the book into `out/`, compares it | 1 min |
| the full bundle, `fiam_v1/` | the same, and the book matches the official one exactly | 1 min |

    uv run run.py --import ~/Downloads       # organizer files, WRDS exports or fiam_v1.zip
    uv run run.py --all --smoke              # every step on a small slice, a 10-minute rehearsal
    uv run run.py --official --all           # the team's overnight run: models, agents, results
    uv run run.py --export-data              # fiam_v1.zip for a teammate
    uv run pytest                            # tests on synthetic data, seconds
    uv run tools/gpu_probe.py                # what this machine's GPU can run

`uv run run.py --help` lists every option. Without uv: `python -m pip install -r requirements.txt`
in Python 3.14, then `python run.py`.

## Data

Every step reads one private folder, `data/fiam_v1/`, never committed or submitted. The first run
builds its core from the organizer's files; teammates get all of it with `--export-data` and
`--import fiam_v1.zip`, and share it only among those covered by our WRDS access. Its `DATA_CARD.md`
lists each file. `uv run -m fiam.data` checks it; `FIAM_DATA_DIR` moves it.

## Agents

`--agents` downloads one pinned llama.cpp build for the machine (Vulkan on Windows, Metal on Apple
silicon, CUDA or Vulkan on Linux and Lightning AI, CPU otherwise) and the two pinned models, about
30 GB once, each checked against its SHA-256. They need a 16 GB GPU or an Apple silicon Mac with
24 GB. A stopped run resumes where it left off. On Lightning AI: a Studio with an L4 GPU, then the
commands above.

## If something goes wrong

- **macOS, `--ml` or `pytest`:** `brew install libomp` (LightGBM needs it).
- **Intel Mac, or macOS 13 and older:** everything but `--ml` runs; PyTorch 2.14 has no build.
- **Windows on ARM:** use x64 Python: `uv run --python cpython-3.14-windows-x86_64-none run.py`.
- **Qwen on a 24 GB Mac:** raise the GPU memory limit once, `sudo sysctl iogpu.wired_limit_mb=20000`.
- **Audit says model exhibits are stale:** code changed since the models ran; run
  `uv run run.py --official --ml` again.

## MAIN.py

The brief asks for one file. `uv run tools/build_main.py` writes `MAIN.py`, which carries every file
the run needs; `uv run MAIN.py` beside the organizer's files unpacks them and runs `run.py` with the
same results. `--with-edgar` adds the SEC records the labels were checked against.

## Layout

`run.py` the one command · `fiam/data.py`, `build_data.py`, `wrds.py` the data · `fiam/book.py` the
book · `fiam/ml/` teachers, scorer, trader, ship rule and the comparison · `fiam/agents/` the agents
and their runner · `fiam/exhibits/`, `fiam/checks/`, `fiam/report/` exhibits, audit, charts and
docs · `prompts/agents/` what the models are sent · `submission/` the official results.

Nicholas commits; assistants only write files.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
