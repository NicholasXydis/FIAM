"""Blind v4b validation using native nautilus_trader orders, fills and accounts."""

import argparse
import dataclasses
import hashlib
import json
import pickle
import sys
from pathlib import Path

import nautilus_trader
import numpy as np
import pandas as pd

from fiam.v4b.engine import checker, fallback, inputs, ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.engine.nautilus_backend import run
from fiam.v4b.engine.nautilus_data import from_world
from fiam.v4b.engine.sim import Setup
from fiam.v4b.engine.yearly import performance
from fiam.v4b.forecast.run import _plain

OUT = Path(__file__).resolve().parents[1] / "out" / "nautilus"
OOS_OUT = Path(__file__).resolve().parents[1] / "out" / "nautilus_oos"
OOS_CUT = pd.Timestamp("2026-08-31")
OOS_WINDOW = (pd.Timestamp("2020-12-31"), pd.Timestamp("2026-07-31"))
OOS_DAILY = Path(__file__).resolve().parents[3] / "data" / "fiam_v1" / "daily_market_2026.parquet"


def main(names=("E3", "fallback"), cache=None, oos=False, out_dir=None):
    m = load()
    out = Path(out_dir) if out_dir else (OOS_OUT if oos else OUT)
    if cache:
        with Path(cache).open("rb") as handle:
            world = pickle.load(handle)
        if world.m != m:
            raise ValueError("cached world mandate differs")
    elif oos:
        # beta_mod.excess_wide reads inputs.daily; the explicit World path
        # covers the market and Nautilus feed, this patch covers the risk leg.
        inputs.DAILY = OOS_DAILY
        world = ladder.World(
            m,
            cut=OOS_CUT,
            window=OOS_WINDOW,
            daily_path=OOS_DAILY,
        )
    else:
        world = ladder.World(m)
    if not oos and world.sessions.max() > pd.Timestamp(m.policy.blind_until):
        raise ValueError("OOS remains sealed")
    # Registry only: eligibility at a formation still uses that dated row.
    e = world.rm.exp
    active = e[e.long_ok & e.eom.between(*world.window)]
    universe = pd.Index(sorted(active.permno.unique()))
    for k, v in list(world.market.items()):
        if isinstance(v, pd.DataFrame):
            world.market[k] = v.reindex(columns=universe)
    world.borrow = world.borrow.reindex(columns=universe)
    world.sessions = world.market["sessions"]
    feed = from_world(world)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "engine": "nautilus_trader",
        "version": nautilus_trader.__version__,
        "python": sys.version,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "mandate": dataclasses.asdict(m),
        "source_identity": ladder.SOURCE_IDENTITY,
        "window_eom": [str(x.date()) for x in world.window],
        "price_units": (
            "2015-2025 split-adjusted price-only shares with distributions paid in cash; "
            "2026 split-adjusted total-return index (no separate dividend leg)"
        ),
        "missing_quotes": ("a position unquoted for stub_days sessions is settled at its "
                           "last mark with half-spread and fees (D12, LESSONS 66)"),
        "fees": "engine/fees.py IBKR Pro fixed + SEC + FINRA TAF + CAT, schedule dated "
                "2026-09-30; flat borrow 0.5% (>= $10bn) / 5% other",
        "target_state": "native executed quantities and marked equity",
        "data_cutoff": str(world.sessions.max().date()),
        "oos": bool(oos),
        "diagnostic_only": bool(oos),
        "proxy_2026": (
            "2026-01-01..2026-08-31 uses a split-adjusted total-return index "
            "built from monthly panel ret and prc/adjfct, with panel ADV/spread; "
            "the mini file's raw daily_return is not used. 2015-2025 uses CRSP "
            "daily quotes and split-adjusted total returns"
        ),
        "native_reports": (
            "orders/fills/positions/accounts CSV and tearsheet export are "
            "disabled for the OOS diagnostic to bound memory; ledger and "
            "holdings are still built from native Nautilus fills"
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    panel = inputs.panel(fallback.COLUMNS, blind_until=world.cut)
    eoms = [
        pd.Timestamp(x)
        for x in sorted(world.rm.exp.eom.unique())
        if world.window[0] <= x <= world.window[1]
    ]
    all_yearly = []
    reports = {}
    for name in names:
        logs = []
        step = ladder.steps(n_e3=250).get(name)
        if name != "fallback" and step is None:
            raise ValueError(f"unknown step {name}")

        def builder(eom):
            def form(w_pre, nav):
                if name == "fallback":
                    pool = fallback.eligible(panel[panel.eom == eom], m, nav)
                    chosen = fallback.pick(pool, m.policy.fallback_names, set(w_pre.index))
                    sides = fallback.pair(chosen, np.sign(w_pre).to_dict())
                    if not m.hard.names_min <= len(sides) <= m.hard.names_max:
                        raise RuntimeError("fallback count outside mandate")
                    weights = sides * (m.policy.fallback_gross / len(sides))
                    log = {"eom": str(eom.date()), "status": "fallback", "nav": nav}
                else:
                    formation = world.formation(eom, step.column, w_pre, nav=nav)
                    weights, log = optimize.build_book(formation, m, step)
                    if weights is None:
                        raise RuntimeError(f"{name} {eom}: {log}")
                logs.append(log | {"nav_at_signal": nav})
                print(
                    f"{name} {eom.date()} native NAV {nav:,.0f} target {len(weights)} "
                    f"gross {weights.abs().sum():.3f}",
                    flush=True,
                )
                return weights

            return form

        targets = {world.signal_day(eom): builder(eom) for eom in eoms}
        setup = Setup(
            nav0=m.hard.nav0,
            participation=m.policy.participation,
            impact_y=m.policy.impact_y,
            stub_days=m.policy.stub_days,
        )
        result = run(targets, feed, setup, report_dir=out / name, native_reports=not oos)
        # The feed and the native report frames are no longer needed for the
        # policy checks; dropping them before the (large) position/panel joins
        # keeps the OOS run inside this machine's memory.
        if len(names) == 1:
            del feed
        del targets
        result.native_orders = result.native_fills = result.native_positions = (
            result.native_accounts
        ) = pd.DataFrame()
        led, pos = result.ledger, result.positions
        # The full native holdings frame carries many presentation columns;
        # the policy checks and attribution only need this audit subset.
        keep = [
            "date",
            "permno",
            "w",
            "w_pre",
            "rebalance",
            "quantity",
            "trade_dollars",
            "adv_dollars",
            "adv_days",
            "missing_sessions",
            "unverified_gap",
        ]
        pos = pos[[c for c in keep if c in pos]].copy()
        result.positions = pos
        breaches, days = checker.check(pos, panel, m, ramp_days=5, sessions=led.index[1:])
        policies = checker.policy_diagnostics(pos, world.policy_inputs(), m)
        summary = ladder.metrics(
            world,
            led,
            pos,
            enforce_policy=name != "E0",
            panel=panel,
            breaches=breaches,
            days=days,
            policy_days=policies,
        )
        breaches.to_parquet(out / name / "breaches.parquet", index=False)
        policies.to_parquet(out / name / "policy_exposures.parquet")
        unresolved = pos[(pos.missing_sessions >= setup.stub_days) & (pos.quantity != 0)]
        summary["unresolved_quote_position_days"] = len(unresolved)
        summary["unverified_gap_position_days"] = int(
            (pos.unverified_gap & pos.quantity.ne(0)).sum()
        )
        summary["eligible_for_oos"] = False
        summary["diagnostic_only"] = bool(oos)
        summary["diagnostic_label"] = (
            f"2021-2026 single run of {name} (D12)"
            if oos else f"2017-2020 validation of {name} (D12)"
        )
        summary["covariance_and_cost_audit"] = "audit complete; see RISK_COST_AUDIT.md"
        reports[name] = summary
        (out / name / "summary.json").write_text(
            json.dumps(summary, indent=2, default=_plain) + "\n"
        )
        (out / name / "solver_logs.json").write_text(
            json.dumps(logs, indent=1, default=_plain) + "\n"
        )
        yearly = performance(led, world.rf, m.hard.premium)
        yearly.insert(0, "model", name)
        yearly.to_csv(out / name / "yearly_performance.csv", index=False)
        all_yearly.append(yearly)
        stale_long = unresolved[unresolved.w > 0].assign(
            dollars=lambda q: q.w * q.date.map(led.nav)
        )
        reserve = stale_long.groupby("date").dollars.sum().reindex(led.index, fill_value=0)
        sensitivity = {}
        for haircut in (0.0, 0.3, 0.55, 1.0):
            adjusted = led.nav - haircut * reserve
            sensitivity[str(haircut)] = {
                "ending_nav": float(adjusted.iloc[-1]),
                "min_nav": float(adjusted.min()),
                "basis": "frozen-holdings valuation overlay, no sale or reoptimization",
            }
        (out / name / "valuation_sensitivity.json").write_text(
            json.dumps(sensitivity, indent=2) + "\n"
        )
        print(name, json.dumps(summary, default=_plain), flush=True)
    if ladder._source_identity() != ladder.SOURCE_IDENTITY:
        raise RuntimeError("source changed during run")
    (out / "summary.json").write_text(json.dumps(reports, indent=2, default=_plain) + "\n")
    pd.concat(all_yearly, ignore_index=True).to_csv(out / "yearly_performance.csv", index=False)
    manifest["artifacts"] = {
        str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", nargs="+", default=["E3", "fallback"])
    parser.add_argument("--world-cache", type=Path)
    parser.add_argument("--oos", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    main(args.steps, args.world_cache, oos=args.oos, out_dir=args.out)
