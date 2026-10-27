# Filing text into dated tables: sections, footprint, customers.

import gzip
import hashlib
import html
import json
import os
import re
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EDGAR = ROOT / "data" / "edgar"
OUT = ROOT / "data" / "v4" / "text"
# The text rules, set before any extraction.
MIN_SECTION = 500
NEAR = 40
ANNUAL = ("10-K", "10-KT", "10-K405")
BATCH = 4000
# Each section's heading and the headings of the items that end it.
HEADINGS = {
    "1a": (
        (r"item\s*1\.?\s*a\b", r"risk\s+factors|risks\b"),
        [
            (r"item\s*1\.?\s*b\b", r"unresolved\s+staff"),
            (r"item\s*1\.?\s*c\b", r"cybersecurity"),
            (r"item\s*2\b", r"(?:description\s+of\s+)?propert"),
        ],
    ),
    "7": (
        (r"item\s*7\b(?!\.?\s*a\b)", r"management(?:.{0,2}s)?\s+discussion"),
        [
            (
                r"item\s*7\.?\s*a\b",
                r"(?:quantitative|qualitative)\s+and\s+(?:quantitative|qualitative)",
            ),
            (r"item\s*8\b", r"(?:consolidated\s+)?financial\s+statements"),
        ],
    ),
    "2": (
        (r"item\s*2\b", r"(?:description\s+of\s+)?propert"),
        [(r"item\s*3\b", r"legal\s+proceedings")],
    ),
}
NOT_BEFORE = re.compile(r"\b(see|in|under|refer|described)\b[^.]{0,40}$", re.I)
# Tags that end a block of text: a heading always starts one.
BLOCK = r"p|div|br|tr|td|th|li|ul|ol|table|h[1-6]|title|center|hr|pre|blockquote|dt|dd"
HTML = re.compile(r"(?i)<(?:html|body|p|div|table|tr|td|br|font|span)\b")
# What a page may print before a heading on its line (page, part).
PAGE_HEAD = re.compile(
    r"^(?:\s|\d{1,3}|[ivx]{1,4}\b|table\s+of\s+contents|index|part\s+(?:i{1,3}|iv)\b|[-.,:|–—])*$",
    re.I,
)
# Below this many blocks a document has no layout to read headings from.
FEW_BLOCKS = 20
# Safe-harbour words, with any hyphen or a space in "forward-looking".
BOILERPLATE = re.compile(
    r"forward[\s\-\u2010\u2011\u2012\u2013\u2014]?looking\s+(?:statement|information)|"
    r"private securities litigation reform act|safe harbor|undue reliance",
    re.I,
)
# A stop, then a capital or a new block; checked against abbreviations.
STOP = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])|\n")
# Words whose full stop never ends a sentence ("Michael S.", "Mr.").
NO_STOP = re.compile(
    r"(?:\b[A-Z]|\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|No|Nos|Inc|Corp|Co|Ltd|Messrs|Hon|Gen|Vol|"
    r"U\.S|L\.P|N\.A|Ph\.D))\.$"
)
ROLES = re.compile(
    r"chief executive officer|chief financial officer|principal executive officer|"
    r"principal financial officer|\bCEO\b|\bCFO\b",
    re.I,
)
LEAVING = re.compile(
    r"\b(resign(?:s|ed|ing|ation)?|retir(?:e|es|ed|ing)|"
    r"retirement(?!\s+(?:plans?|savings|benefits?|income|accounts?|programs?|agreements?))|"
    r"step(?:s|ped|ping)?\s+down|depart(?:s|ed|ing|ure)|terminat(?:e|es|ed|ing|ion)|"
    r"separat(?:ed|es|ion)\s+from|not\s+(?:to\s+)?stand\s+for\s+re-?election|"
    r"(?<!medical )leav(?:e|es|ing)(?!\s+of\s+absence)|left\s+(?:the|his|her|its|our)|"
    r"transition(?:s|ed|ing)?\s+(?:out\s+of|from|to\s+a\s+new\s+(?:role|position))|ceas(?:e|es|ed|ing)\s+to\s+(?:be|serve|hold)|"
    r"relinquish(?:es|ed|ing)?|succeed(?:s|ed|ing)?|replac(?:e|es|ed|ing))\b",
    re.I,
)
# The item's own title names departures, so it is read as no event.
TITLE_502 = re.compile(
    r"departure\s+of\s+directors\s+(?:or|of|and)\s+(?:certain|principal)\s+officers", re.I
)
# Pay and severance terms say what would happen, not what did.
IF_ONLY = re.compile(
    r"\b(?:if|unless|in\s+the\s+event|in\s+case|entitled|eligible)\b|"
    r"\bwould\s+(?:receive|be\s+entitled|be\s+eligible|be\s+paid|vest)\b|"
    r"\bmay\s+be\s+terminated\b|"
    r"upon\s+(?:a\s+|an\s+|any\s+|such\s+|his\s+|her\s+)?(?:qualif\w+\s+)?terminat",
    re.I,
)
DISAGREE = re.compile(r"\bdisagree\w*\b", re.I)
# A disagreement denied ("not the result of any disagreement") is none.
DENIED = re.compile(r"\b(not|no|never|without|none|nor|other\s+than)\b|n[’']t\b", re.I)
STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    "Puerto Rico": "PR",
}  # fmt: skip
STATE_NAMES = re.compile(r"\b(" + "|".join(sorted(STATES, key=len, reverse=True)) + r")\b")
# A state name in any case or a capital code; the country may follow.
STATE = (
    r"\b((?i:" + "|".join(sorted(STATES, key=len, reverse=True)) + r")|"
    + "|".join(sorted(set(STATES.values()))) + r")\b\.?\s*,?\s*"
    + r"(?:(?i:united\s+states(?:\s+of\s+america)?|u\.?s\.?a\.?)\s*,?\s*)?"
)  # fmt: skip
STATE_ZIP = re.compile(STATE + r"(\d{5})(?:-\d{4})?\b")
# A comma, then a state name or code, right after a state name.
STATE_AFTER = re.compile(
    r",[^\S\n]*(" + "|".join(sorted(STATES, key=len, reverse=True)) + r"|[A-Z]{2})\b"
)
# A property's state code: "Evansville, IN" or "Dallas TX 75201" only.
STATE_CODE = re.compile(
    r",[^\S\n]*([A-Z]{2})(?=[^\S\n]*(?:\d{5}\b|[;,.)]|$|(?:and|or|AND|OR)\b|[a-z]))"
    r"|\b([A-Z]{2})(?=[^\S\n]+\d{5}\b)",
    re.M,
)
LABEL = re.compile(
    r"principal\s+(?:executive|corporate|administrative|business)\s+offices?\b", re.I
)
# "Irving TX (Address of principal executive offices) 75039" on a cover.
STATE_LABEL = re.compile(
    STATE + r"(?:\((?i:zip\s+code)\)\s*)?"
    r"\((?i:[^)]{0,60}principal\s+\w+\s+offices?\b[^)]{0,40})\)"
    r"\s*(?:\((?i:zip\s+code)\)\s*)?(\d{5})?"
)
# The inline XBRL cover tags (2019 on) hold the same address fields.
XBRL = r'name="dei:{}"[^>]*>(?:\s*<[^>]+>)*\s*([^<]{{1,40}})'
CODES = set(STATES.values())
SHARE = r"(\d{1,3}(?:\.\d+)?)\s*%"
# Verbs, one share or a list, then plain words to revenue or sales.
CUSTOMER = re.compile(
    r"\b(?:accounted\s+for|represented|comprised)\s+"
    r"(?:(?P<floor>over|more\s+than|in\s+excess\s+of|greater\s+than|at\s+least|exceeding)\s+|"
    r"(?:approximately|about|nearly|roughly|almost)\s+)?"
    rf"(?P<shares>{SHARE}(?:\s*(?:,\s*and|,|and)\s*(?:approximately\s+)?{SHARE})*)"
    r"(?P<more>\s+or\s+more)?,?\s+(?:respectively,?\s+)?of\s+"
    r"(?:(?:our|the|its|total|consolidated|net|gross|company.?s|annual|worldwide|operating|"
    r"aggregate|reported|combined|overall|fiscal|\d{4})\s+){0,4}(?:revenues?|sales)\b",
    re.I,
)
# A customer cue in the sentence, so a product line is never a customer.
CUE = re.compile(
    r"\b(customers?|clients?|sales\s+to|revenues?\s+from|shipments\s+to|sold\s+to|"
    r"purchases\s+by|distributors?|wholesalers?|retailers?|payors?|payers?)\b",
    re.I,
)
# After the share only "no other customer" confirms a customer.
TAIL_CUE = re.compile(r"\b(?:no\s+)?other\s+(?:single\s+|individual\s+)?(?:customer|client)", re.I)
# "Sales of X" names a product, never a customer.
PRODUCT = re.compile(r"\b(?:sales|revenues?)\s+of\s+(?:our\s+|the\s+|its\s+)?$", re.I)
TOKEN = re.compile(r"[A-Za-z0-9][\w&.'’\-]*|&|,|[()]")
SUFFIX = re.compile(
    r"^(?:inc|corp|co|ltd|llc|l\.l\.c|l\.p|lp|plc|n\.v|n\.a|s\.a|ag|se|limited|"
    r"incorporated|corporation|company)\.?$",
    re.I,
)
# Tokens ending in a full stop that never end a sentence.
ABBREV = re.compile(r"^(?:[A-Z]\.)+$|^(?:St|Jr|Mr|Mrs|Dr)\.$")
CONNECT = {"&", "and", "of", "de", "the", "du", "la"}
LEAD = {
    "In", "During", "For", "Additionally", "Also", "However", "Further", "Furthermore",
    "Approximately", "The", "Each", "Both", "Only", "Collectively", "Together", "While",
    "Although", "Whereas", "When", "As", "Since", "Thus", "Therefore", "Accordingly",
    "Moreover", "Similarly", "Historically", "Currently", "Generally", "Typically",
}  # fmt: skip
GOVERNMENT = re.compile(
    r"\b(government|federal|department|agency|agencies|ministry|army|navy|air\s+force|DoD|"
    r"Medicare|Medicaid|state\s+of|commonwealth|county|city\s+of|NASA|postal\s+service)\b",
    re.I,
)
UNNAMED = re.compile(
    r"\b(customers?|clients?|dealers?|distributors?|wholesalers?|retailers?|licensees?|resellers?|"
    r"payors?|payers?|tenants?|lessees?|purchasers?|operators?|partners?|parties|GPOs?|"
    r"group\s+purchasing)\b",
    re.I,
)
# Words that make a "name" a region, period or revenue line instead.
GENERIC = set(
    "sales revenue revenues international domestic foreign export exports product products "
    "service services segment segments us u.s. usa united states america americas north south "
    "east west europe european asia pacific china japan canada india mexico latin emea apac "
    "fiscal year years quarter quarters january february march april may june july august "
    "september october november december total net gross other our its we top ten five "
    "largest major significant oem oems retail wholesale direct indirect online and of the "
    "& a an one two three four africa australia austria belgium brazil britain france germany "
    "hong kong ireland israel italy korea middle netherlands singapore spain sweden "
    "switzerland taiwan uk kingdom".split()
)
# A word that makes a name part of the filer, never a customer.
PART = re.compile(
    r"\b(segments?|divisions?|business(?:es)?|products?|lines?|units?|table\s+of\s+contents)\b"
    r"|^(?:sales|revenues?|net)\s+(?:of|from|in|for)\b",
    re.I,
)


# A main document as text, one line per block, tags out, entities read.
def html_text(raw: str) -> str:
    # Scripts, styles and the hidden inline XBRL header are not text.
    raw = re.sub(r"(?is)<(script|style|ix:header)[^>]*>.*?</\1>", " ", raw)
    # HTML source newlines are spaces; a plain-text blank line is a block.
    if HTML.search(raw):
        raw = re.sub(r"[\r\n]+", " ", raw)
    else:
        raw = re.sub(r"\s*\n\s*\n\s*", "<p>", raw).replace("\n", " ")
    # Inline formatting splits words ("R<span>isk</span>"): no space there.
    raw = re.sub(r"(?i)</?(?:span|font|b|i|u|a|em|strong|sup|sub|small|big)\b[^>]*>", "", raw)
    raw = re.sub(rf"(?i)</?(?:{BLOCK})\b[^>]*>", "\n", raw)
    text = re.sub(r"<[^>]+>", " ", raw)
    # Compatibility forms (the "fi" ligature in "offices") made plain.
    text = unicodedata.normalize("NFKC", html.unescape(text))
    text = re.sub(r"[​‌‍⁠﻿]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r" *\n[\n ]*", "\n", text).strip()


# The text on one line, exactly as the first footprint check read it.
def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Whether a match begins its block, after at most a page header.
def block_start(text: str, at: int) -> bool:
    line = text[text.rfind("\n", 0, at) + 1 : at]
    return len(line) <= 80 and bool(PAGE_HEAD.match(line))


# Item headings: the title within 40 characters, no cross-reference.
def headings(
    text: str, item: str, title: str, after: int = 0, bare: bool = False
) -> list[re.Match]:
    laid_out = text.count("\n") >= FEW_BLOCKS
    out = []
    for m in re.compile(item, re.I).finditer(text, after):
        line = text[text.rfind("\n", 0, m.start()) + 1 : m.start()] if laid_out else ""
        before = line if laid_out else text[max(0, m.start() - NEAR) : m.start()]
        rest = text[m.end() : text.find("\n", m.end()) if "\n" in text[m.end() :] else None]
        # A stop may print its item alone on a line ("Item 7A." and no title).
        alone = bare and laid_out and len(rest.strip(" .:-–—")) == 0
        head = re.search(title, text[m.end() : m.end() + NEAR + 40], re.I)
        if not alone and (head is None or head.start() > NEAR):
            continue
        if re.match(r"\s*[,\"“”]", text[m.end() : m.end() + 3]) or re.search(
            r"[\"“‘']\s?$", before[-2:]
        ):
            continue
        if NOT_BEFORE.search(before[-NEAR:]):
            continue
        # A title closed by ")" or a quote is a reference, not a heading.
        if head is not None and re.match(r"[ .]*[)”\"]", text[m.end() + head.end() :]):
            continue
        if laid_out and not block_start(text, m.start()):
            continue
        out.append(m)
    return out


# A 10-K section: the longest span from a heading to the next item's.
def section(text: str, which: str, minimum: int = MIN_SECTION) -> str | None:
    (item, title), stops = HEADINGS[which]
    best = None
    for m in headings(text, item, title):
        ends = [h.start() for s, st in stops for h in headings(text, s, st, m.end(), True)[:1]]
        if not ends:
            continue
        span = text[m.start() : min(ends)]
        if best is None or len(span) > len(best):
            best = span
    return best if best is not None and len(best) >= minimum else None


# Sentences split at stops and blocks, never after "Mr." or an initial.
def sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in STOP.finditer(text):
        if m.group(0) != "\n" and NO_STOP.search(text[max(0, m.start() - 8) : m.start()]):
            continue
        out.append(text[start : m.start()])
        start = m.end()
    out.append(text[start:])
    return [s for s in out if s.strip()]


# Text without its safe-harbour and forward-looking sentences.
def strip_boilerplate(text: str) -> str:
    return " ".join(s for s in sentences(text) if not BOILERPLATE.search(s))


# Whether a sentence names a sitting CEO or CFO, not a former one.
def names_role(sentence: str) -> bool:
    for m in ROLES.finditer(sentence):
        before = sentence[max(0, m.start() - 30) : m.start()]
        if re.search(r"\bformer(?:ly)?\s+(?:\w+\s+){0,2}$", before, re.I):
            continue
        # "Chief Executive Officer of a SaaS company" is another firm's role.
        if re.match(r"\s+of\s+(?:a|an|another)\b", sentence[m.end() : m.end() + 12], re.I):
            continue
        return True
    return False


# The 5.02 red-flag rule: a CEO or CFO leaving, or a director's dispute.
def departure_502(text: str) -> dict:
    said = sentences(TITLE_502.sub(" ", text))
    officer = any(names_role(s) and LEAVING.search(s) and not IF_ONLY.search(s) for s in said)
    dispute = any(
        DISAGREE.search(s) and re.search(r"\bdirector", s, re.I) and not DENIED.search(s)
        for s in said
    )
    return {"ceo_cfo_leaving": officer, "director_disagreement": dispute}


# Cover headquarters: XBRL tags, the state at the label, the nearest.
def headquarters(text: str, raw: str = "") -> tuple[str | None, str | None]:
    tag = re.search(XBRL.format("EntityAddressStateOrProvince"), raw)
    if tag:
        value = html.unescape(tag.group(1)).strip()
        state = STATES.get(value.title(), value.upper())
        if state in CODES:
            code = re.search(XBRL.format("EntityAddressPostalZipCode"), raw)
            return state, code.group(1).strip()[:5] if code else None
    cover = text[:200000]
    mark = LABEL.search(cover)
    if not mark:
        name = re.search(r"exact\s+name\s+of\s+(?:the\s+)?registrant", cover, re.I)
        first = STATE_ZIP.search(cover[name.end() : name.end() + 1500]) if name else None
        if first is None:
            return None, None
        return STATES.get(first.group(1).title(), first.group(1).upper()), first.group(2)
    lo = max(0, mark.start() - 600)
    window = cover[lo : mark.end() + 300]
    for m in STATE_LABEL.finditer(window):
        if lo + m.start() <= mark.start() <= lo + m.end():
            state = m.group(1)
            return STATES.get(state.title(), state.upper()), m.group(2)
    found = list(STATE_ZIP.finditer(window))
    if not found:
        return None, None
    best = min(found, key=lambda m: abs(lo + m.end() - mark.start()))
    state = best.group(1)
    return STATES.get(state.title(), state.upper()), best.group(2)


# A state name placing a site, not a city, river or company name.
def is_state(body: str, m: re.Match) -> bool:
    name, after = m.group(1), body[m.end() : m.end() + 40]
    before = body[max(0, m.start() - 8) : m.start()]
    if name == "Washington" and re.match(r",?\s*D\.?\s*C\b", after):
        return False
    if name == "Kansas" and re.match(r"\s+City", after):
        return False
    if re.search(r"\b(?:Fort|Mount|Mt\.|Lake|Port|Saint|St\.)\s+$", before):
        return False
    # ", NC" after a name, or any state after "Washington," marks a town.
    other = STATE_AFTER.match(after)
    code = STATES.get(other.group(1), other.group(1)) if other else None
    town = other and (len(other.group(1)) == 2 or name == "Washington")
    if town and code in CODES and code != STATES[name]:
        return False
    # A capitalised word right after is a proper name, except "City".
    return not re.match(r"[^\S\n]+(?!City\b)[A-Z][a-z]", after)


# Item 2's states, by name or by a capital code after a comma or a ZIP.
def property_states(text: str) -> list[str]:
    body = section(text, "2", minimum=1) or ""
    found = [
        (m.start(), STATES[m.group(1)]) for m in STATE_NAMES.finditer(body) if is_state(body, m)
    ]
    found += [(m.start(), "DC") for m in re.finditer(r"Washington,?\s*D\.?\s*C\b", body)]
    codes = [(m.start(), m.group(1) or m.group(2)) for m in STATE_CODE.finditer(body)]
    found += [(at, code) for at, code in codes if code in CODES]
    return list(dict.fromkeys(code for _, code in sorted(found)))


# The capitalised words before a share, back to a lower-case word.
def name_before(fragment: str, listed: bool) -> list[str]:
    fragment = re.sub(r"\s*\([^()]{0,60}\)", "", fragment).rstrip(" ,")
    tokens, name = TOKEN.findall(fragment), []
    for tok in reversed(tokens):
        if tok in "()":
            break
        # A comma stays only before a legal suffix or inside a list.
        if tok == ",":
            if name and (SUFFIX.match(name[0]) or listed):
                name.insert(0, tok)
                continue
            break
        ends = tok.endswith(".") and not SUFFIX.match(tok) and not ABBREV.match(tok)
        if name and ends:
            break
        if tok[0].isupper() or (tok[0].isdigit() and re.search(r"[A-Za-z]", tok)) or tok == "&":
            name.insert(0, tok)
        elif tok.lower() in CONNECT and name:
            name.insert(0, tok)
        else:
            break
    while name and (name[0] in LEAD or name[0].lower() in CONNECT or name[0] == ","):
        name.pop(0)
    # A heading word such as "Revenues" before the name is not part of it.
    if (
        len(name) > 1
        and name[0].lower() in {"revenues", "revenue", "sales"}
        and name[1][0].isupper()
    ):
        name.pop(0)
    return name


# A token list as written: commas closed up, the full stop kept.
def joined(tokens: list[str]) -> str:
    return " ".join(tokens).replace(" ,", ",").strip(" ,")


# A mention's kind: named, government, unnamed, joint or none at all.
def kind_of(name: str) -> str:
    if GOVERNMENT.search(name):
        return "government"
    words = [w for w in re.split(r"[\s,]+", name.lower()) if w and not SUFFIX.match(w)]
    # "B" alone is what is left of "Customer B": a customer, but unnamed.
    if UNNAMED.search(name) or not words or re.fullmatch(r"[A-Z]\.?", name):
        return "unnamed"
    if all(w.strip(".") in GENERIC or w in GENERIC for w in words) or PART.search(name):
        return "none"
    # One share for "Lowe's and Home Depot" belongs to neither alone.
    if re.search(r"\sand\s", name):
        return "joint"
    return "named"


# The current sentence's start, after its block and real full stop.
def sentence_tail(lead: str) -> str:
    lead = lead[lead.rfind("\n") + 1 :]
    cut = 0
    for m in re.finditer(r"(\S+)[.!?]\s+(?=[A-Z(])", lead):
        word = m.group(1) + "."
        if not SUFFIX.match(word) and not ABBREV.match(word.split(",")[-1]):
            cut = m.end()
    return lead[cut:]


# One name's latest-year share, or None when the years are not printed.
def latest_share(shares: list[float], after: str) -> float | None:
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", after[:90])]
    if len(years) == len(shares) and len(set(years)) == len(years):
        return shares[years.index(max(years))]
    return None


# Customers with 10% or more of revenue: (name, share, kind, floor).
def customers(text: str) -> list[tuple[str, float, str, bool]]:
    out = []
    for m in CUSTOMER.finditer(text):
        shares = [float(s) for s in re.findall(SHARE, m.group("shares"))]
        floor = bool(m.group("floor") or m.group("more"))
        sentence = sentence_tail(text[max(0, m.start() - 300) : m.start()])
        tail = text[m.end() : m.end() + 250]
        if not CUE.search(sentence) and not TAIL_CUE.search(tail):
            continue
        tokens = name_before(sentence, listed=len(shares) > 1)
        name = joined(tokens)
        if tokens and PRODUCT.search(sentence[: sentence.rfind(tokens[0])]):
            continue
        if len(shares) > 1:
            parts = [joined(TOKEN.findall(p)) for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", name)]
            parts = [p for p in parts if p and not SUFFIX.match(p)]
            if len(parts) == len(shares):
                pairs = list(zip(parts, shares))
            elif len(parts) == 1:
                latest = latest_share(shares, text[m.end() : m.end() + 90])
                pairs = [] if latest is None else [(parts[0], latest)]
            else:
                continue
        else:
            pairs = [(name, shares[0])]
        for one, pct in pairs:
            if not one:
                gap = UNNAMED.search(sentence[-60:])
                one = sentence[-60:].strip() if gap else ""
            kind = kind_of(one) if one else "none"
            if 10 <= pct <= 100 and kind != "none":
                out.append((one, pct, kind, floor))
    return list(dict.fromkeys(out))


# Legal words and filler dropped before names are compared.
LEGAL = re.compile(
    r"\b(the|inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|"
    r"group|nv|sa|ag|lp|se|spa|bv|ab|asa|new|del)\b"
)
OVERLAP = 0.8
MATCH_YEARS = 3


# A company name reduced for matching: lower case, words, no suffixes.
def normal_name(name: str) -> str:
    s = re.sub(r"\(last known\)", " ", str(name), flags=re.I).lower()
    s = re.sub(r"['’`.]", "", s.replace("&", " and "))
    s = LEGAL.sub(" ", re.sub(r"[^a-z0-9 ]", " ", s))
    return " ".join(s.split())


# Named customers to the one CRSP stock whose dated name matches.
def match_customers(found: pd.DataFrame, names: pd.DataFrame) -> pd.DataFrame:
    names = names.reset_index(drop=True)
    keys = names["value"].map(normal_name)
    words = keys.str.split().map(set)
    exact: dict[str, list[int]] = {}
    index: dict[str, set[int]] = {}
    for i, key in enumerate(keys):
        exact.setdefault(key.replace(" ", ""), []).append(i)
        for w in words[i]:
            index.setdefault(w, set()).add(i)
    start, stop = names["valid_from"].to_numpy(), names["valid_to"].to_numpy()
    permno = names["permno"].to_numpy()
    hits, how = [], []
    for r in found.itertuples():
        key = normal_name(r.customer)
        since = r.filing_date - pd.DateOffset(years=MATCH_YEARS)

        # The candidate rows in force in the window, filer left out.
        def live(rows):
            return {
                int(permno[i])
                for i in rows
                if start[i] <= r.filing_date
                and (pd.isna(stop[i]) or stop[i] >= since)
                and permno[i] != r.permno
            }

        same = live(exact.get(key.replace(" ", ""), [])) if key else set()
        if len(same) == 1:
            hits.append(same.pop())
            how.append("exact")
            continue
        mine = set(key.split())
        near = set().union(*(index.get(w, set()) for w in mine)) if mine and not same else set()
        close = live(i for i in near if len(mine & words[i]) / len(mine | words[i]) > OVERLAP)
        hits.append(close.pop() if len(close) == 1 else None)
        how.append("overlap" if hits[-1] is not None else "none")
    return found.assign(customer_permno=pd.array(hits, dtype="Int64"), match=how)


# One annual report's rows: both sections, footprint and customers.
def read_annual(row: tuple[int, str]) -> dict:
    cik, accession = row
    path = EDGAR / "docs" / str(cik) / f"{accession}.gz"
    raw = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
    text = html_text(raw)
    item1a, item7 = section(text, "1a"), section(text, "7")
    state, zipcode = headquarters(flat(text), raw[:400000])
    return {
        "accession": accession,
        "cik": cik,
        "item1a": strip_boilerplate(item1a) if item1a else None,
        "item7": strip_boilerplate(item7) if item7 else None,
        "hq_state": state,
        "hq_zip": zipcode,
        "property_states": ",".join(property_states(text)),
        "customers": json.dumps(customers(text)),
        "chars": len(text),
    }


# One 5.02 8-K's rule flags from its text.
def read_502(row: tuple[int, str]) -> dict:
    cik, accession = row
    path = EDGAR / "docs" / str(cik) / f"{accession}.gz"
    text = html_text(gzip.decompress(path.read_bytes()).decode("utf-8", "replace"))
    return {"accession": accession, "cik": cik} | departure_502(text)


# Runs a reader over many filings in parallel, in a stable order.
def run_all(reader, rows: list[tuple[int, str]], workers: int | None = None) -> pd.DataFrame:
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        out = list(pool.map(reader, rows, chunksize=64))
    return pd.DataFrame(out)


# The filings with a saved document, by kind, from the EDGAR index.
def held(kind: str) -> list[tuple[int, str]]:
    f = pd.read_parquet(EDGAR / "filings.parquet", columns=["cik", "form", "accession", "items"])
    saved = set()
    for line in (EDGAR / "docs" / "log.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if "path" in entry:
            saved.add("/".join(entry["path"].removesuffix(".gz").split("/")[-2:]))
    if kind == "annual":
        f = f[f["form"].isin(ANNUAL)]
    else:
        f = f[
            (f["form"] == "8-K") & f["items"].fillna("").str.split(",").map(lambda s: "5.02" in s)
        ]
    # A saved document without a receipt is a gap, never silently skipped.
    disk = {f"{p.parent.name}/{p.stem}" for p in (EDGAR / "docs").glob("*/*.gz")}
    if disk - saved:
        raise RuntimeError(f"{len(disk - saved)} documents lack a receipt: edgar.py relog")
    # A joint filing is read from the filer whose copy is saved.
    f = f[(f["cik"].astype(int).astype(str) + "/" + f["accession"]).isin(saved)]
    f = f.drop_duplicates("accession")
    return list(zip(f["cik"].astype(int), f["accession"]))


# Builds the raw text tables: uv run python -m fiam.vfinal.text
if __name__ == "__main__":
    folder = OUT / "annual"
    folder.mkdir(parents=True, exist_ok=True)
    rows = held("annual")
    for n, at in enumerate(range(0, len(rows), BATCH)):
        part = run_all(read_annual, rows[at : at + BATCH])
        part.to_parquet(folder / f"part-{n:02d}.parquet", index=False, compression="zstd")
        print(f"annual {min(at + BATCH, len(rows)):,} of {len(rows):,}", flush=True)
    keep = ["accession", "item1a", "item7", "hq_state", "customers"]
    annual = pd.read_parquet(folder, columns=keep)
    found = {c: round(float(annual[c].notna().mean()), 4) for c in ("item1a", "item7", "hq_state")}
    five = run_all(read_502, held("502"))
    five.to_parquet(OUT / "five02.parquet", index=False)
    report = {"annual_reports": len(annual)} | {f"{c}_found": v for c, v in found.items()}
    report["with_customers"] = round(float((annual["customers"] != "[]").mean()), 4)
    report |= {"five02_filings": len(five), "ceo_cfo_leaving": int(five["ceo_cfo_leaving"].sum())}
    report["director_disagreement"] = int(five["director_disagreement"].sum())
    # Inputs and code by hash, so the build can be traced and repeated.
    report["code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["receipts_sha256"] = hashlib.sha256(
        (EDGAR / "docs" / "log.jsonl").read_bytes()
    ).hexdigest()
    (OUT / "build.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
