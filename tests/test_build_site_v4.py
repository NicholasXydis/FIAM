# The site's headline source on small synthetic result files.

import csv
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import build_site as b

COMMIT = "abcdef123456"
SITE = Path(__file__).resolve().parents[1] / "site" / "src" / "data" / "fiam.json"
# The keys the headline mode fills, each checked against the bundle.
FILLED = (
    "book",
    "code",
    "window",
    "months",
    "headline",
    "years",
    "race",
    "beta",
    "stocks",
    "costs",
)
# The table's cells the tests read, in the formats the report writes.
CELLS = {
    1: ("Ending value (US$ bn)", "0.95", "1.05"),
    2: ("Cumulative return (%)", "-5.5", "6.1"),
    3: ("Annualised return (%)", "arithmetic -3.57, CAGR -3.80", "arithmetic 7.27, CAGR 7.52"),
    4: ("Annualised volatility (%)", "7.8", "0.56"),
    5: ("Alpha vs S&P 500 (%, s.e.)", "-6.25 (3.18)", "n/a"),
    6: ("Beta monthly (s.e.)", "-0.056 (0.041)", "n/a"),
    8: ("Sharpe ratio", "-0.8794", "undefined, constant excess"),
    9: ("IR vs T-bill + 4%, before costs", "-1.1904", "n/a"),
    10: ("Tracking error (%)", "7.775", "n/a"),
    11: ("Max drawdown (%)", "-29.26", "0.0"),
    14: ("Positions held", "avg 273.0, min 252, max 281", "n/a"),
    17: ("One-way turnover (%)", "with build 122, without 107; all trade days 122", "n/a"),
    21: ("Trading cost (% NAV a year)", "1.2844", "n/a"),
    22: ("Borrow cost (% NAV a year)", "0.4464", "n/a"),
    23: ("IR net of all costs", "-1.39 (0.44); at 100% gross IR -1.74, Sharpe -0.88", "n/a"),
}
# Each stock's ticker and name in the Arcana file, by PERMNO and date.
ARCANA = [
    ("2021-01-04", "OLD US Equity", 1, "Old Name Inc"),
    ("2021-06-01", "NEW US Equity", 1, "NEW NAME INC"),
    ("2021-01-04", "BRK/A US Equity", 2, "BERKSHIRE HATHAWAY INC"),
    ("2021-01-04", "", 3, ""),
]


# Every trading day from the endowment close to the end of March 2022.
def days() -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp("2020-12-31")]).append(
        pd.bdate_range("2021-01-04", "2022-03-31")
    )


# A daily book whose bill is higher on each month's first day.
def daily_frame() -> pd.DataFrame:
    index = days()
    i = np.arange(len(index))
    ret = np.where(i == 0, 0.0, 0.002 * np.sin(i))
    later = pd.Series(index.to_period("M")).duplicated().to_numpy()
    rf = np.where(later, 0.0001, 0.0003)
    return pd.DataFrame(
        {
            "nav": 1e9 * np.cumprod(1 + ret),
            "ret": ret,
            "rf": rf,
            "n_long": np.where(i == 0, 0, 100 + i % 3),
            "n_short": np.where(i == 0, 0, 150),
        },
        index=pd.Index(index, name="date"),
    )


# S&P 500 closes from before the run to after it.
def closes() -> pd.Series:
    index = pd.bdate_range("2020-11-02", "2022-04-29")
    i = np.arange(len(index))
    return pd.Series(4000 * np.cumprod(1 + 0.004 * np.cos(i * 0.7)), index=index)


# Two positions a month, mid month and the month's last day.
def positions(daily: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, month in daily.iloc[1:].groupby(daily.index[1:].to_period("M")):
        for date in (month.index[len(month) // 2], month.index[-1]):
            late = date == month.index[-1]
            out += [(date, 1, 2e7 if late else 1e6), (date, 2, -1e7), (date, 3, 5e6)]
    return pd.DataFrame(out, columns=["date", "permno", "value"])


# Writes a CSV of dict rows with the given columns.
def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, fieldnames=columns)
        out.writeheader()
        out.writerows(rows)


# The headline folder's five files, as the report writes them.
def write_folder(folder: Path) -> None:
    folder.mkdir(parents=True)
    cells = {n: CELLS.get(n, (f"row {n}", "0.0", "n/a")) for n in range(1, 24)}
    table = [
        dict(row=n, name=a, strategy=s, benchmark=bm, note="") for n, (a, s, bm) in cells.items()
    ]
    write_csv(
        folder / f"table_9_1_{COMMIT}.csv", ["row", "name", "strategy", "benchmark", "note"], table
    )
    write_csv(
        folder / f"vs_market_{COMMIT}.csv",
        ["measure", "fund", "sp500_price"],
        [
            dict(measure="Sharpe ratio", fund=-0.88, sp500_price=0.7),
            dict(measure=b.CORRELATION, fund=-0.0918, sp500_price=0.99),
        ],
    )
    daily = daily_frame()
    daily.to_parquet(folder / f"daily_7_{COMMIT}.parquet")
    positions(daily).to_parquet(folder / f"positions_7_{COMMIT}.parquet")
    columns = ["Date", "Ticker", "Weights", "Asset Class", "ISIN", "AUM", "Custom Tag"]
    own = [
        dict(Date=d, Ticker=t, Weights=0.01, PERMNO=p, Name=n)
        | {"Asset Class": "Equity", "ISIN": "", "AUM": 1e9, "Custom Tag": "long"}
        for d, t, p, n in ARCANA
    ]
    write_csv(
        folder / f"arcana_weights_monthly_{COMMIT}_own.csv", [*columns, "PERMNO", "Name"], own
    )


# A pick file in folder naming the headline folder, final or not.
def write_pick(folder: Path, headline: Path, final: bool) -> Path:
    pick = folder / f"pick_{COMMIT}.json"
    body = {"final": final, "headline": str(headline), "next": [] if final else ["report"]}
    pick.write_text(json.dumps(body), encoding="utf-8")
    return pick


# The bundled site data, its predicted betas cut to the synthetic run.
@pytest.fixture(scope="module")
def base() -> dict:
    if not SITE.exists():
        pytest.skip("no bundled site data")
    data = json.loads(SITE.read_text(encoding="utf-8"))
    months = len(b.fund_months(daily_frame()))
    return data | {"beta": data["beta"] | {"exante": data["beta"]["exante"][:months]}}


# The headline output from a synthetic folder, as the JSON holds it.
@pytest.fixture
def made(tmp_path, base) -> dict:
    write_folder(tmp_path / "revised")
    out = b.v4(base, tmp_path / "revised", COMMIT, closes())
    return json.loads(json.dumps(out, allow_nan=False))


# A pick that is not final is refused with a clear message.
def test_refuses_a_pick_that_is_not_final(tmp_path):
    pick = write_pick(tmp_path, tmp_path / "revised", final=False)
    with pytest.raises(SystemExit, match="not final.*report"):
        b.headline_folder(pick)


# A final pick gives its headline folder and the file suffix.
def test_final_pick_gives_folder_and_commit(tmp_path):
    pick = write_pick(tmp_path, tmp_path / "revised", final=True)
    assert b.headline_folder(pick) == (tmp_path / "revised", COMMIT)


# The newest pick is the one written last; none at all is refused.
def test_newest_pick(tmp_path):
    with pytest.raises(SystemExit, match="No pick file"):
        b.newest_pick(tmp_path)
    old, new = tmp_path / "pick_aaaaaaaaaaaa.json", tmp_path / "pick_bbbbbbbbbbbb.json"
    for path, when in ((new, 2_000_000_000), (old, 1_000_000_000)):
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (when, when))
    assert b.newest_pick(tmp_path) == new


# A folder missing any of the five files is refused by name.
def test_missing_file_is_refused(tmp_path):
    write_folder(tmp_path / "revised")
    (tmp_path / "revised" / f"vs_market_{COMMIT}.csv").unlink()
    with pytest.raises(SystemExit, match="vs_market"):
        b.v4_files(tmp_path / "revised", COMMIT)


# Each string cell gives the number the site reads.
def test_cells_parse():
    assert b.first(CELLS[23][1]) == -1.39
    assert b.numbers(CELLS[23][1]) == [-1.39, 0.44, 100.0, -1.74, -0.88]
    assert b.with_se(CELLS[5][1]) == (-6.25, 3.18)
    assert b.with_se(CELLS[6][1]) == (-0.056, 0.041)
    assert b.labelled(CELLS[3][1], "CAGR") == -3.80
    assert b.labelled(CELLS[3][1], "arithmetic") == -3.57
    assert b.labelled(CELLS[3][2], "arithmetic") == 7.27
    assert b.labelled(CELLS[14][1], "avg") == 273.0
    assert b.labelled(CELLS[17][1], "without") == 107.0


# Cells with no such number raise rather than guess.
def test_cells_refuse_what_is_not_there():
    with pytest.raises(ValueError):
        b.first("n/a")
    with pytest.raises(ValueError):
        b.with_se("-6.25")
    with pytest.raises(ValueError):
        b.labelled("avg 273.0", "CAGR")


# The hurdle is each month's first daily bill x 252 / 12, plus 4% / 12.
def test_hurdle_formula():
    m = b.fund_months(daily_frame())
    assert str(m.index[0]) == "2021-01"
    assert m["bill"].to_numpy() == pytest.approx(0.0003 * 252 / 12)
    assert m["hurdle"].to_numpy() == pytest.approx(0.0003 * 252 / 12 + 0.04 / 12)
    rf = pd.Series(
        [0.0002, 0.0009, 0.0004], index=pd.to_datetime(["2021-02-01", "2021-02-02", "2021-03-01"])
    )
    assert b.monthly_bill(rf).tolist() == pytest.approx([0.0002 * 21, 0.0004 * 21])


# The race compounds the fund, hurdle and S&P 500 month by month.
def test_race_compounds_each_month(made):
    daily, race = daily_frame(), made["race"]
    m = b.fund_months(daily)
    assert len(race["book"]) == len(made["months"]) + 1 == len(m) + 1
    assert race["book"][-1] == pytest.approx(daily["nav"].iloc[-1] / 1e9, abs=1e-4)
    assert race["hurdle"][-1] == pytest.approx((1 + m["hurdle"]).prod(), abs=1e-4)
    close = closes()
    end = close[close.index <= "2022-03-31"].iloc[-1] / close[close.index <= "2020-12-31"].iloc[-1]
    assert race["market"][-1] == pytest.approx(end, abs=1e-4)
    assert made["years"]["2022"]["months"] == 3
    year = made["years"]["2021"]
    assert year["active"] == pytest.approx(year["strategy"] - year["benchmark"], abs=2e-4)
    assert made["window"] == "2021-01 to 2022-03" and made["code"] == COMMIT


# The headline numbers are the table's rows, scaled to fractions.
def test_headline_reads_each_row(made):
    head = made["headline"]
    assert head["ir"] == -1.39
    assert head["ir_gross"] == -1.19
    assert head["sharpe"] == -0.879
    assert head["cagr"] == -0.038
    assert head["vol"] == 0.078
    assert head["alpha"] == -0.0625
    assert head["alpha_t"] == round(-6.25 / 3.18, 2)
    assert (head["beta"], head["beta_se"]) == (-0.056, 0.041)
    assert head["drawdown"] == -0.2926
    assert head["correlation"] == -0.092
    assert head["positions"] == 273.0
    assert head["turnover"] == round(1.07 / 12, 3)
    assert head["cumulative"] == -0.055
    assert head["net"] == round((-3.57 - 7.27) / 100 + 0.04, 4)
    m = b.fund_months(daily_frame())
    assert head["hit"] == round(float((m["ret"] > m["hurdle"]).mean()), 3)


# Costs come from rows 21 and 22; the ladder scales them by k.
def test_costs_from_rows_21_and_22(made):
    c = made["costs"]
    assert c["parts"] == dict(
        commission=0.0, spread=0.0, impact=0.01284, borrow=0.00446, financing=0.0
    )
    assert c["total"] == round(0.012844 + 0.004464, 5)
    assert c["gross"] == pytest.approx(c["net"] + c["total"], abs=1e-4)
    one = c["ladder"][0]
    assert one["multiple"] == 1.0 and one["ir"] == round(-0.1084 / 0.07775, 3)
    assert c["break_even_multiple"] == round(1 - 0.1084 / (0.012844 + 0.004464), 3)


# Holdings are each month's last date, named from the Arcana file.
def test_holdings_last_date_and_tickers(made):
    s = made["stocks"]
    assert s["ticker"] == ["NEW", "BRK/A", ""]
    assert s["name"] == ["New Name Inc", "Berkshire Hathaway Inc", ""]
    nav = daily_frame()["nav"]
    last = nav[nav.index <= "2022-03-31"].iloc[-1]
    assert s["book"][-1] == [
        0,
        round(2e7 / last * 1e5),
        1,
        round(-1e7 / last * 1e5),
        2,
        round(5e6 / last * 1e5),
    ]
    assert len(s["book"]) == len(made["months"])


# The rolling beta starts once a full window of days exists.
def test_rolling_beta_months(made):
    rolling = made["beta"]["rolling"]
    assert rolling and min(rolling) >= "2021-12"
    assert all(band > 0 for _, band in rolling.values())


# A run whose months differ from the predicted betas is refused.
def test_month_count_must_match(tmp_path, base):
    write_folder(tmp_path / "revised")
    short = base | {"beta": base["beta"] | {"exante": [0.0]}}
    with pytest.raises(SystemExit, match="exante"):
        b.v4(short, tmp_path / "revised", COMMIT, closes())


# A value's shape: dict keys, list element shapes and leaf types.
def shape(x):
    if isinstance(x, dict):
        # Dicts keyed by year or month compare their values' shapes only.
        if x and all(re.fullmatch(r"\d{4}(-\d{2})?", k) for k in x):
            return ("by date", frozenset(shape(v) for v in x.values()))
        return tuple(sorted((k, shape(v)) for k, v in x.items()))
    if isinstance(x, list):
        return ("list", frozenset(shape(v) for v in x))
    return type(x).__name__


# The filled keys have the bundled file's key names and value types.
def test_same_keys_and_types_as_the_site(made, base):
    assert set(made) == set(base)
    for key in FILLED:
        assert shape(made[key]) == shape(base[key]), key
    for key in set(base) - set(FILLED):
        assert made[key] == base[key], key
