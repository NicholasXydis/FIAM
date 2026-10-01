# Amendment 4: the factor-neutral book against the current one, once, on 2016-2026.


from fiam import benchmarks as B
from fiam import book as P
from fiam import paths
from fiam.exhibits import construction as K
from fiam.exhibits.pack import factor_fit

OUT = paths.EXHIBITS / "factor_neutral.json"
WINDOWS = dict(
    y2016_2020=("2016-01-01", "2020-12-01"),
    y2021_2022=("2021-01-01", "2022-12-01"),
    y2023_2026=("2023-01-01", "2026-08-01"),
    y2021_2026=("2021-01-01", "2026-08-01"),
)


# Six-factor loadings and the alpha left after them, over every month the book holds.
def factors(book) -> dict:
    five = B.french("ff5_factors.zip", ["mkt_rf", "smb", "hml", "rmw", "cma", "rf"])
    six = five.drop(columns="rf").join(B.french("ff_momentum.zip", ["mom"]), how="inner")
    fit = factor_fit(book["net"], six)
    return dict(alpha_annual=fit["alpha_annual"], alpha_t=fit["alpha_t"], betas=fit["betas"])


# The four rules amendment 4 fixed, each true or false.
def verdict(current: dict, neutral: dict) -> dict:
    rules = dict(
        ir_higher=neutral["information_ratio"] > current["information_ratio"],
        monthly_beta_closer_to_zero=abs(neutral["beta_monthly"]) < abs(current["beta_monthly"]),
        drawdown_shallower=neutral["max_drawdown"] > current["max_drawdown"],
        every_rule_every_month=100 <= neutral["names_min"]
        and neutral["names_max"] <= 500
        and neutral["gross_max"] <= 2.0
        and neutral["net_max_abs"] <= 0.5
        and neutral["gross_max_2021_2025"] <= 2.0,
    )
    return dict(**rules, ships=all(rules.values()))


def main() -> None:
    books = {}
    for name, design in (("current", P.CURRENT), ("factor_neutral", P.NEUTRAL)):
        book, holdings = K.run(design)
        books[name] = dict(**K.monthly(book), **K.daily(book, holdings), factors=factors(book))
        books[name]["by_window"] = {
            w: P.information_ratio(book.loc[a:b, "net"]) for w, (a, b) in WINDOWS.items()
        }
        print(f"  {name}: IR {books[name]['information_ratio']:+.2f}, {books[name]['by_window']}")
    out = dict(
        what="The current book and the factor-neutral book on 2016-01 to 2026-08, both with the "
        "Phase 2 costs, judged once by the rules amendment 4 fixed.",
        factors=dict(zip(("size", "value", "profitability", "investment", "momentum"), P.FACTORS)),
        current=books["current"],
        factor_neutral=books["factor_neutral"],
        verdict=verdict(books["current"], books["factor_neutral"]),
    )
    paths.write_json(OUT, out)
    print(f"  verdict: {out['verdict']}")


if __name__ == "__main__":
    main()
