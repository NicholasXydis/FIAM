Everything above FILING is byte-identical on every call so llama.cpp reuses the KV cache for it.
Only the last two lines change. Do not reorder.

---

Triage one US SEC Form 8-K filing for a systematic equity strategy. Decide whether the disclosure is
material to the stock's next-month return, and in which direction.

- Judge only from the item codes and text below. Use no outside knowledge.
- Company name, ticker, CIK and dates have been removed. Do not guess the issuer or the year. If you
  recognise the event, ignore that and judge the text on its face.
- Most 8-Ks are routine. Default to material = false without a concrete reason otherwise.
- Item 9.01 means an exhibit is attached. The exhibit is not included here, so it carries no information.
- Confident prose is not evidence. Judge the disclosure.
- Evidence must come from the text below, never invented.

Return one JSON object, nothing else:

  material    true if a reasonable investor would reprice the stock on this disclosure alone
  direction   -1 negative, 0 neutral or unclear, 1 positive
  confidence  0.0 to 1.0 in steps of 0.1
  item        the most material item code present, or "none"
  evidence    one sentence from the filing, at most 300 characters

ITEM CODES: 5.02, 9.01
TEXT: The Board appointed Jane Roe as Chief Financial Officer effective immediately, succeeding the prior
officer who resigned to pursue other opportunities.
{"material": true, "direction": -1, "confidence": 0.4, "item": "5.02", "evidence": "The prior Chief Financial Officer resigned and a successor was appointed effective immediately."}

ITEM CODES: 4.02
TEXT: The Audit Committee concluded that previously issued financial statements for the prior two fiscal
years should no longer be relied upon due to errors in revenue recognition.
{"material": true, "direction": -1, "confidence": 0.9, "item": "4.02", "evidence": "Previously issued financial statements should no longer be relied upon due to revenue recognition errors."}

ITEM CODES: 8.01, 9.01
TEXT: The registrant announced that its Board declared a regular quarterly cash dividend, consistent with
the dividend declared in each of the preceding quarters.
{"material": false, "direction": 0, "confidence": 0.8, "item": "8.01", "evidence": "The Board declared a regular quarterly cash dividend consistent with preceding quarters."}

FILING
ITEM CODES: {items}
TEXT: {text}
