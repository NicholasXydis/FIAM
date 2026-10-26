# Split-half reliability of the slope-averaged forecast: how much is estimation noise?
import numpy as np, pandas as pd
from fiam.v4b.forecast import data
inp = pd.read_parquet("fiam/v4b/out/elasso/rolling/ret/input/data.parquet")
inp["date"] = pd.to_datetime(inp["date"]); inp = inp[inp.date <= "2020-12-31"].reset_index(drop=True)
chars = [c for c in inp.columns if c not in ("date","permno","exchcd","me","ret")]
Z = inp[chars].fillna(0).to_numpy(); y = inp["ret"].to_numpy(); w0 = inp["me"].to_numpy()
q = inp.groupby("date")["ret"].rank(pct=True); tail = ((q > .9).astype(float) - (q <= .1).astype(float)).to_numpy()
dates = np.sort(inp.date.unique()); idx = {d: np.flatnonzero(inp.date.to_numpy() == d) for d in dates}
def slopes(yv):
    B = []
    for d in dates:
        i = idx[d]; w = w0[i] / w0[i].mean(); z = Z[i]; yy = yv[i]
        zm = (w[:, None] * z).sum(0) / w.sum(); ym = (w * yy).sum() / w.sum(); zc = z - zm
        B.append((w[:, None] * zc * (yy - ym)[:, None]).sum(0) / np.maximum((w[:, None] * zc**2).sum(0), 1e-12))
    return np.array(B)
big = inp["me"].to_numpy() >= 500
for name, yv in (("ret", y), ("tail", tail)):
    B = slopes(yv); rel = []; tt = None
    for k, d in enumerate(dates):
        if d < pd.Timestamp("2017-01-31"): continue
        h = B[:k]  # slopes realised before forecasting row d
        a, b = h[0::2].mean(0), h[1::2].mean(0)
        i = idx[d][big[idx[d]]]
        fa, fb = Z[i] @ a, Z[i] @ b
        r = pd.Series(fa).corr(pd.Series(fb), method="spearman"); rel.append((k, r))
        tt = h.mean(0) / (h.std(0, ddof=1) / np.sqrt(len(h)))
    rel = pd.DataFrame(rel, columns=["H", "r_half"])
    rel["r_full"] = 2 * rel.r_half / (1 + rel.r_half)
    print(name, "history 23..70 months: split-half r", rel.r_half.round(3).iloc[[0, len(rel)//2, -1]].tolist(),
          "-> full-sample reliability", rel.r_full.round(3).iloc[[0, len(rel)//2, -1]].tolist())
    r70 = rel.r_full.iloc[-1]
    for n_m in (120, 240, 420):
        f = n_m / 70; print(f"   Spearman-Brown at {n_m} months: {f*r70/(1+(f-1)*r70):.3f}")
    print("   slope means at 70 months with |t|>2:", int((np.abs(tt) > 2).sum()), "of", len(tt), "; |t|>1:", int((np.abs(tt) > 1).sum()))
