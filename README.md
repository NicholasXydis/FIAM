# FIAM

Team repository for the FIAM challenge, Montréal. Read `BRIEF.md` first.

## Setup

python -m pip install pyarrow pandas scikit-learn lightgbm statsmodels matplotlib shap cvxpy requests tiingo

Copy the organizer's files into `data/`, then check the two Parquet files against the checksums in their
`readme.md`.

Copy `.env.example` to `.env` and fill in the Tiingo and LightningAI keys.

## Layout

`prompts/` what we send the local model, and part of the submission. `src/` the pipeline.
`submission/` what we hand in. `data/`, `cache/`, `models/`, `notebooks/` are gitignored.

## Rules

Branch off `main` & open a pull request.

Prompts stay as files in `prompts/`. The cache keys off their hash.

## Team

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
