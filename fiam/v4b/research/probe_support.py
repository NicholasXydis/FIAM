import pickle
from pathlib import Path

import pandas as pd

from fiam.v4b.engine import ladder, optimize
from fiam.v4b.engine.mandate import load


def main():
    path = Path("fiam/v4b/cache/validation_world.pkl")
    if path.exists():
        with path.open("rb") as handle:
            world = pickle.load(handle)
    else:
        world = ladder.World(load())
        with path.open("wb") as handle:
            pickle.dump(world, handle)
    f = world.formation("2017-02-28", "Elasso_MaInf", pd.Series(dtype=float))
    step = optimize.Step("E1")
    c = optimize._candidates(f, world.m)
    longs = c[c.long_ok].nlargest(400, "mu")
    shorts = c[c.short_ok].nsmallest(400, "mu")
    w0, log0 = optimize.solve_qp(f, world.m, step, longs.index.union(shorts.index), None)
    print("stage0", log0, flush=True)
    if w0 is not None:
        print("stage0 by sector", w0.groupby(f.snap["month"].sector).sum(), flush=True)
    names, signs, extra = optimize.greedy_support(f, world.m, step)
    c = c.loc[names].assign(side=signs)
    print(c.groupby(["sector", "side"]).agg(n=("cap", "size"), cap=("cap", "sum")), flush=True)
    w, log = optimize.build_book(f, world.m, step)
    print(log, flush=True)


if __name__ == "__main__":
    main()
