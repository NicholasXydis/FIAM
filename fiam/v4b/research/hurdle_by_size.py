"""Hurdle IR vs book size from Grinold alpha = IC x omega x z. No data read.

Inputs are pre-2021 panel medians from pre2021_noise.out (pool, idio vol);
TC, costs and the realised-TE inflation are stated judgements, not fits.
"""

import math
from statistics import NormalDist

ND = NormalDist()
POOL, GROSS, OMEGA = 1862, 1.77, 0.259  # names, crash-cap gross, idio vol/yr
HURDLE, COSTS, TC, INFL = 0.04, 0.02, 0.6, 1.5


def main():
    print("N   p     E|z|  TEidio TEreal | IR at IC=0.02 0.03 0.04 0.06 | IC needed")
    for n in (200, 275, 350, 450, 500):
        p = n / 2 / POOL
        ez = ND.pdf(ND.inv_cdf(1 - p)) / p
        te = GROSS * OMEGA / math.sqrt(n)
        per_ic = GROSS * TC * OMEGA / math.sqrt(12) * ez * 12
        irs = [(per_ic * ic - HURDLE - COSTS) / (te * INFL) for ic in (0.02, 0.03, 0.04, 0.06)]
        need = (HURDLE + COSTS) / per_ic
        print(
            f"{n:3d} {p:.3f} {ez:.2f} {te:.3%} {te * INFL:.3%} | "
            + " ".join(f"{x:+.2f}" for x in irs)
            + f" | {need:.4f}"
        )
    se = 0.10 / math.sqrt(24)
    print(
        "selection: SE(IC,24m)=",
        round(se, 4),
        " E[max] K=96 indep",
        round(se * math.sqrt(2 * math.log(96)), 4),
        " K_eff=10",
        round(se * math.sqrt(2 * math.log(10)), 4),
    )
    yr = 0.10 / math.sqrt(12)
    print(
        "P(neg year) IC=0.02 sd=0.10:",
        round(ND.cdf(-0.02 / yr), 3),
        " IC=0.04:",
        round(ND.cdf(-0.04 / yr), 3),
    )


if __name__ == "__main__":
    main()
