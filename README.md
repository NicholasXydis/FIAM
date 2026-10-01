# FIAM

A market-neutral US equity book for the McGill-FIAM Hackathon 2026: twelve published stock
measures, hedged on a beta our machine learning learned, with every trading cost charged.
`BRIEF.md` tells the story in a page; `RESULTS.md` has every number.

## Run it on Windows, macOS or Linux

1. Install [uv](https://docs.astral.sh/uv/) once: it brings Python and every pinned package.
   - macOS, Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Run `uv run MAIN.py`.

| what is beside `MAIN.py` | what it does | time |
|---|---|---|
| nothing | checks the submitted holdings and returns against every rule in the brief | seconds |
| the organizer's three files | builds the data, rebuilds the book into `out/`, compares it | a few minutes |

`uv run run.py --help` lists the rest: `--ml` retrains the models, `--agents` runs the local AI
agents (a 16 GB GPU or a 24 GB Apple silicon Mac), `--official` rewrites `submission/`.

## Layout

`run.py` the one command · `fiam/book.py`, `costs.py` the book and its costs · `fiam/ml/` the models
· `fiam/agents/` the agents · `fiam/exhibits/`, `fiam/checks/`, `fiam/report/` results, audit and
docs · `prompts/agents/` what the models read · `submission/` the official results.

Data from WRDS is licensed, so it is never committed: a run without it is marked provisional.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
