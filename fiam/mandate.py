# A rule set as a file: v1's limits by default, a finals mandate when one is given, checked first.

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from fiam import book as P

TEMPLATES = Path("mandates")
# GICS sectors by their two-digit code, so a mandate may name a sector either way.
SECTORS = {
    "energy": "10", "materials": "15", "industrials": "20", "consumer discretionary": "25",
    "consumer staples": "30", "health care": "35", "financials": "40",
    "information technology": "45", "communication services": "50", "utilities": "55",
    "real estate": "60",
}  # fmt: skip


# Every rule the optimizer reads. None turns a band off: a long-only book is never beta neutral.
@dataclass(frozen=True)
class Mandate:
    name: str = "v1"
    gross: float = P.LIMITS["gross"]
    net: float = 0.0
    name_cap: float = P.LIMITS["name"]
    sector: float | None = P.LIMITS["sector"]
    beta: float | None = P.LIMITS["beta"]
    risk: float | None = P.LIMITS["risk"]
    pool: int = P.LIMITS["pool"]
    ridge: float = P.LIMITS["ridge"]
    names_min: int = 100
    names_max: int = 500
    long_only: bool = False
    countries: tuple = ("USA",)
    country_cap: float | None = None
    vol_budget: float | None = None
    # Final v3's realized volatility a year (v2_amendment_3.md); None keeps its 10%.
    vol_target: float | None = None
    # The widest net exposure the rules allow either way; the book still targets net above.
    net_band: float | None = None
    # The most one-way turnover a month, as a share of NAV; the first month's build is exempt.
    turnover: float | None = None
    # The yearly spread over the T-bill the book is judged against; None keeps the brief's 4%.
    hurdle: float | None = None
    # Who may enter at all: the smallest market cap in $ millions, and GICS sectors left out.
    min_market_cap: float | None = None
    exclude_sectors: tuple = ()
    strategy_text: str = ""

    # Long and short dollars per dollar of NAV, from gross and net.
    @property
    def sides(self) -> tuple[float, float]:
        return (self.gross + self.net) / 2, (self.gross - self.net) / 2


V1 = Mandate()


# A mandate file; a key the optimizer does not know stops the run instead of being ignored.
def load(path: str | Path) -> Mandate:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = sorted(set(raw) - {f.name for f in fields(Mandate)})
    if unknown:
        raise ValueError(f"{path}: unknown keys {unknown}")
    if "countries" in raw:
        raw["countries"] = tuple(raw["countries"])
    if raw.get("exclude_sectors"):
        named = [
            SECTORS.get(str(s).strip().lower(), str(s).strip()) for s in raw["exclude_sectors"]
        ]
        raw["exclude_sectors"] = tuple(named)
    return Mandate(**raw)


# Rules that cannot all hold, in words, before any solver is asked to try.
def check(m: Mandate) -> list[str]:
    long, short = m.sides
    problems = []
    if abs(m.net) > m.gross:
        problems.append(f"net {m.net:.0%} is larger than gross {m.gross:.0%}")
    if m.long_only and short > 1e-9:
        problems.append("a long-only mandate needs net equal to gross")
    if m.long_only and m.beta is not None:
        problems.append("a long-only book cannot be beta neutral: set beta to null")
    if m.names_max * m.name_cap < m.gross:
        problems.append(
            f"{m.names_max} names at most {m.name_cap:.1%} each cannot reach {m.gross:.0%} gross"
        )
    if m.names_min > m.names_max:
        problems.append(f"names_min {m.names_min} is above names_max {m.names_max}")
    if m.country_cap is not None and len(m.countries) * m.country_cap < 1:
        problems.append(
            f"{len(m.countries)} countries at {m.country_cap:.0%} each cannot hold it all"
        )
    # Sector nets add up to the book's net, and there are eleven GICS sectors.
    if m.sector is not None and abs(m.net) > 11 * m.sector:
        problems.append(f"net {m.net:.0%} cannot fit eleven sectors capped at {m.sector:.0%} each")
    if m.net_band is not None and abs(m.net) > m.net_band:
        problems.append(f"net {m.net:.0%} is outside the band of ±{m.net_band:.0%}")
    if m.vol_target is not None and not 0 < m.vol_target <= 0.5:
        problems.append(f"a volatility target of {m.vol_target:.0%} a year cannot be met")
    unknown = sorted(set(m.exclude_sectors) - set(SECTORS.values()))
    if unknown:
        problems.append(f"unknown sectors {unknown}: use GICS codes or names, e.g. 10 or Energy")
    if m.min_market_cap is not None and m.min_market_cap < 0:
        problems.append("a smallest market cap below zero cannot be meant")
    if m.hurdle is not None and not 0 <= m.hurdle <= 0.5:
        problems.append(f"a hurdle of {m.hurdle:.0%} a year over the T-bill cannot be meant")
    if m.turnover is not None and not 0 < m.turnover <= m.gross:
        problems.append(f"a turnover cap of {m.turnover:.0%} a month cannot be met")
    if long > 0 and m.pool * m.name_cap < long:
        problems.append(f"a pool of {m.pool} per side at {m.name_cap:.1%} cannot fill {long:.0%}")
    return problems


# The mandate as plain data, for the run's record.
def record(m: Mandate) -> dict:
    return asdict(m)
