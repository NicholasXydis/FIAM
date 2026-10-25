# The site's data and the ad's crises, from final v3's pack. Read only.

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The repo root on the path, so crisis windows import fiam from any cwd.
sys.path.insert(0, str(ROOT))
BOOK = "brake+shorts+size+target10+voltarget+zerobeta@1e7"
PACK = ROOT / "out" / "finals" / BOOK / "submission"
V2 = ROOT / "out" / "v2"
EXHIBITS = ROOT / "submission" / "exhibits"
OUT = ROOT / "site" / "src" / "data" / "fiam.json"
CRASHES = ROOT / "site" / "src" / "data" / "crashes.json"
CACHE = ROOT / "cache" / "stress_daily.parquet"
MODELS = {"gemma": "Gemma 4 26B-A4B", "qwen": "Qwen3.8-27B"}
# The twelve measures in fiam/book.py, grouped by the question asked.
SIGNALS = [
    ("be_me", +1, "cheap", "Book-to-market"),
    ("qmj", +1, "profitable", "Quality minus junk"),
    ("ope_be", +1, "profitable", "Operating profit to equity"),
    ("gp_at", +1, "profitable", "Gross profit to assets"),
    ("at_gr1", -1, "careful", "Asset growth"),
    ("noa_gr1a", -1, "careful", "Growth in operating assets"),
    ("chcsho_12m", -1, "careful", "Net stock issues"),
    ("eqnetis_at", -1, "careful", "Net equity issuance"),
    ("ret_12_1", +1, "rising", "12-month momentum"),
    ("niq_su", +1, "rising", "Earnings surprise"),
    ("ivol_capm_21d", -1, "safe", "Idiosyncratic volatility"),
    ("o_score", -1, "safe", "Distress risk (O-score)"),
]
FAMILIES = {
    "cheap": "Is it cheap?",
    "profitable": "Is it profitable?",
    "careful": "Is it careful with its money?",
    "rising": "Is it rising?",
    "safe": "Is it safe?",
}
CAPACITY = {"v1": "First book", "v2": "Built for size", "v2-pass": "Short rule only"}


# A JSON file from the pack or out/v2, as a dict.
def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# A CSV file as one dict per row, as the pack's returns are read.
def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# Rounds a number for the site file, so the bundle stays small.
def r(x: float, digits: int = 4) -> float:
    return round(float(x), digits)


# The month before a "YYYY-MM" month.
def before(month: str) -> str:
    year, m = int(month[:4]), int(month[5:7]) - 1
    return f"{year - 1}-12" if m == 0 else f"{year}-{m:02d}"


# Growth of $1 for the book, hurdle (T-bill + 4%) and S&P 500 by month.
def race(returns: list[dict], months: list[str]) -> dict:
    close = {}
    for row in rows(ROOT / "data" / "benchmarks" / "SP500.csv"):
        if row["SP500"] not in ("", "."):
            close[row["observation_date"][:7]] = float(row["SP500"])
    book, hurdle, market = [1.0], [1.0], [1.0]
    monthly = []
    for row, month in zip(returns, months):
        total, active = float(row["portfolio_total_return"]), float(row["active_return"])
        sp = close[month] / close[before(month)] - 1
        book.append(book[-1] * (1 + total))
        hurdle.append(hurdle[-1] * (1 + total - active))
        market.append(market[-1] * (1 + sp))
        monthly.append(sp)
    return dict(
        book=[r(x) for x in book],
        hurdle=[r(x) for x in hurdle],
        market=[r(x) for x in market],
        market_monthly=[r(x) for x in monthly],
        book_monthly=[r(float(x["portfolio_total_return"])) for x in returns],
    )


# Every held stock, and each month as [stock, weight in 0.001% units].
def holdings(pack: Path, months: list[str]) -> dict:
    names, held = {}, {m: [] for m in months}
    for row in rows(pack / "holdings.csv"):
        permno = int(row["PERMNO"])
        names[permno] = (row["TICKER"] or "", row["COMPANY NAME"] or "")
        held[row["Date"][:7]].append((permno, float(row["WEIGHT"])))
    order = sorted(names)
    index = {p: i for i, p in enumerate(order)}
    book = []
    for month in months:
        flat = []
        for permno, weight in sorted(held[month]):
            flat += [index[permno], round(weight * 1000)]
        book.append(flat)
    return dict(
        ticker=[names[p][0] for p in order],
        name=[names[p][1].title() for p in order],
        book=book,
    )


# The September 2026 book, blank names filled from the record's latest.
def september(pack: Path) -> dict:
    known = {}
    for row in rows(pack / "holdings.csv"):
        known[row["PERMNO"]] = (row["TICKER"] or "", row["COMPANY NAME"] or "")
    book = []
    for row in rows(ROOT / "frozen" / "september_final.csv"):
        ticker, name = row["ticker"], row["company_name"]
        if not ticker:
            ticker, name = known.get(row["permno"], ("", ""))
        book.append([ticker, name.title(), round(float(row["weight"]) * 1e5)])
    book.sort(key=lambda x: -x[2])
    return dict(decision="2026-08-31", book=book)


# Gross and net return, the cost parts and the break-even ladder.
def costs(pack: dict, metrics: dict) -> dict:
    parts = pack["costs"]["components"]
    even = pack["costs"]["break_even"]
    return dict(
        gross=r(metrics["performance"]["return_gross_annual"]),
        net=r(metrics["performance"]["return_net_annual"]),
        parts={k: r(v, 5) for k, v in parts.items() if k != "total"},
        total=r(parts["total"], 5),
        break_even_multiple=r(even["break_even_multiple"], 3),
        break_even_cost=r(even["break_even_annual_cost"]),
        ladder=[
            dict(
                multiple=float(k[1:]),
                cost=r(v["annual_cost"]),
                active=r(v["active_annual"]),
                ir=r(v["information_ratio"], 3),
            )
            for k, v in even["ladder"].items()
        ],
    )


# The 1,000 random large-cap books and benchmarks on the same money.
def edge(report: dict) -> dict:
    null = report["null"]
    irs = [round(float(x["ir"]), 3) for x in rows(V2 / "final_exhibits" / "null_irs.csv")]
    naive, large = report["naive"], report["large"]
    small = next(v for k, v in large.items() if k.endswith("@1e7"))
    live = report["projection"]["1e7"]
    ladder = [
        ("Random large-cap books, average", null["mean"], "null"),
        ("Equal weights on our score", naive["naive_equal_model@1e7"]["information_ratio"], "alt"),
        (
            "Equal weights on our own names",
            naive["naive_equal_holdings@1e7"]["information_ratio"],
            "alt",
        ),
        (
            "Our favourite names held still",
            naive["favourites_held@1e7"]["information_ratio"],
            "alt",
        ),
        ("Our rule on the 500 largest stocks", small["information_ratio"], "alt"),
        ("Expected live, after published haircuts", live["harvey_liu_2015"], "live"),
        ("Final book", null["final_ir"], "ours"),
    ]
    return dict(
        irs=irs,
        draws=null["draws"],
        final=r(null["final_ir"], 3),
        best=r(null["best"], 3),
        mean=r(null["mean"], 3),
        p5=r(null["p5"], 3),
        p95=r(null["p95"], 3),
        beaten=round(null["percentile"] * null["draws"]),
        live_low=r(live["harvey_liu_2015"], 3),
        live_high=r(live["mclean_pontiff_2016"], 3),
        ladder=[dict(label=a, ir=r(b, 3), kind=c) for a, b, c in ladder],
    )


# IR and dollars a year by fund size, for our book and three it beat.
def capacity() -> dict:
    books = load(V2 / "capacity.json")["books"]
    out = []
    for key, label in {**CAPACITY, "final v3": "Final book"}.items():
        out.append(
            dict(
                key=key,
                label=label,
                break_even=books[key]["break_even"],
                peak=books[key]["peak"],
                rows=[
                    dict(
                        capital=x["capital"],
                        ir=r(x["information_ratio"], 3),
                        net=r(x["net_annual"]),
                        cost=r(x["cost_annual"]),
                        dollars=round(x["dollars"]),
                    )
                    for x in books[key]["record"]
                ],
            )
        )
    return dict(books=out)


# Each retail persona and its client brief, from prompts/agents.
def personas() -> list[dict]:
    text = (ROOT / "prompts" / "agents" / "crowd_lab.md").read_text(encoding="utf-8")
    parts = text.split("\n## ")[1:]
    return [
        dict(key=key, client=" ".join(body.split()).removeprefix("Your client "))
        for key, body in (part.split("\n", 1) for part in parts)
    ]


# The AI Crowd Lab's agreement, diversity and overlap with our book.
def crowd() -> dict:
    lab = load(V2 / "crowd_lab.json")
    insights = load(V2 / "crowd_insights.json")[f"book {BOOK}"]
    record = lab[f"{BOOK} record"]
    picks = load(EXHIBITS / "crowd.json")
    retail = lab["retail"]
    return dict(
        personas=personas(),
        agents=retail["agreement"]["agents"],
        copycats=lab["copycat"]["agreement"]["agents"],
        effective_voters=r(retail["agreement"]["effective_voters"], 2),
        correlation=r(retail["agreement"]["mean_correlation"], 3),
        same_information=r(retail["diversity"]["same_information_different_persona"], 3),
        same_persona=r(retail["diversity"]["same_persona_different_information"], 3),
        rerun_agreement=r(retail["replay_checks"]["rerun"]["agreement"], 3),
        longs_in_favourites=r(insights["overlap"]["retail"]["longs_in_favourites"], 3),
        shorts_in_favourites=r(insights["overlap"]["retail"]["shorts_in_favourites"], 3),
        copycat_longs=r(insights["overlap"]["copycat"]["longs_in_favourites"], 3),
        copycat_test={
            k: dict(longs=r(v["buys_our_longs"], 2), shorts=r(v["shorts_our_shorts"], 2))
            for k, v in insights["copycat_test"].items()
        },
        crowd_beta=r(record["crowding_beta"]["beta"], 3),
        crowd_t=r(record["crowding_beta"]["t"], 2),
        picks=picks["picks"],
        models=[MODELS.get(m, m) for m in ("gemma", "qwen")],
        model_agreement=r(picks["agreement_between_models"], 3),
        likes={k: r(v, 3) for k, v in picks["what_the_crowd_likes"].items()},
    )


# The agents, each with the few numbers that say what it did.
def agents(desk: dict) -> list[dict]:
    triage, analyst = load(EXHIBITS / "triage.json"), load(EXHIBITS / "analyst.json")
    picks = load(EXHIBITS / "crowd.json")
    advocate = desk["advocate"]
    return [
        dict(
            key="rules",
            name="Rules reader",
            model=MODELS["gemma"],
            does="Reads the finals rules and quotes every limit word for word",
            facts=[["Limits quoted", "every one, with its source line"]],
        ),
        dict(
            key="triage",
            name="Triage",
            model=MODELS["gemma"],
            does="Sorts company filings into routine, good, bad and distress",
            facts=[
                ["Filings labelled", f"{triage['labelled']:,}"],
                ["Accuracy, cross-validated", f"{triage['cross_validated_accuracy']:.0%}"],
            ],
        ),
        dict(
            key="analyst",
            name="Analyst",
            model=MODELS.get(analyst["model"], analyst["model"]),
            does="Reads a stock's month with names, tickers and dates hidden",
            facts=[
                ["Verdicts", f"{analyst['stock_months']:,}"],
                [
                    "Named the hidden company",
                    f"{analyst['look_ahead_probe']['company_named']:.0%} of "
                    f"{analyst['look_ahead_probe']['filings']} filings",
                ],
            ],
        ),
        dict(
            key="advocate",
            name="Devil's advocate",
            model=MODELS["gemma"],
            does="Attacks the final book, and code checks every claim",
            facts=[
                ["Critiques raised", str(advocate["asked"])],
                ["Confirmed by code", str(advocate["confirmed"])],
            ],
        ),
        dict(
            key="memo",
            name="Memo writer",
            model=MODELS["qwen"],
            does="Writes the PM memo, and every number in it is checked",
            facts=[["Unsupported numbers", str(len(desk["memo"]["unsupported_numbers"]))]],
        ),
        dict(
            key="explainer",
            name="Explainer",
            model=MODELS["qwen"],
            does="Says why the book holds a name, from the facts it was shown",
            facts=[["Positions explained", str(len(desk["september"]["explained"]))]],
        ),
        dict(
            key="crowd",
            name="AI crowd",
            model=" and ".join(MODELS.values()),
            does="Plays retail stock pickers on anonymous stock cards",
            facts=[
                ["Picks", f"{picks['picks']:,}"],
                ["Agreement between the two models", f"{picks['agreement_between_models']:.2f}"],
            ],
        ),
    ]


# Every attempt by family from the RESULTS.md ledger, and what survived.
def honesty(metrics: dict, pack: dict, desk: dict) -> dict:
    robust = metrics["robustness"]
    halves = pack["subperiod"]
    return dict(
        attempts=robust["attempts_all"],
        eligible=robust["attempts_eligible"],
        dsr_all=r(robust["deflated_sharpe_probability_all"], 3),
        dsr_eligible=r(robust["deflated_sharpe_probability_eligible"], 3),
        first_half_ir=r(halves["first_half_2021_2022"]["information_ratio"], 2),
        second_half_ir=r(halves["second_half_2023_2026"]["information_ratio"], 2),
        check_2016_2020_ir=r(desk["registry"]["weak_2016_2020"]["value"], 2),
        families=[
            dict(
                what=x["experiment"],
                family=x["family"],
                eligible=x["eligible_for_deployment"] == "yes",
                attempts=int(x["attempts"]),
                result=x["result"],
                verdict=x["verdict"],
            )
            for x in rows(EXHIBITS / "config_log.csv")
        ],
    )


# Each replayed crisis beside the value-weighted US market's move.
def crises() -> list[dict]:
    import pandas as pd

    from fiam.exhibits.stress import CRISES

    daily = pd.read_parquet(CACHE, columns=["date", "ret", "cap"]).dropna()
    replay = load(V2 / "stress.json")["final v3"]["crises"]
    out = []
    for name, (first, last) in CRISES.items():
        days = daily[(daily["date"] >= first) & (daily["date"] <= last)]
        weight = days["cap"] / (1 + days["ret"])
        market = (days["ret"] * weight).groupby(days["date"]).sum() / weight.groupby(
            days["date"]
        ).sum()
        out.append(
            dict(
                name=name,
                first=first,
                last=last,
                market=r((1 + market).prod() - 1),
                book=r(replay[name]["loss"]),
                coverage=r(replay[name]["coverage"], 2),
            )
        )
    return out


# The site's whole data file from the pack, the desk and the exhibits.
def build(folder: Path = PACK) -> dict:
    metrics, pack = load(folder / "metrics.json"), load(folder / "exhibits" / "pack.json")
    returns = rows(folder / "returns.csv")
    months = [x["holding_month"][:7] for x in returns]
    desk, report = load(V2 / "desk_final.json"), load(V2 / "final_exhibits" / "report.json")
    perf, comp = metrics["performance"], pack["completeness"]
    stress = load(V2 / "stress.json")["final v3"]["crises"]
    return dict(
        book=BOOK,
        code=metrics["run"]["code_sha256"],
        window=metrics["run"]["window"],
        months=months,
        headline=dict(
            ir=r(perf["information_ratio"], 3),
            ir_gross=r(perf["information_ratio_before_costs"], 3),
            net=r(perf["return_net_annual"]),
            gross=r(perf["return_gross_annual"]),
            cagr=r(perf["return_total_cagr"]),
            vol=r(perf["volatility_annual"]),
            sharpe=r(perf["sharpe_ratio"], 3),
            drawdown=r(perf["max_drawdown_total"]),
            alpha=r(perf["alpha_annual"]),
            alpha_t=r(perf["alpha_tstat"], 2),
            beta=r(perf["beta_realized"], 3),
            beta_se=r(perf["beta_stderr"], 3),
            correlation=r(perf["correlation_with_market"], 3),
            hit=r(perf["hit_rate_positive_active_months"], 3),
            positions=r(metrics["compliance"]["positions_average"], 1),
            longs=r(comp["average_long_positions"], 1),
            shorts=r(comp["average_short_positions"], 1),
            turnover=r(metrics["costs"]["turnover_monthly_one_way"], 3),
            cumulative=r(comp["cumulative_return_full_period"]),
            best_month=comp["comparison"]["strategy"]["best_month"],
            worst_month=comp["comparison"]["strategy"]["worst_month"],
        ),
        years={
            k: {n: r(v[n]) for n in ("strategy", "benchmark", "market", "active")}
            | {"months": v["months"]}
            for k, v in comp["by_year"].items()
        },
        race=race(returns, months),
        beta=dict(
            exante=[r(float(x["beta"])) for x in returns],
            rolling={
                k: [r(v["beta"], 3), r(v["noise_band"], 3)]
                for k, v in pack["beta_drift"]["rolling_12m"].items()
            },
            outside_noise=r(pack["beta_drift"]["rolling_12m_outside_noise_band"], 3),
        ),
        stocks=holdings(folder, months),
        signals=[dict(code=c, sign=s, family=f, label=label) for c, s, f, label in SIGNALS],
        families=FAMILIES,
        journey=load(ROOT / "out" / "figures" / "clips" / "journey.json"),
        costs=costs(pack, metrics),
        edge=edge(report),
        capacity=capacity(),
        crowd=crowd(),
        agents=agents(desk),
        explained=desk["september"]["explained"],
        september=september(folder),
        factor_story=desk["factor_story"]["story"],
        crises={k: r(v["loss"]) for k, v in stress.items()},
        honesty=honesty(metrics, pack, desk),
    )


# Both files need the pack and crisis cache, which the results kit sets.
def main(args: list[str]) -> None:
    folder = Path(args[0]) if args else PACK
    for path in (folder, CACHE):
        if not path.exists():
            raise SystemExit(f"No {path}: uv run run.py --import fiam_results.zip first.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for out, data in ((OUT, build(folder)), (CRASHES, crises())):
        out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}: {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1:])
