# Any v2 run as the committee pack in out/finals/<run>/ (finals.md).

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

from fiam import book as P
from fiam import paths

ROOT = Path("out") / "finals"


# The run's files in the submission's shape, returning their folder.
def write(run: Path) -> Path:
    target = ROOT / run.parent.name
    folder = target / "submission"
    (folder / "exhibits").mkdir(parents=True, exist_ok=True)
    # The pack reads the committed cost and hedge files in its submission/.
    (folder / "models").mkdir(exist_ok=True)
    for name in ("book_inputs.parquet", "borrow.parquet", "spreads.json"):
        if not (folder / "models" / name).exists():
            shutil.copy2(Path("submission") / "models" / name, folder / "models" / name)
    book = pd.read_csv(run / "returns.csv", parse_dates=["holding_month", "forecast_eom"])
    book = book.set_index("holding_month")
    held = pd.read_parquet(run / "holdings.parquet")
    held = held.assign(
        PERMNO=held["permno"],
        eom=pd.to_datetime(held["eom"]),
        Date=(pd.to_datetime(held["eom"]) + pd.offsets.MonthBegin(1)).dt.normalize(),
        WEIGHT=held["weight"] * 100,
        TICKER=pd.NA,
        COMPANY_NAME=pd.NA,
    )
    filled = P.fill_labels(held, P.load_panel())
    out = filled[["Date", "PERMNO", "TICKER", "COMPANY_NAME", "WEIGHT"]]
    out = out.rename(columns={"COMPANY_NAME": "COMPANY NAME"}).round({"WEIGHT": 6})
    out.to_csv(folder / "holdings.csv", index=False, lineterminator="\n")
    rf = P.benchmarks().set_index("month")[["rf"]]
    total = book.join(rf, how="left")
    total["portfolio_total_return"] = total["rf"] + total["net"]
    total["active_return"] = total["portfolio_total_return"] - (total["rf"] + 0.04 / 12)
    total.reset_index().to_csv(folder / "returns.csv", index=False, lineterminator="\n")
    paths.write_json(folder / "metrics.json", P.performance(book), rounded=False, default=str)
    return target


# The pack and performance charts as for v1, but in the finals folder.
def main(run: str) -> None:
    target = write(Path(run))
    env = os.environ | {"FIAM_OUT": str(target)}
    for step in ("fiam.exhibits.pack", "fiam.report.charts"):
        subprocess.run([sys.executable, "-m", step], env=env, check=True)
    print(f"wrote {target}/submission: holdings, returns, metrics, pack and charts")


if __name__ == "__main__":
    main(sys.argv[1])
