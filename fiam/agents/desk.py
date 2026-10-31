# The desk agents' shared parts: inputs, the number check, clean words.

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from fiam.agents import final_book as F

PACK = F.PACK
DESK = PACK / "desk"
LOG = DESK / "calls.jsonl"
NUMBERS = F.NUMBERS_PACK / "numbers.json"
DATA = F.NUMBERS_PACK / "data"
CROWD_LIVE = PACK / "crowd_aug" / "crowd_where_we_sit.json"
HYPE = PACK / "hype_map" / "results.json"
TRIAGE = PACK / "triage" / "triage_final.json"
ANALYST = PACK / "analyst" / "analyst_final.json"
RULES = PACK / "rules" / "rules_check.json"
EXPLAINER = PACK / "explanations.json"
# A number as written: digits, thousands commas, one decimal part.
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# Units a writer may move a number through: as is, percent, thousands.
FACTORS = (1, 100, 1000)
# Claims the record cannot support, never let into anything written.
OVERCLAIMS = (
    r"out[- ]of[- ]sample",
    r"\b(?:fixed|frozen|designed|set|built|locked)\b[^.]*\bbefore 2021\b",
)
# Words that compare the number before them with the number after.
ABOVE = r"above|over|exceeds|more than|higher than"
BELOW = r"below|under|within|inside|less than|lower than"
# Advice on trades or weights, which no desk agent may give.
ADVICE = (
    r"\b(?:should|ought to|recommend\w*|advis\w*)\b",
    r"\bsuggest\w*\s+(?:that\s+)?(?:we|you|the (?:fund|desk|committee)|to)\b",
    r"\b(?:we|you|the committee)\s+(?:could|might|may)\s+consider\b",
    r"\b(?:to|we|you|(?:could|might|may|must|needs? to))\s+(?:raise|lower|cut|reduce|trim|"
    r"increase|add|boost|shrink|buy|sell|cover|hedge)\b(?!-off)",
)


# A JSON file, or None when that agent has not written it yet.
def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# A path as the records show it: from the repo root when inside it.
def rel(path: Path) -> str:
    path = Path(path).resolve()
    return path.relative_to(F.H.ROOT).as_posix() if path.is_relative_to(F.H.ROOT) else str(path)


# Writes JSON with a newline, keys in the order given.
def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=1, ensure_ascii=False, default=str)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


# Writes text with one closing newline.
def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


# Every number in a text as written, thousands commas taken out.
def numbers(text: str) -> list[str]:
    plain_minus = (text or "").replace("−", "-")
    return [n.rstrip(",").replace(",", "") for n in NUMBER.findall(plain_minus)]


# All values a source shows, sign dropped, for the number check.
def shown(source: str) -> list[float]:
    return sorted({abs(float(n)) for n in numbers(source)})


# A number is supported if a shown value rounds to it at its precision.
def supported(token: str, values: list[float]) -> bool:
    token = token.replace(",", "")
    value = float(token)
    if value in (0.0, 1.0):
        return True
    places = len(token.split(".")[1]) if "." in token else 0
    for v in values:
        for f in FACTORS:
            if abs(round(v * f, places) - value) < 1e-9:
                return True
    return False


# The numbers in a text that no shown value supports.
def unsupported(text: str, values: list[float]) -> list[str]:
    return [n for n in numbers(text) if not supported(n, values)]


# A text cut into sentences; decimal points never end one.
def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z$\"'(\d])", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


# Which banned patterns a sentence hits, by list name.
def breaks(sentence: str, advice: bool) -> list[str]:
    found = [f"overclaim {p}" for p in OVERCLAIMS if re.search(p, sentence, re.IGNORECASE)]
    if advice:
        found += [f"advice {p}" for p in ADVICE if re.search(p, sentence, re.IGNORECASE)]
    return found


# Comparisons a sentence gets backwards, say "a above b" when a is less.
def wrong_sides(sentence: str) -> list[str]:
    nums = [(m.start(), m.end(), m.group()) for m in NUMBER.finditer(sentence)]
    wrong = []
    for word in re.finditer(rf"\b(?:{ABOVE}|{BELOW})\b", sentence, re.IGNORECASE):
        before = [n for n in nums if n[1] <= word.start()]
        after = [n for n in nums if n[0] >= word.end()]
        if not before or not after:
            continue
        a = abs(float(before[-1][2].replace(",", "")))
        b = abs(float(after[0][2].replace(",", "")))
        up = re.fullmatch(ABOVE, word.group(), re.IGNORECASE) is not None
        if (a > b) != up and a != b:
            wrong.append(f"{before[-1][2]} {word.group()} {after[0][2]}")
    return wrong


# Keeps sentences whose numbers trace and whose words keep the rules.
def check(
    text: str, values: list[float], advice: bool = False, sides: bool = False
) -> tuple[str, list[dict]]:
    kept, dropped = [], []
    for s in sentences(plain(text)):
        bad, broken = unsupported(s, values), breaks(s, advice)
        if sides:
            broken += [f"wrong side {w}" for w in wrong_sides(s)]
        if bad or broken:
            dropped.append(dict(text=s, unsupported_numbers=bad, broken_rules=broken))
        else:
            kept.append(s)
    return " ".join(kept), dropped


# Audience copy: no dashes, colons, semicolons or Oxford commas.
def plain(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"(?<=\d)\s*[–—]\s*(?=\d)", " to ", s)
    s = re.sub(r"\s*[–—]\s*", ", ", s)
    s = re.sub(r"(?<=\d):(?=\d)", " to ", s)
    s = re.sub(r"\s*:\s*", ", ", s)
    s = re.sub(r";\s*(\w)", lambda m: ". " + m.group(1).upper(), s)
    s = s.replace(";", ".")
    while True:
        after = re.sub(r"(,[^,.]{1,60}), (and|or) ", r"\1 \2 ", s)
        if after == s:
            break
        s = after
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\.\s*,", ".", s)
    return re.sub(r"\s{2,}", " ", s).strip()


# Whether a line keeps the on-screen rules and a length limit.
def screen_ok(line: str, limit: int) -> bool:
    if len(line) > limit or re.search(r"[–—:;]", line):
        return False
    return re.search(r",[^,.]{1,60}, (?:and|or) ", line) is None


# 1st, 2nd, 51st: an ordinal for a percentile.
def nth(n: int) -> str:
    n = int(n)
    end = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{end}"


# A file's last change as a date, for the agents' map.
def stamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


# A model call through the logged asker, retried once on bad numbers.
def ask_checked(asker, key: str, user: str, fields: list[str], values: list[float]) -> dict:
    first = asker.ask(key, user)
    answer = first["parsed"] or {}
    bad = sorted({n for f in fields for n in unsupported(plain(str(answer.get(f, ""))), values)})
    calls = [dict(key=key, error=first["error"], unsupported_numbers=bad)]
    if bad or first["error"] or not answer:
        listed = ", ".join(bad) or "none, but the answer was empty or failed"
        fix = (
            f"{user}\n\nA first answer quoted numbers that are not in the facts ({listed}). "
            "Write the answer again using only numbers printed in the facts, exactly as "
            "printed or rounded."
        )
        again = asker.ask(key + "_retry", fix)
        if again["parsed"]:
            answer = again["parsed"]
        calls.append(dict(key=key + "_retry", error=again["error"]))
    return dict(answer=answer, calls=calls)


# Runs the desk: `uv run python -m fiam.agents.desk [memo|risk|devil]`
def main(argv: list[str]) -> None:
    from fiam.agents import devil, found, memo, risk_desk

    steps = dict(memo=memo.run, risk=risk_desk.run, devil=devil.run, found=found.run)
    chosen = [a for a in argv if a in steps] or list(steps)
    for name in chosen:
        steps[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
