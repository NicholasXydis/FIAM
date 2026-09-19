# FIAM

Team repository for the FIAM challenge, Montréal. Read `BRIEF.md` first.

## Setup

python -m pip install pyarrow pandas scikit-learn lightgbm statsmodels matplotlib shap cvxpy requests tiingo

Copy the organizer's files into `data/`. The organizers publish a SHA-256 for each Parquet file under
"File integrity" in their `data/readme.md` — a fingerprint of the file's bytes. Check yours match, once:

    sha256sum data/*.parquet

Both match as of the last check. Never re-save these files in place: rewriting one changes its
fingerprint even when the rows are identical. Intermediates go to `data/` under new names.

Copy `.env.example` to `.env` and fill in the Tiingo and LightningAI keys.

## Layout

`prompts/` what we send the local model, and part of the submission. `src/` the pipeline.
`submission/` what we hand in. `data/`, `cache/`, `models/`, `notebooks/` are gitignored.

`MAIN.py` is the entrypoint and the single file we submit. It runs offline with no API key, top to bottom,
and writes every chart to `submission/figures/` as PNG. `models/MANIFEST.txt` records the model weights
we used, by name and SHA-256 — the weights themselves stay out of git.

## Rules

Branch off `main` & open a pull request.

Prompts stay as files in `prompts/`. The cache keys off their hash.

## Team

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
