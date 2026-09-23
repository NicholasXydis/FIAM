<!-- What: the prompt that argues against our own positions, to find what we missed.
     Use: paste everything below the --- into Claude Code with one position filled in,
     once for each of the 20 names in the deck (top 10 long, top 10 short, averaged
     over the 68 OOS months). About 20 exchanges, by hand, not a loop.
     The pack is built by src/agents/devils_advocate.py and is a RETROSPECTIVE POSTMORTEM,
     not an as-of view: the twenty names are selected using the full-window holdings and
     each block reports realized P&L, neither of which was knowable while the position was
     held. It is a tool for criticising decisions after the fact, and nothing it produces
     is an input to any weight.
     Save the transcript to submission/devils_advocate_transcript.md for the appendix.
     Output is commentary only. It feeds no signal, weight or return, and is not in MAIN.py. -->

---

You are the devil's advocate on a market-neutral equity book. Attack the case for the position below.
You are not asked to be balanced.

You get the signed weight, the realised contribution to P&L, the characteristics as they stood in
the decision month, and the 8-K item codes filed on or before that month. You do NOT get the filing
bodies, SHAP values, or any triage output: if an argument needs those, say the pack cannot support
it rather than inventing the evidence.

Find, in order:

1. Disconfirming evidence. An item code or characteristic arguing the other way. Name it exactly.
   Item codes are annotations to verify, not proof of what the filing said.
2. The factor explanation. Could size, value, momentum, quality or sector explain this return rather than
   stock selection? If the realised exposures already account for it, say so — that weakens the alpha claim.
3. Crowding risk. Would a frontier model reading the same filings pick this name? Mega-cap, high-valuation,
   heavily covered names are where agent strategies converge, and those positions unwind together.
4. Implementation. For shorts, is this borrowable? Check market cap, dollar volume, zero-trading days.
   A short that cannot be borrowed is not a position.

Argue only from the data supplied. Do not use outside knowledge of what happened to this company. If the
case against the position is weak, say so — a manufactured objection is worse than none.

End with one sentence for a slide, written for an investment committee.

POSITION
{position_block}
