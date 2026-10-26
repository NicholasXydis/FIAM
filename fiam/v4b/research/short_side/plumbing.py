# Plumbing audit of the rolling E-LASSO input/output against HHRZ §2 / FM appendix.
import numpy as np
import pandas as pd

from fiam.v4b.forecast import data

B = "fiam/v4b/out/elasso/rolling"
inp = pd.read_parquet(f"{B}/ret/input/data.parquet")
inp["date"] = pd.to_datetime(inp["date"])
chars = [c for c in inp.columns if c not in ("date", "permno", "exchcd", "me", "ret")]
print("1. input rows", len(inp), "dates", inp.date.min().date(), inp.date.max().date(), "chars", len(chars),
      "names/month median", int(inp.groupby("date").size().median()))

# Timing: the row dated d must carry month-d return and chars/me at eom d-1.
pan = pd.read_parquet(data.PANEL, columns=["permno", "eom", "ret", "ret_exc", "ret_exc_lead1m", "me", "ivol_capm_252d"])
pan["eom"] = pd.to_datetime(pan["eom"]).astype("datetime64[ns]")
pan = pan.rename(columns={"ret": "ret_panel"})
x = inp[["date", "permno", "ret", "me", "ivol_capm_252d"]].copy()
x["eom_prev"] = x["date"] - pd.offsets.MonthEnd(1)
m = x.merge(pan.rename(columns={"eom": "eom_prev", "me": "me_prev", "ivol_capm_252d": "iv_prev"}), on=["permno", "eom_prev"], how="left")
nxt = pan[["permno", "eom", "ret_exc"]].rename(columns={"eom": "date", "ret_exc": "ret_exc_month_d"})
m = m.merge(nxt, on=["permno", "date"], how="left")
print("2. timing: |input ret - panel ret_exc_lead1m(eom d-1)| max", float((m["ret"] - m["ret_exc_lead1m"]).abs().max()),
      "; corr(input ret, panel ret_exc of month d)", round(m[["ret", "ret_exc_month_d"]].corr().iloc[0, 1], 6),
      "; max |diff|", float((m["ret"] - m["ret_exc_month_d"]).abs().max()))
print("3. weight me == panel me at eom d-1:", float((m["me"] - m["me_prev"]).abs().max()))
# The ghz transform was applied to the eom d-1 cross-section (z of iv_prev within month).
zz = m.groupby("date")["iv_prev"].transform(lambda s: (s.clip(s.quantile(.01), s.quantile(.99)) - s.clip(s.quantile(.01), s.quantile(.99)).mean()) / s.clip(s.quantile(.01), s.quantile(.99)).std())
print("4. ghz(ivol at eom d-1) vs input column: max |diff| where present", float((zz - m["ivol_capm_252d"]).abs()[m["iv_prev"].notna()].max()))
g = inp.groupby("date")[chars]
mu, sd = g.mean().abs().max().max(), g.std()
print("5. per-month char mean max |.|", round(float(mu), 4), "; sd range", round(float(sd.min().min()), 3), round(float(sd.max().max()), 3))
na_months = inp.groupby("date")[chars].apply(lambda d: d.isna().any()).sum()
print("6. chars dropped by R (any NA in month) - months affected:", na_months[na_months > 0].to_dict())
zero_share = (inp[chars] == 0).mean().sort_values(ascending=False)
print("7. share of filled (zero) values, top 8:", zero_share.head(8).round(3).to_dict())

# Output alignment.
fe = pd.read_parquet(f"{B}/ret/run/forecastElasso.parquet")
fe["date"] = pd.to_datetime(fe["date"])
j = fe.merge(inp[["date", "permno", "ret"]], on=["date", "permno"], suffixes=("_fc", "_in"))
print("8. forecast rows", len(fe), "first date", fe.date.min().date(), "; forecast 'ret' == 100*input ret:",
      float((j["ret_fc"] - 100 * j["ret_in"]).abs().max()), "; rows matched", len(j), "of", len(fe))
months_before = inp.date.drop_duplicates().sort_values()
first = fe.date.min()
print("   months of slope history behind the first forecast:", int((months_before < first).sum()),
      "; behind 2016-12 formation (date 2017-01):", int((months_before < pd.Timestamp("2017-01-31")).sum()),
      "; behind 2020-11 formation:", int((months_before < pd.Timestamp("2020-12-31")).sum()),
      "; paper: >=120 (data 1980:01, OOS 1990:01)")
