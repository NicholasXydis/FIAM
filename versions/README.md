# Versions

Each folder holds `recipe.json`, the fingerprints a test checks, so a closed version can never change unnoticed.

## v1

- Round one's submitted book, built by `fiam/book.py` on twelve signals with a fixed $10 million fund
- Its holdings and returns live in `submission/` and its September 2026 book is frozen
- Several of its choices were made while 2021 to 2026 was visible, so its record is partly in sample and never called out of sample

## vfinal

- The final fund for the finals, $1 billion compounding, with every finals rule enforced in code
- Its code is `fiam/vfinal/`, its settings and protocol are in `versions/vfinal/`, and `uv run fiam help` lists its commands
- Rows public after 2020 open only through the data gate, and the lock in `frozen/vfinal/` hashes its code, settings and headline outputs
