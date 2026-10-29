# The forecast files in build order, under out/vfinal/forecast.

import pandas as pd

from fiam.vfinal import config
from fiam.vfinal.forecast import extras, inputs, midmonth, pool, regime


# The base and el_plus work folders.
def folders():
    return config.FORECAST / "base", config.FORECAST / "plus"


# The training rows and forecast rows, written once.
def base_inputs() -> dict:
    base, _ = folders()
    base.mkdir(parents=True, exist_ok=True)
    tr = inputs.frame("resrank", inputs.CUT)
    tr.to_parquet(base / "input.parquet", index=False)
    f = inputs.features(pd.Timestamp(config.FEATURES_FROM), pd.Timestamp(config.LAST_EOM))
    f.to_parquet(base / "features.parquet", index=False)
    return {"input": list(tr.shape), "features": list(f.shape)}


# The refit blocks as his forecastElasso_raw, each eom its own refit.
def assemble(work, ordered: bool) -> pd.DataFrame:
    parts = sorted((work / "refits_wf").glob("forecast_*.parquet"))
    raw = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    if ordered:
        raw = raw.sort_values(["date", "permno"], ignore_index=True)
    assert not raw.duplicated(["date", "permno"]).any()
    eom = pd.to_datetime(raw["date"]) - pd.offsets.MonthEnd(1)
    assert (eom == pd.to_datetime(raw["refit"])).all(), "formation eom must equal its refit"
    return raw


# The base MaInf's monthly IC, the market state and regime rho.
def rho() -> dict:
    base, _ = folders()
    raw = assemble(base, ordered=True)
    raw.to_parquet(base / "forecastElasso_raw.parquet", index=False)
    ic = regime.monthly_ic(raw)
    state = regime.market_state([pd.Timestamp(e) for e in ic.index])
    r = regime.rho_series(ic, state)
    ic.rename("ic").rename_axis("eom").reset_index().to_parquet(base / "ic.parquet", index=False)
    r.reset_index().to_parquet(base / "rho.parquet", index=False)
    state = state.reset_index(names="eom").astype({"corr_share": float, "hml12": float})
    state.to_parquet(base / "state.parquet", index=False)
    return {"months": len(r), "rho_mean": float(r["rho"].mean())}


# The base forecast with its rho, for the proof.
def base_forecast() -> pd.DataFrame:
    base, _ = folders()
    raw = pd.read_parquet(base / "forecastElasso_raw.parquet",
                          columns=["date", "permno", "MaInf"])  # fmt: skip
    r = pd.read_parquet(base / "rho.parquet")[["eom", "rho"]]
    eom = (pd.to_datetime(raw["date"]) - pd.offsets.MonthEnd(1)).astype("datetime64[ns]")
    f = pd.DataFrame({"permno": raw["permno"].astype("int64"), "eom": eom,
                      "mainf": raw["MaInf"].astype("float64")})  # fmt: skip
    r["eom"] = pd.to_datetime(r["eom"]).astype("datetime64[ns]")
    f = f.merge(r, on="eom", how="left", validate="many_to_one")
    assert f["rho"].notna().all(), "a formation without rho"
    g = f.groupby("eom")["mainf"]
    f["z"] = (f["mainf"] - g.transform("mean")) / g.transform("std") * f["rho"]
    f = f.sort_values(["eom", "permno"], ignore_index=True)
    f.to_parquet(base / "elasso_rho.parquet", index=False)
    return f


# The el_plus rows: the base rows with the three extras joined.
def plus_inputs() -> None:
    base, plus = folders()
    extras.build(extras.target())
    extras.plus_rows(base, plus, extras.target())


# el_plus's MaInf times the base rho, z-scored per formation.
def plus_forecast() -> pd.DataFrame:
    base, plus = folders()
    raw = assemble(plus, ordered=False)
    raw = raw.assign(eom=(pd.to_datetime(raw["date"]) - pd.offsets.MonthEnd(1))
                     .astype("datetime64[ns]"))  # fmt: skip
    r = pd.read_parquet(base / "rho.parquet")[["eom", "rho"]]
    r["eom"] = pd.to_datetime(r["eom"]).astype("datetime64[ns]")
    f = raw[["permno", "eom", "MaInf"]].rename(columns={"MaInf": "mainf"})
    f = f.merge(r, on="eom", how="left", validate="many_to_one")
    assert f["rho"].notna().all()
    g = f.groupby("eom")["mainf"]
    f["z"] = (f["mainf"] - g.transform("mean")) / g.transform("std") * f["rho"]
    f = f.sort_values(["eom", "permno"], ignore_index=True)
    f.to_parquet(config.FORECAST / "elasso_rho.parquet", index=False)
    return f


# The mid-month raw inputs, then el_plus's mid-month forecasts.
def mid_month(rets: pd.DataFrame, mids: dict) -> pd.DataFrame:
    base, plus = folders()
    target = config.CACHE / "mid_month_raw.parquet"
    midmonth.raw(rets, mids).to_parquet(target, index=False)
    feats = pd.read_parquet(plus / "features.parquet")
    feats["date"] = pd.to_datetime(feats["date"]).astype("datetime64[ns]")
    r = pd.read_parquet(base / "rho.parquet")[["eom", "rho"]]
    r = r.assign(eom=pd.to_datetime(r["eom"]).astype("datetime64[ns]")).set_index("eom")["rho"]
    got = midmonth.score(pd.read_parquet(target), feats, plus / "refits_wf", r)
    got.to_parquet(config.FORECAST / "mid_month.parquet", index=False)
    return got


# Both walk-forwards' refits over the worker processes.
def walkforward(which: str) -> dict:
    base, plus = folders()
    return pool.run(base if which == "base" else plus)
