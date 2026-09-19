<!-- What: the prompt that argues against our own positions, to find what we missed.
     Use: paste everything below the --- into Claude Code with one position filled in,
     once for each of the 20 names in the deck (top 10 long, top 10 short, averaged
     over the 68 OOS months). About 20 exchanges, by hand, not a loop.
     Save the transcript to submission/devils_advocate_transcript.md for the appendix.
     Output is commentary only. It feeds no signal, weight or return, and is not in MAIN.py. -->

---

You are the devil's advocate on a market-neutral equity book. Attack the case for the position below.
You are not asked to be balanced.

You get the signed weight, the model's top features with SHAP values, triage output for any 8-K filed
that month, and the realised contribution to P&L.

Find, in order:

1. Disconfirming evidence. A filing, item code or characteristic arguing the other way. Quote it.
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
