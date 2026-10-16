# Finals day

Run everything from the folder that holds `MAIN.py`, on any laptop or on Lightning AI.

## Before the day
1. `pip install uv`, then unzip `fiam_finals.zip` from the USB into an empty folder.
2. `uv run MAIN.py --import fiam_v1.zip --import fiam_results.zip` sets up the code, data and
   results, and checks our book reproduces.
3. Rehearse: `uv run MAIN.py --world fake --finals mandates/case_2025.json`. Every book should show
   `breaches 0 empty 0` and its largest country at 75% or less.
4. Run `--rules` once with internet, so the rules reader's model downloads (about 14 GB).

## On the day
1. **Rules.** `uv run MAIN.py --rules rules.pdf` drafts `mandates/<name>_draft.json`, each limit with
   its quote. Check it against the rules and fix it by hand. No GPU: edit a copy of
   `mandates/case_2025.json`. Add `min_market_cap` or `exclude_sectors` by hand if the rules set them.
2. **Data.** `uv run MAIN.py --world <folder>`. If their columns are named differently, copy
   `fiam/world_columns.json` into the folder as `columns.json` and change only what differs.
3. **Books.** `uv run MAIN.py --world --finals mandates/<name>_draft.json`. Add `--window 2021-01
   2025-06` or `--capital 1e8` if the day asks for other months or another fund size.
4. **Pack.** Run the `--pack` command it prints.
5. **Deck.** `uv run MAIN.py --finals-pack` adds a slide with today's book. The deck, the PDF and the
   film are in the zip.

## If something goes wrong
| What | Do this |
|---|---|
| `uv` is not found | `py -m uv run MAIN.py` on Windows, `python3 -m uv run MAIN.py` elsewhere |
| No GPU, or no model | Write the mandate by hand; the books never need a GPU |
| Other column names | `columns.json` beside the data |
| Other currencies | Name the currency column in `columns.json`; rates run to October 2026 |
| The rules cannot all hold | `--finals` names them before any run; fix the mandate |
| A film will not play | Play `deck/ai_crowd_short.mp4` on its own; the PDF has every page |
