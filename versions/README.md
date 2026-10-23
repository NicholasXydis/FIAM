# Versions

Each folder holds `recipe.json`, the fingerprints a test checks, so a closed version can never change unnoticed.

## v1

- Round one's submitted book, built by `fiam/book.py` on twelve signals with a fixed $10 million fund
- Its holdings and returns live in `submission/` and its September 2026 book is frozen
- Several of its choices were made while 2021 to 2026 was visible, so its record is not clean out of sample

## v2

- v1 plus trading costs, persistence, beta control, shorts and liquidity rules in `fiam/v2.py`
- Runs with `uv run run.py --v2` under the v2 protocol and its first two amendments
- Its September 2026 book and fitted parameters are frozen

## v3

- Final v3 adds the drawdown brake, size control, a 10 percent risk target and zero beta
- Information ratio 0.99 at $10 million but 0.45 at $1 billion over 2021 to 2026, and Sharpe -1.25 on 2016 to 2020
- Fifteen of its choices were made with 2021 to 2026 visible and it breaks four finals rules

## v4

- The finals book, $1 billion compounding, with every finals rule enforced in code
- Built only on choices tested before 2021, with one sealed run of 2021 to 2026
- Its protocol is written before any run and its files are frozen at the freeze
