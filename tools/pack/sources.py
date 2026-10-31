# Where the pack reads the fund's outputs and inputs, and writes.

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The fund's run folder; FIAM_RUN points at another copy of it.
VFINAL = Path(os.environ.get("FIAM_RUN", ROOT / "out" / "vfinal"))
RUN = VFINAL / "bw_fresh_lag"
CACHE = VFINAL / "cache"
FORECAST = VFINAL / "forecast"
# The pack's output folder; FIAM_PACK writes it somewhere else.
OUT = Path(os.environ.get("FIAM_PACK", ROOT / "out" / "pack"))
DATA = OUT / "data"
# Public benchmarks in git: FRED's TB3MS and SP500.
BENCHMARKS = ROOT / "data" / "benchmarks"
# CRSP's S&P 500 and Fama-French daily, as the engine extracted them.
CRSP_MARKET = ROOT / "data" / "v4" / "extracts" / "crsp_market_daily.parquet"
FF_DAILY = ROOT / "data" / "v4" / "extracts" / "ff_daily.parquet"
# CRSP daily returns over the 17 crisis windows.
STRESS = ROOT / "cache" / "stress_daily.parquet"
# The organisers' panel, read only.
PANEL = ROOT / "data" / "organisers" / "chars_final_with_names.parquet"
# Yahoo monthly bars, local only: their terms bar sharing them.
MARKET = ROOT / "data" / "market"
YAHOO = {
    "SPY": "1e713c3c23f94ca00a2b226b3656be2a28b312873f5098c28a44b1a5721e4d8c",
    "AGG": "a8cf055d74a1036516789160e9fa4a9f2062cfd19cd2ad837fca3a480e72add7",
    "IEF": "c80a5b9a0540f920492f43516e2e5f0e49f22017d768c53e05128af5734d7bf8",
}


# A Yahoo bar file's path once its bytes match the recorded hash.
def yahoo_file(ticker: str) -> Path:
    path = MARKET / f"{ticker}.json"
    if not path.exists():
        raise SystemExit(f"No {path}: put the local Yahoo bar files there.")
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != YAHOO[ticker]:
        raise SystemExit(f"{path} has sha256 {got}, not the recorded {YAHOO[ticker]}.")
    return path
