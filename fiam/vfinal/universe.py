# The trading universe at each formation.

import pandas as pd

from fiam.vfinal import data

# New positions need $600m; held ones keep going to $500m.
ENTRY_MUSD, HOLD_MUSD = 600.0, 500.0
# The traded price floor, on the panel's price, never the dsf's.
MIN_PRICE = 5.0


# Who may be bought, shorted or kept at one month-end formation.
def members(eom, held_long=(), held_short=()) -> pd.DataFrame:
    day, eom = pd.Timestamp(eom), pd.Timestamp(eom) + pd.offsets.MonthEnd(0)
    # Only a month end or its last session: a later row is never read.
    if data.eom_session([day]).iloc[0] != data.eom_session([eom]).iloc[0]:
        raise ValueError(f"{day:%Y-%m-%d} is not a month-end formation")
    rows = data.table("panel", ["me", "prc"], where={"eom": (eom, eom)})
    last = data.eom_session([eom]).iloc[0]
    data.assert_public_by(rows["first_close"], last, "universe panel rows")
    # A stock trades on T, the month's last session, or it is out.
    day = data.table("dsf", ["ret"], where={"date": (last, last)})
    data.assert_public_by(day["first_close"], last, "universe dsf rows")
    traded = set(day.loc[day["ret"].notna(), "permno"])
    rows = rows.assign(
        session=last,
        traded_on_t=rows["permno"].isin(traded),
        price_ok=rows["prc"].abs() >= MIN_PRICE,
    )
    ok = rows["traded_on_t"] & rows["price_ok"]
    big, kept = rows["me"] >= ENTRY_MUSD, rows["me"] >= HOLD_MUSD
    rows["new_long"] = ok & big
    rows["new_short"] = ok & big
    # A held name below $500m leaves at this formation.
    rows["keep_long"] = ok & kept & rows["permno"].isin(set(held_long))
    rows["keep_short"] = ok & kept & rows["permno"].isin(set(held_short))
    rows["eligible"] = rows["new_long"] | rows["keep_long"] | rows["keep_short"]
    cols = ["permno", "eom", "session", "me", "prc", "traded_on_t", "price_ok"]
    return rows[[*cols, "new_long", "new_short", "keep_long", "keep_short", "eligible"]]


# Counts of what each rule removed, for the card and the audit.
def dropped(eoms) -> pd.DataFrame:
    rows = []
    for eom in eoms:
        m = members(eom)
        big = m["me"] >= ENTRY_MUSD
        rows.append(
            {
                "eom": pd.Timestamp(eom) + pd.offsets.MonthEnd(0),
                "big": int(big.sum()),
                "no_trade_on_t": int((big & ~m["traded_on_t"]).sum()),
                "under_5_dollars": int((big & m["traded_on_t"] & ~m["price_ok"]).sum()),
                "eligible_new": int(m["new_long"].sum()),
            }
        )
    return pd.DataFrame(rows)
