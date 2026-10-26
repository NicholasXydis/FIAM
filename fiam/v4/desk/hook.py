# The desk in the engine: A0's formations kept, shrinks at t+1.

import copy

from fiam.v4.construct import execution
from fiam.v4.desk import after, arms

# Arm A0 is the exam's own run, recorded by step 7's hook.
Recording = execution.Recording


# An arm's hook: A0's formations replayed, its shrinks one close late.
class Arm(execution.Execution):
    # A0's formations (copied again), its switches and this arm's shrinks.
    def __init__(self, made: dict, plan: dict, squeeze=None, trigger=None, overlays=None,
                 brake: bool = False):  # fmt: skip
        super().__init__(copy.deepcopy(made), squeeze=squeeze, trigger=trigger,
                         overlays=overlays, brake=brake)  # fmt: skip
        self.plan_shrinks = plan

    # The step 7 rules, then today's shrinks queued for the next close.
    def watch(self, i, d, book, want) -> None:
        super().watch(i, d, book, want)
        if self.live is None:
            return
        held = want.index[want.abs() > 1e-9]
        cut = {p: m for p, m in arms.today(self.plan_shrinks, d).items() if p in held}
        if cut:
            f = self.live
            self.queue(d, "desk", len(cut),
                       lambda w, s=cut: after.enforce(w, s, f.cap_of(w))[0])  # fmt: skip
