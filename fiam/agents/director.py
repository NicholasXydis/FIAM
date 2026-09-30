# The research director: an agent picks each year's book from the months before it, scored after.


import pandas as pd

from fiam import book as P
from fiam import evaluate as E
from fiam import paths
from fiam.agents import harness as H

PROMPT = H.ROOT / "prompts" / "agents" / "director.md"
OUT = paths.EXHIBITS / "director.json"
SHIP, MONTHS = paths.EXHIBITS / "ship.json", paths.EXHIBITS / "ship_candidates.csv"
BUDGET = 4 if paths.SMOKE else 15


# Every candidate's monthly record, as the ship step wrote it.
def load() -> pd.DataFrame:
    table = pd.read_csv(MONTHS, parse_dates=["holding_month"])
    return table.set_index(["candidate", "holding_month"]).sort_index()


# One year's decision room: the tools see holding months before that year, nothing later.
class Room:
    # Keeps only holding months before the decision year.
    def __init__(self, table: pd.DataFrame, year: int):
        self.table = table[table.index.get_level_values("holding_month") < f"{year}-01-01"]
        self.names = list(P.CANDIDATES)

    # A window's IR, beta, net, cost, turnover and worst drawdown for one candidate.
    def stats(self, name: str, first_year: int) -> dict:
        if name not in self.names:
            raise KeyError(f"no candidate named {name}")
        part = self.table.loc[name]
        part = part[part.index >= f"{first_year}-01-01"]
        if len(part) < 6:
            raise ValueError("fewer than six months in that window")
        wealth = (1 + part["net"]).cumprod()
        fit = P.judge(part["net"], str(part.index.min().date()), str(part.index.max().date()))
        return dict(
            months=len(part),
            information_ratio=round(fit["information_ratio"], 2),
            beta=round(fit["beta"], 2),
            net_annual=round(part["net"].mean() * 12, 3),
            cost_annual=round(part["cost"].mean() * 12, 3),
            turnover=round(part["turnover"].mean(), 2),
            max_drawdown=round(float((wealth / wealth.cummax() - 1).min()), 3),
        )

    # Each candidate's name in words.
    def list_candidates(self) -> dict:
        return {n: P.candidate_label(n) for n in self.names}

    # Every candidate over the same window, side by side.
    def compare(self, first_year: int) -> dict:
        return {n: self.stats(n, first_year) for n in self.names}

    # One candidate year by year, so a single lucky year shows.
    def by_year(self, name: str) -> dict:
        part = self.table.loc[name]["net"]
        return {
            str(y): dict(net=round(g.sum(), 3), information_ratio=round(P.information_ratio(g), 2))
            for y, g in part.groupby(part.index.year)
        }


# Read-only tools over one year's room, and the answer.
def tools(room: Room) -> list[H.Tool]:
    empty = dict(type="object", properties={})
    window = dict(
        type="object",
        properties=dict(first_year=dict(type="integer", description="first holding year")),
        required=["first_year"],
    )
    named = dict(type="object", properties=dict(name=dict(type="string")), required=["name"])
    answer = dict(
        type="object",
        properties=dict(
            candidate=dict(type="string", enum=list(P.CANDIDATES)),
            reason=dict(type="string", description="why, quoting only numbers a tool returned"),
        ),
        required=["candidate", "reason"],
    )
    return [
        H.Tool(
            "list_candidates",
            "Each candidate's name and what it adds.",
            empty,
            room.list_candidates,
        ),
        H.Tool(
            "compare",
            "Every candidate over holding months from first_year to the decision: IR, beta, net, "
            "cost, turnover, drawdown.",
            window,
            room.compare,
        ),
        H.Tool(
            "by_year", "One candidate's net return and IR in each past year.", named, room.by_year
        ),
        H.Tool("final_answer", "The candidate to trade next year, and why.", answer, lambda **a: a),
    ]


# One run per ship year, then the picks scored against the rule and chance.
def main() -> None:
    table = load()
    system = PROMPT.read_text(encoding="utf-8")
    rule = paths.read_json(SHIP)["chosen"]
    picks, years = {}, {}
    with H.Server("qwen") as server:
        for year in map(int, rule):
            room = Room(table, year)
            task = f"Choose the book for {year}. The last month you can see is December {year - 1}."
            run = H.Run("director", "qwen", system, task, BUDGET, tag=str(year))
            result = H.run_agent(server, run, tools(room))
            answer = result["answer"] or {}
            # No answer within the budget keeps the default, and says so.
            pick = answer.get("candidate") if answer.get("candidate") in room.names else "composite"
            picks[str(year)] = pick
            years[str(year)] = dict(
                pick=pick,
                reason=answer.get("reason", "no answer within the budget"),
                rule=rule[str(year)],
                status=result["status"],
                calls=len(result["calls"]),
                transcript=result["transcript"].relative_to(H.ROOT).as_posix(),
            )
    summary = dict(
        what="Each year an agent chose one book from the candidate grid using the months before "
        "it, with the rule's choice beside it. Scored afterwards by joining each year's pick; a "
        "switch carries last year's book, so these are close to, not equal to, a walked book.",
        model=server.name,
        years=years,
        director=E.chance(E.candidates(), picks),
        rule=E.chance(E.candidates(), rule),
        agreed_with_rule=sum(picks[y] == rule[y] for y in picks),
    )
    paths.write_json(OUT, summary)
    d = summary["director"]
    print(f"director IR {d['information_ratio']:+.2f}, above {d['share_of_random_beaten']:.0%}")


if __name__ == "__main__":
    main()
