# D17 clean book race, rule fixed before any book ran (DECISIONS.md D17):
# the winner is the highest net annual return on 2017-2020 among E5 books with
# |daily beta| <= 0.05 and both legs' after-beta alpha > 0 (legs_report), else
# the highest net return. The previous race winner (betamatch on all-name
# training) races with the three holdable-trained books.
# Usage: python -m fiam.v4b.research.race_d17

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"
BOOKS = {"all_betamatch": OUT / "nautilus_var_betamatch",
         "h_raw": OUT / "nautilus_h_raw",
         "h_volneut": OUT / "nautilus_h_volneut",
         "h_betamatch": OUT / "nautilus_h_betamatch"}
BETA_MAX = 0.05


def row(run: Path) -> dict:
    g = json.loads((run / "E5" / "legs.json").read_text())
    return {"net": g["ann_ret"], "vol": g["ann_vol"], "beta": g["beta_daily"], "maxdd": g["max_drawdown"],
            "long_alpha": g["long"]["alpha_vs_mkt_ann"], "long_t": g["long"]["alpha_t"],
            "short_alpha": g["short"]["alpha_vs_mkt_ann"], "short_t": g["short"]["alpha_t"],
            "costs": g["spread_pct_nav_yr"] + g["impact_pct_nav_yr"] + g["fees_pct_nav_yr"] + g["borrow_pct_nav_yr"],
            "gross": g["compliance"]["avg_gross"], "names": g["compliance"]["avg_names"],
            "turnover": g["compliance"]["turnover_annualised"]}


def main() -> dict:
    rows = {k: row(v) for k, v in BOOKS.items()}
    ok = [k for k, r in rows.items() if abs(r["beta"]) <= BETA_MAX and r["long_alpha"] > 0 and r["short_alpha"] > 0]
    winner = max(ok or rows, key=lambda k: rows[k]["net"])
    rep = {"rule": "max net | |beta|<=0.05 & both legs' alpha > 0", "qualified": ok, "winner": winner, "books": rows}
    (OUT / "race_d17.json").write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    r = main()
    for k, x in r["books"].items():
        print(f"{k:14s} net {x['net']*100:+.1f}%/yr vol {x['vol']*100:.1f} beta {x['beta']:+.3f} maxDD {x['maxdd']*100:.1f} "
              f"long a {x['long_alpha']*100:+.1f} (t {x['long_t']:+.1f}) short a {x['short_alpha']*100:+.1f} "
              f"(t {x['short_t']:+.1f}) costs {x['costs']*100:.1f}% gross {x['gross']:.2f} names {x['names']:.0f}")
    print("qualified:", r["qualified"], "| winner:", r["winner"])
