# FIAM

A market-neutral book of US stocks for the McGill-FIAM Hackathon 2026. It buys the best and shorts
the worst on twelve published stock measures, stays neutral to the market with a beta our machine
learning learned, and pays realistic trading costs. `BRIEF.md` tells the story, `RESULTS.md` has
the numbers.

**January 2021 to August 2026, after costs:** information ratio
<!--N:metrics.json:performance.information_ratio:.2f-->0.74<!--/N-->, net return
<!--N:metrics.json:performance.return_net_annual:.1%-->12.8%<!--/N--> a year, beta
<!--N:metrics.json:performance.beta_realized:+.2f-->−0.03<!--/N-->, worst drawdown
<!--N:metrics.json:performance.max_drawdown_total:.1%-->−7.4%<!--/N-->.

## Run it

```
pip install uv
uv run MAIN.py
```

uv installs the right Python and packages by itself (or use `winget install astral-sh.uv` on
Windows, `brew install uv` on a Mac). With nothing beside `MAIN.py`, it checks our holdings against
every rule in the brief in seconds. Put the organizer's three data files beside it and it rebuilds
the whole book in a few minutes and compares it with ours. `uv run run.py --help` lists the rest.

## What is where

`fiam/book.py` builds the book · `fiam/costs.py` charges the costs · `fiam/ml/` the models ·
`fiam/agents/` the AI agents · `fiam/checks/` the audit · `submission/` our official results.

Nicholas Xydis · Yohannah Ilieva · Jérémie Caussignac · Agamjot Singh Bawa · Nokto Lapointe
