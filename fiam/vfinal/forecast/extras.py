# el_plus's three extras: SYY-10, the SUE forecast, short interest.

import pandas as pd

from fiam.vfinal import config, sources, unseal
from fiam.vfinal.forecast import grid, inputs
from fiam.vfinal.signals import short_interest

# The SUE cell the locked models chose for the panel set.
STOCKS = "panel"
COLS = ["syy", "sue_forecast", "short_ratio"]


# The three extras for every panel row from 2015-01 to 2026-07.
def build(target) -> pd.DataFrame:
    t = grid.Table(sources.characteristics())
    cell = unseal.choices()["members"]["sue"][STOCKS]["chosen"]
    sue = grid.sue_column(t, STOCKS, cell["leaves"], cell["children"])
    x = t.x.loc[t.feats[STOCKS].index, ["permno", "eom", "syy_raw"]]
    out = x.assign(sue_forecast=sue.reindex(x.index)).rename(columns={"syy_raw": "syy"})
    eoms = sorted(out["eom"].unique())
    si = short_interest.build(eoms).rename(columns={"value": "short_ratio"})
    out = out.merge(si[["permno", "eom", "short_ratio"]], on=["permno", "eom"], how="left")
    out = out[["permno", "eom", "syy", "sue_forecast", "short_ratio"]]
    out.to_parquet(target, index=False)
    return out


# One file's rows with the extras, standardised within each month.
def joined(f: pd.DataFrame, extras: pd.DataFrame, fill: bool) -> pd.DataFrame:
    f = f.copy()
    f["eom"] = (pd.to_datetime(f["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    f = f.merge(extras, on=["permno", "eom"], how="left", validate="many_to_one")
    for c in COLS:
        z = inputs.ghz(f, c)
        f[c] = z.fillna(0.0) if fill else z
    return f.drop(columns="eom")


# The el_plus training and forecast rows from the base ones.
def plus_rows(base, plus, extras_file) -> None:
    plus.mkdir(parents=True, exist_ok=True)
    e = pd.read_parquet(extras_file)
    e["eom"] = pd.to_datetime(e["eom"]).astype("datetime64[ns]")
    e = e.drop_duplicates(["permno", "eom"])
    tr = joined(pd.read_parquet(base / "input.parquet"), e, fill=False)
    tr.to_parquet(plus / "input.parquet", index=False)
    ft = joined(pd.read_parquet(base / "features.parquet"), e, fill=True)
    ft.to_parquet(plus / "features.parquet", index=False)


# The default extras file under this run's cache.
def target():
    return config.CACHE / "el_plus_extras.parquet"
