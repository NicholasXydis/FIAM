# The `global` switch's data (finals_global.md): a finals panel of any countries as a bundle in our
# layout, read through FIAM_DATA_DIR like the US bundle, with its own market and country weights.
# uv run python -m fiam.world build <finals folder or file> [columns.json] | fake

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from fiam import benchmarks, data, layers, paths

WORLD = Path("data") / "world"
FAKE = Path("data") / "world_fake"
HERE = Path(__file__).parent
# Our bundle's columns and types, so a bundle can be built on a machine without the US data.
SCHEMA = json.loads((HERE / "world_schema.json").read_text(encoding="utf-8"))
TEMPLATE = HERE / "world_columns.json"
# Ids for stocks without a PERMNO start here, above every PERMNO, so the two never meet.
FIRST_ID = 100_000_000
# Columns in money, converted to dollars with the month-end rate when a currency is named.
MONEY = ("prc", "me", "market_equity", "dolvol_126d")
# Federal Reserve H.10 series: units per dollar (dex..us), or dollars per unit (dexus..).
FED = {
    "CAD": "dexcaus", "JPY": "dexjpus", "EUR": "dexuseu", "GBP": "dexusuk", "AUD": "dexusal",
    "NZD": "dexusnz", "CHF": "dexszus", "CNY": "dexchus", "HKD": "dexhkus", "INR": "dexinus",
    "KRW": "dexkous", "MXN": "dexmxus", "BRL": "dexbzus", "DKK": "dexdnus", "NOK": "dexnous",
    "SEK": "dexsdus", "SGD": "dexsius", "ZAR": "dexsfus", "TWD": "dextaus", "THB": "dexthus",
    "MYR": "dexmaus", "LKR": "dexslus",
}  # fmt: skip
TYPES = {
    "double": pa.float64(), "int8": pa.int8(), "int16": pa.int16(), "int32": pa.int32(),
    "int64": pa.int64(), "bool": pa.bool_(), "large_string": pa.large_string(),
    "timestamp[ms]": pa.timestamp("ms"), "date32[day]": pa.date32(),
    "list<element: string>": pa.list_(pa.string()),
}  # fmt: skip


# The column map: the template, then the day's own file (given, or columns.json beside the data).
def spec(source: Path, columns: Path | None = None) -> dict:
    out = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    beside = source / "columns.json" if source.is_dir() else source.with_name("columns.json")
    chosen = columns or (beside if beside.exists() else None)
    if chosen:
        out |= json.loads(Path(chosen).read_text(encoding="utf-8"))
    return out


# Every panel file in the folder that has the map's id and month columns, as one frame.
def read_panel(source: Path, m: dict) -> pd.DataFrame:
    found = (
        [source] if source.is_file() else sorted({p for g in m["files"] for p in source.glob(g)})
    )
    frames = []
    for path in found:
        frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        frame = frame.rename(columns=m["rename"])
        if {m["id"], m["eom"]} <= set(frame.columns):
            frames.append(frame)
        else:
            print(f"skipped {path.name}: no {m['id']} and {m['eom']} columns")
    if not frames:
        raise SystemExit(
            f"{source}: no panel with {m['id']} and {m['eom']}; name them in columns.json"
        )
    frame = pd.concat(frames, ignore_index=True)
    eom = pd.to_datetime(frame[m["eom"]], errors="coerce") + pd.offsets.MonthEnd(0)
    keep = eom >= pd.Timestamp(m["first"])
    if m.get("countries") and m["country"] in frame:
        keep &= frame[m["country"]].astype("string").str.upper().isin(m["countries"])
    return frame[keep.fillna(False)].assign(**{m["eom"]: eom[keep.fillna(False)]})


# A US stock's PERMNO where the panel gives one; every other stock FIRST_ID plus its id's rank.
def ids(frame: pd.DataFrame, m: dict) -> pd.Series:
    rank = pd.factorize(frame[m["id"]].astype("string"), sort=True)[0] + FIRST_ID
    out = pd.Series(rank, index=frame.index, dtype="int64")
    if m.get("permno") in frame:
        permno = pd.to_numeric(frame[m["permno"]], errors="coerce")
        us = frame["country"].eq("USA") & permno.between(1, FIRST_ID - 1)
        out = out.where(~us, permno).astype("int64")
    return out


# The Federal Reserve's daily rates: the pinned FRED file, else the WRDS layer (to Feb 2025).
def fed_rates() -> pd.DataFrame | None:
    pinned = sorted(benchmarks.BENCH.glob("fx_daily_*.csv"))
    if pinned:
        parts = [pd.read_csv(p, index_col="observation_date", parse_dates=True) for p in pinned]
        frame = pd.concat(parts, axis=1).apply(pd.to_numeric, errors="coerce")
        return frame.rename(columns=str.lower)
    layer = layers.load("market/fx_daily")
    return None if layer is None else layer.set_index(pd.to_datetime(layer.pop("date")))


# Dollars per unit of each currency at each month end: the map's fx_file, else the Fed's rates.
def usd_per_unit(m: dict, currencies: list, months: pd.DatetimeIndex) -> pd.DataFrame:
    if m.get("fx_file"):
        table = pd.read_csv(m["fx_file"], parse_dates=["date"])
        wide = table.pivot_table(index="date", columns="currency", values="usd_per_unit")
    else:
        fed = fed_rates()
        if fed is None:
            raise SystemExit("prices in other currencies need data/benchmarks/fx_daily.csv")
        wide = {}
        for currency in currencies:
            series = FED.get(currency)
            if series not in fed:
                raise SystemExit(f"no exchange rate for {currency}: add an fx_file to columns.json")
            rate = fed[series].astype(float)
            wide[currency] = rate if series.startswith("dexus") else 1 / rate
        wide = pd.DataFrame(wide)
    found = wide.resample("ME").last().reindex(months)
    gaps = [c for c in currencies if c not in found or found[c].isna().any()]
    if gaps:
        raise SystemExit(f"no month-end rate for {gaps} in some months: add an fx_file")
    return found


# Prices, sizes and next month's return in dollars for rows the map says are in another currency.
def in_dollars(frame: pd.DataFrame, m: dict) -> tuple[pd.DataFrame, list]:
    column = m.get("currency")
    if not column or column not in frame:
        return frame, []
    currency = frame[column].astype("string").str.upper().fillna("USD")
    foreign = sorted(set(currency) - {"USD"})
    if not foreign:
        return frame, []
    months = pd.DatetimeIndex(sorted(frame["eom"].unique()))
    rates = usd_per_unit(m, foreign, months.append(months[-1:] + pd.offsets.MonthEnd(1)))
    rates["USD"] = 1.0
    now = rates.stack().rename("now")
    ahead = rates.shift(-1).stack().rename("ahead")
    key = pd.MultiIndex.from_arrays([frame["eom"], currency])
    now, ahead = now.reindex(key).to_numpy(), ahead.reindex(key).to_numpy()
    out = frame.copy()
    for col in MONEY:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce") * now
    out["ret_exc_lead1m"] = (1 + out["ret_exc_lead1m"]) * ahead / now - 1
    return out, foreign


# One column cast to our bundle's type; a column the panel lacks is left empty.
def cast(frame: pd.DataFrame, name: str, kind: str) -> pa.Array:
    target = TYPES[kind]
    if name not in frame:
        return pa.nulls(len(frame), target)
    s = frame[name]
    if kind.startswith(("int", "double")):
        s = pd.to_numeric(s, errors="coerce")
        s = s.astype("Int64") if kind.startswith("int") else s.astype("float64")
    elif kind.startswith(("timestamp", "date")):
        s = pd.to_datetime(s, errors="coerce")
        s = s.dt.date if kind.startswith("date") else s
    elif kind == "bool":
        s = s.astype("boolean")
    else:
        s = s.astype("string")
    return pa.array(s, from_pandas=True).cast(target, safe=False)


# Our layout from any table: every column of the schema, in order, plus any named extras.
def arrow(frame: pd.DataFrame, schema: dict) -> pa.Table:
    return pa.table({name: cast(frame, name, kind) for name, kind in schema.items()})


# The finals panel as a bundle in our layout under `out`, with a manifest of what it holds.
def build(source: Path, out: Path = WORLD, columns: Path | None = None) -> dict:
    m = spec(source, columns)
    frame = read_panel(source, m)
    named = {m["eom"]: "eom", m["country"]: "country", m["return"]: "ret_exc_lead1m"}
    absent = [k for k in named if k not in frame]
    if absent:
        raise SystemExit(f"the panel has no {absent}: name them in columns.json")
    frame = frame.rename(columns=named)
    frame["eom"] = frame["eom"].astype("datetime64[s]")
    frame["country"] = frame["country"].astype("string").str.upper()
    frame["permno"] = ids(frame, m)
    rows = len(frame)
    frame = frame.drop_duplicates(["permno", "eom"], keep="last")
    frame, converted = in_dollars(frame, m)
    out.mkdir(parents=True, exist_ok=True)
    features = {k: v for k, v in SCHEMA["features"].items() if k != data.TARGET}
    pq.write_table(arrow(frame, features | {"country": "large_string"}), out / data.FEATURES.name)
    labels = frame.assign(
        holding_month=(frame["eom"] + pd.offsets.MonthBegin(1)).dt.normalize(),
        next_month_excess_return=frame["ret_exc_lead1m"],
        source_crsp=0,
    )
    pq.write_table(arrow(labels, SCHEMA["labels"]), out / data.LABELS.name)
    pq.write_table(arrow(frame.iloc[:0], SCHEMA["filings"]), out / data.FILINGS.name)
    counts = frame.groupby("country").size().sort_values(ascending=False)
    report = dict(
        schema_version=1,
        what="A finals panel in our layout (fiam.world, finals_global.md)",
        organizer_characteristics=SCHEMA["organizer_characteristics"],
        world=dict(
            source=str(source),
            columns=m,
            rows=rows,
            duplicates_dropped=rows - len(frame),
            months=[f"{frame['eom'].min():%Y-%m}", f"{frame['eom'].max():%Y-%m}"],
            countries={str(k): int(v) for k, v in counts.items()},
            converted_to_usd=converted,
            missing_columns=sorted(set(features) - set(frame.columns)),
        ),
    )
    paths.write_json(out / data.MANIFEST.name, report, rounded=False, end="\n")
    return report["world"] | dict(missing_columns=len(report["world"]["missing_columns"]))


# The rehearsal's bundle (finals_global.md): our US panel, a stock "CAN" when its PERMNO ends in
# 0, 1 or 2. Mechanics only: its returns are never evidence.
def fake(out: Path = FAKE) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    features = pq.read_table(data.FEATURES)
    permno = features.column("permno").to_numpy()
    country = np.where(permno % 10 <= 2, "CAN", "USA")
    features = features.append_column("country", pa.array(country, pa.large_string()))
    pq.write_table(features, out / data.FEATURES.name)
    shutil.copy2(data.LABELS, out / data.LABELS.name)
    pq.write_table(pq.read_schema(data.FILINGS).empty_table(), out / data.FILINGS.name)
    report = data.manifest() | dict(world=dict(fake=True, rule="PERMNO ending 0, 1 or 2 is CAN"))
    paths.write_json(out / data.MANIFEST.name, report, rounded=False, end="\n")
    return dict(rows=len(country), can=int((country == "CAN").sum()))


# The panel's own market: each month's value-weighted next-month excess return in the given
# countries, keyed on the holding month as the book's returns are.
def market(folder: Path, countries: tuple) -> pd.Series:
    names = data.read(folder / data.FEATURES.name, ["permno", "eom", "me", "country"])
    paid = data.read(folder / data.LABELS.name, [*data.KEYS, "next_month_excess_return"])
    both = names[names["country"].isin(countries)].merge(paid, on=data.KEYS).dropna()
    both = both[both["me"] > 0]
    weighted = (both["me"] * both["next_month_excess_return"]).groupby(both["eom"]).sum()
    vw = weighted / both.groupby("eom")["me"].sum()
    vw.index = (vw.index + pd.offsets.MonthBegin(1)).normalize()
    return vw.rename("world")


# Each month's share of the book's gross in each country.
def country_weights(held: pd.DataFrame, folder: Path) -> pd.DataFrame:
    where = data.read(folder / data.FEATURES.name, ["permno", "eom", "country"])
    held = held.assign(eom=pd.to_datetime(held["eom"]).astype("datetime64[s]"))
    joined = held.merge(where, on=data.KEYS, how="left").fillna({"country": "unknown"})
    gross = joined.assign(gross=joined["weight"].abs()).pivot_table(
        index="eom", columns="country", values="gross", aggfunc="sum", fill_value=0.0
    )
    return gross.div(gross.sum(axis=1), axis=0)


def main(args: list[str]) -> None:
    if args[:1] == ["fake"]:
        print(json.dumps(fake(), indent=1))
    elif args[:1] == ["build"] and len(args) > 1:
        chosen = Path(args[2]) if len(args) > 2 else None
        print(json.dumps(build(Path(args[1]), columns=chosen), indent=1, default=str))
    else:
        raise SystemExit("uv run python -m fiam.world build <finals folder or file> [columns.json]")


if __name__ == "__main__":
    main(sys.argv[1:])
