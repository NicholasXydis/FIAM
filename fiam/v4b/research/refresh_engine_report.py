"""Recompute reporting from completed, saved fills without selecting new targets.

Used after a reporting-only correction. A changed Ma1 selection or hurdle N
requires a construction rerun instead. The original generator identity and
new reporting identity are both retained in the manifest.
"""

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import pandas as pd

from fiam.v4b.engine import checker, inputs, ladder, optimize
from fiam.v4b.engine.mandate import load
from fiam.v4b.engine.reconcile import monthly_reference
from fiam.v4b.engine.yearly import MODELS, performance
from fiam.v4b.forecast.run import _plain

OUT = ladder.OUT


def refresh(world=None):
    m = load()
    report_path, manifest_path = OUT / "ladder.json", OUT / "manifest.json"
    report, manifest = json.loads(report_path.read_text()), json.loads(manifest_path.read_text())
    if "final_steps" not in manifest:
        raise ValueError("construction is incomplete: final steps are absent")
    world = world or ladder.World(m)
    if world.m != m or world.sessions.max() > pd.Timestamp(m.policy.blind_until):
        raise ValueError("reporting world does not match the frozen blind mandate")
    panel = inputs.panel(["me", "me_company"])
    runs, monthly, active, yearly, evidence = {}, {}, {}, [], {}
    for name in MODELS:
        led_path, pos_path = OUT / f"ledger_{name}.parquet", OUT / f"positions_{name}.parquet"
        ledger, pos = pd.read_parquet(led_path), pd.read_parquet(pos_path)
        if (
            ledger.index.has_duplicates
            or not ledger.index.is_monotonic_increasing
            or ledger.index.max() > pd.Timestamp(m.policy.blind_until)
        ):
            raise ValueError(f"{name}: invalid ledger dates")
        bands = name != "E0"
        runs[name] = ladder.metrics(world, ledger, pos, enforce_policy=bands)
        runs[name]["monthly_reconciliation"] = monthly_reference(
            ledger, pos, world.market["returns"]
        )
        monthly[name] = ladder.monthly_active(ledger, world)
        active[name] = (
            ledger.ret.iloc[1:] - world.rf.reindex(ledger.index[1:]) - m.hard.premium / 252
        )
        breaches, _ = checker.check(pos, panel, m, ramp_days=5, sessions=ledger.index[1:])
        breaches.to_parquet(OUT / f"breaches_{name}.parquet", index=False)
        policies = checker.policy_diagnostics(pos, world.policy_inputs(), m)
        policies.to_parquet(OUT / f"policy_{name}.parquet")
        table = performance(ledger, world.rf, m.hard.premium)
        table.insert(0, "model", name)
        counts = breaches.groupby(breaches.date.dt.year).size()
        table["breach_rows"] = table.year.map(counts).fillna(0).astype(int)
        policy_counts = policies.violated.groupby(policies.index.year).sum()
        table["policy_breach_days"] = table.year.map(policy_counts).fillna(0).astype(int)
        yearly.append(table)
        for path in (led_path, pos_path):
            evidence[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    def compare(old, new, floor=ladder.GATE_FLOOR):
        return ladder.gate(
            runs[old], runs[new], monthly[old], monthly[new], active[old], active[new], floor=floor
        )

    ma1 = compare("E2", "E2_Ma1", floor=0)
    winner = "Elasso_Ma1" if ma1["promoted"] else "Elasso_MaInf"
    previous_winner = report["gates"]["Ma1_over_MaInf_at_E2"]["winner"]
    if winner != previous_winner:
        raise ValueError("report correction changes Ma1 selection: rerun construction")
    winner_run = "E2_Ma1" if ma1["promoted"] else "E2"
    costs = ladder._costs_by_n(runs[winner_run], n_ref=round(runs[winner_run]["avg_names"]))
    n, hurdle = optimize.hurdle_pick(ladder.FROZEN_IC, costs, gross=m.policy.target_gross)
    if n != manifest["final_steps"]["E3"]["names"]:
        raise ValueError("report correction changes hurdle N: rerun construction")
    gates = {
        "E1_over_E0": compare("E0", "E1"),
        "E2_over_E1": compare("E1", "E2"),
        "Ma1_over_MaInf_at_E2": ma1 | {"winner": winner},
        "E3_over_winner": compare(winner_run, "E3"),
    }
    stress = ladder.metrics(
        world,
        pd.read_parquet(OUT / "ledger_E3_adv_half.parquet"),
        pd.read_parquet(OUT / "positions_E3_adv_half.parquet"),
        enforce_policy=True,
    )
    gates["E3_over_winner"]["stress_process_passed"] = ladder.process_ok(stress)
    gates["E3_over_winner"]["promoted"] &= ladder.process_ok(stress)
    spreads = {}
    for mult in m.policy.spread_multipliers:
        spreads[str(mult)] = ladder.metrics(
            world,
            pd.read_parquet(OUT / f"ledger_E3_spread_{mult}.parquet"),
            pd.read_parquet(OUT / f"positions_E3_spread_{mult}.parquet"),
            enforce_policy=True,
        )
    candidate, ship = ladder.select_candidate(runs, gates, ma1["promoted"])
    report.update(
        runs=runs,
        gates=gates,
        candidate_by_gates=candidate,
        ship=ship,
        monthly_candidate_eligible=ship is not None,
        ready_for_freeze=False,
        ready_for_oos=False,
        stress_adv_half=stress,
        ir_stressed_adv_half=stress["net_ir_daily"],
        spread_sensitivity=spreads,
        hurdle={"n_pick": n, "table": hurdle, "ic_frozen": ladder.FROZEN_IC, "costs_by_n": costs},
    )
    report["reporting_note"] = (
        "Monthly cohort arithmetic uses float64, matching simulation; "
        "targets and actual fills are unchanged."
    )
    if ladder._source_identity() != ladder.SOURCE_IDENTITY:
        raise ValueError("source changed while refreshing reporting")
    manifest["report_refresh"] = {
        "generator_source_identity": manifest["source_identity"],
        "report_source_identity": ladder.SOURCE_IDENTITY,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ledger_and_position_sha256": evidence,
        "selection_and_hurdle_unchanged": True,
    }
    table = pd.concat(yearly, ignore_index=True)
    table.to_csv(OUT / "yearly_performance.csv", index=False)
    (OUT / "yearly_performance.json").write_text(
        json.dumps(table.to_dict("records"), indent=2, default=_plain) + "\n"
    )
    pd.DataFrame(monthly).to_parquet(OUT / "monthly_active.parquet")
    report_path.write_text(json.dumps(report, indent=2, default=_plain) + "\n")
    manifest_path.write_text(json.dumps(manifest, indent=2, default=_plain) + "\n")
    print(
        table[["model", "year", "net_return", "net_ir", "max_drawdown", "cost_pct_nav"]].to_string(
            index=False
        )
    )
    print("candidate", candidate, "ship", ship)
    return report, table


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--world-cache",
        type=Path,
        help="Trusted local World pickle, optional; otherwise rebuild blind inputs",
    )
    args = parser.parse_args()
    world = None
    if args.world_cache:
        with args.world_cache.open("rb") as handle:
            world = pickle.load(handle)
    refresh(world)
