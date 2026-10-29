# The final book, its SEC filings and a logged local model to read them.

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.agents import harness as H
from fiam.vfinal import clock
from fiam.vfinal import text as T

EDGAR = H.ROOT / "data" / "edgar"
WORK = Path(os.environ.get("FIAM_WORK", str(Path.home() / "FIAM_work")))
BOOK = WORK / "ai_ca_plan" / "final_book_2026-08-31.csv"
PACK = WORK / "vfinal_pack" / "ai"
# The book's date: a filing counts only if accepted by its last minute.
AS_OF = "2026-08-31"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
# A number as printed: digits, thousands commas, one decimal part.
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# A percentage, a table's bracketed "(37.2) %" included.
PERCENT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\)?\s*%")
# Growing waits while the shared model server is busy or restarting.
WAITS = (10, 30, 60, 120, 240)
MAX_TOKENS = 2048
FETCH_WORKERS = 4


# The book's names with their side and SEC id, largest first.
def book(path: Path = BOOK) -> pd.DataFrame:
    held = pd.read_csv(path)
    links = pd.read_parquet(EDGAR / "cik_map.parquet", columns=["permno", "cik"])
    held = held.merge(links, on="permno", how="left")
    held["side"] = np.where(held["w"] > 0, "long", "short")
    return held.sort_values("w", key=abs, ascending=False, ignore_index=True)


# Whether each filing is public on EDGAR by the book's last minute.
def public_by(accepted, filing_date, day: str = AS_OF) -> pd.Series:
    seen = clock.edgar_available(accepted, filing_date)
    cutoff = (pd.Timestamp(day) + clock.END_OF_DAY).tz_localize(clock.EASTERN)
    return (seen <= cutoff).reset_index(drop=True)


# The repo's SEC fetcher: paced, with the contact header SEC asks for.
def sec(url: str) -> bytes:
    from fiam.alt import sixty_first

    return sixty_first.edgar().fetch(url)


# A document's bytes, read once from SEC and kept gzipped in a cache.
def cached(url: str, path: Path) -> bytes:
    if path.exists():
        return gzip.decompress(path.read_bytes())
    body = sec(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(gzip.compress(body))
    partial.replace(path)
    return body


# A filing's folder on EDGAR.
def folder(cik: int, accession: str) -> str:
    return f"{ARCHIVE}/{int(cik)}/{accession.replace('-', '')}"


# A filing's main document as text, from the local cache or else SEC.
def main_text(cik: int, accession: str, document: str, cache: Path) -> str:
    local = EDGAR / "docs" / str(int(cik)) / f"{accession}.gz"
    if local.exists():
        raw = gzip.decompress(local.read_bytes())
    else:
        url = f"{folder(cik, accession)}/{document}"
        raw = cached(url, cache / str(int(cik)) / f"{accession}.gz")
    return T.html_text(raw.decode("utf-8", "replace"))


# A filing's exhibit 99 documents, 99.1 first, from its index page.
def exhibit_urls(cik: int, accession: str, cache: Path) -> list[str]:
    from fiam.alt import sixty_first

    base = folder(cik, accession)
    page = cached(f"{base}/{accession}-index.htm", cache / str(int(cik)) / f"{accession}_index.gz")
    out = []
    for row in (r for t in sixty_first.tables(page.decode("utf-8", "replace")) for r in t):
        kinds = [c for c in row if re.fullmatch(r"EX-99(\.0?1)?\S*", c)]
        docs = [c.split()[0] for c in row if re.search(r"\.html?\b", c)]
        if kinds and docs:
            out.append((kinds[0], f"{base}/{docs[0]}"))
    out.sort(key=lambda k: (not re.fullmatch(r"EX-99\.0?1", k[0]), k[0]))
    return [url for _, url in out]


# A filing's first exhibit 99 as text, or empty when it has none.
def exhibit_text(cik: int, accession: str, cache: Path) -> str:
    urls = exhibit_urls(cik, accession, cache)
    if not urls:
        return ""
    raw = cached(urls[0], cache / str(int(cik)) / f"{accession}_ex99.gz")
    return T.html_text(raw.decode("utf-8", "replace"))


# Runs one reader over many filings on a few threads, in a stable order.
def fetch_all(reader, rows: list) -> list:
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        return list(pool.map(reader, rows))


# Every periodic report a company filed, from the bulk submissions file.
def periodic(cik: int, forms: tuple = ("10-Q", "10-K", "10-KT")) -> pd.DataFrame:
    keys = ["form", "filingDate", "acceptanceDateTime", "accessionNumber", "primaryDocument"]
    keys += ["reportDate"]
    with zipfile.ZipFile(EDGAR / "submissions.zip") as zf:
        names = set(zf.namelist())
        doc = json.loads(zf.read(f"CIK{int(cik):010d}.json"))
        pages = [doc["filings"]["recent"]]
        extra = [p["name"] for p in doc["filings"].get("files", []) if p["name"] in names]
        pages += [json.loads(zf.read(name)) for name in extra]
    table = pd.concat(
        [pd.DataFrame({k: p.get(k) or [""] * len(p["form"]) for k in keys}) for p in pages],
        ignore_index=True,
    )
    return table[table["form"].isin(forms)].reset_index(drop=True)


# Each number in a text, commas out, trailing decimal zeros dropped.
def numbers(text: str, pattern: re.Pattern = NUMBER) -> list[str]:
    out = []
    for raw in pattern.findall(text or ""):
        value = raw.rstrip(",").replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        out.append(value or "0")
    return out


# A text kept only if its numbers and percentages are in the source.
def number_check(texts: list[str], source: str) -> tuple[list[str], list[dict]]:
    printed, percents = set(numbers(source)), set(numbers(source, PERCENT))
    kept, dropped = [], []
    for said in texts:
        missing = [n for n in numbers(said) if n not in printed]
        missing += [f"{n}%" for n in numbers(said, PERCENT) if n in printed and n not in percents]
        if missing:
            dropped.append(dict(text=said, unsupported_numbers=missing))
        else:
            kept.append(said)
    return kept, dropped


# A text's SHA-256, to key and replay a prompt.
def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# What the model server says about itself, slots included.
def server_props(url: str) -> dict:
    with urllib.request.urlopen(f"{url}/props", timeout=10) as r:
        p = json.loads(r.read())
    return dict(
        build=p.get("build_info"),
        model_path=p.get("model_path"),
        context=p.get("default_generation_settings", {}).get("n_ctx"),
        slots=p.get("total_slots"),
    )


# Waits up to five minutes for the shared server's health check.
def wait_healthy(url: str, seconds: int = 300) -> bool:
    end = time.monotonic() + seconds
    while True:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=10) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except OSError, ValueError:
            pass
        if time.monotonic() > end:
            return False
        time.sleep(10)


# Asks a served model many prompts in parallel, logging each call.
class Asker:
    # The log to write, the set system prompt and the answer's shape.
    def __init__(self, log: Path, system: str, schema: dict):
        if not H.REMOTE:
            raise SystemExit("set FIAM_LLM_URL to the served Gemma, say http://127.0.0.1:8082")
        self.log, self.system, self.schema = log, system, schema
        self.lock, self.server, self.props = threading.Lock(), None, {}
        self.fresh = 0

    # Checks the server, then loads answers already logged for a resume.
    def __enter__(self) -> Asker:
        if not wait_healthy(H.REMOTE):
            raise SystemExit(f"no healthy model server at {H.REMOTE}")
        self.server = H.Server("gemma").__enter__()
        self.props = server_props(self.server.url)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        self.done = {}
        for row in map(json.loads, lines):
            if row.get("error") is None and row.get("system_sha256") == digest(self.system):
                self.done[(row["key"], row["user_sha256"])] = row
        self.handle = self.log.open("a", encoding="utf-8", newline="\n")
        return self

    # Closes the log.
    def __exit__(self, *exc) -> None:
        self.handle.close()

    # One prompt's call, retried while the server is busy, then logged.
    def ask(self, key: str, user: str) -> dict:
        if (key, digest(user)) in self.done:
            return self.done[(key, digest(user))]
        messages = [dict(role="system", content=self.system), dict(role="user", content=user)]
        started, error, reply, attempts = datetime.now(UTC).isoformat(), None, {}, 0
        clock0 = time.monotonic()
        for wait in (0, *WAITS):
            time.sleep(wait)
            attempts += 1
            try:
                reply, error = self.server.chat(messages, schema=self.schema), None
                break
            except urllib.error.HTTPError as exc:
                error = f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}"
                if exc.code < 500 and exc.code != 429:
                    break
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"
        row = dict(
            key=key,
            started_utc=started,
            seconds=round(time.monotonic() - clock0, 1),
            attempts=attempts,
            error=error,
            server=dict(url=self.server.url, **self.props),
            request=dict(
                model=self.server.name,
                messages=messages,
                schema=self.schema,
                temperature=H.TEMPERATURE,
                seed=H.SEED,
                max_tokens=MAX_TOKENS,
            ),
            system_sha256=digest(self.system),
            user_sha256=digest(user),
            reply=reply.get("content"),
            parsed=H.parse(reply) if reply else {},
        )
        with self.lock:
            self.handle.write(json.dumps(row) + "\n")
            self.handle.flush()
            self.fresh += 1
            if self.fresh % 50 == 0:
                print(f"  {self.log.parent.name}: {self.fresh:,} new calls", flush=True)
        return row

    # Every prompt asked on as many threads as the server has slots.
    def ask_all(self, prompts: list[tuple[str, str]]) -> list[dict]:
        workers = max(1, min(int(self.props.get("slots") or 1), 4))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda kp: self.ask(*kp), prompts))

    # The run's model settings and call counts, for the record.
    def accounting(self, rows: list[dict], format_failures: int) -> dict:
        return dict(
            model=self.server.name,
            model_file=H.MODELS[self.server.name][1],
            servers_at_call_time=[
                dict(json.loads(k), calls=int(n))
                for k, n in pd.Series(
                    [json.dumps(r["server"], sort_keys=True) for r in rows], dtype=object
                )
                .value_counts()
                .items()
            ],
            temperature=H.TEMPERATURE,
            seed=H.SEED,
            max_tokens=MAX_TOKENS,
            reply_shape="JSON schema enforced by the server",
            threads="one per server slot, at most four",
            system_prompt_sha256=digest(self.system),
            prompts=len(rows),
            calls_made_this_run=self.fresh,
            answers_reused_from_log=len(rows) - self.fresh,
            server_failures=sum(r["error"] is not None for r in rows),
            retried=sum(r["attempts"] > 1 for r in rows),
            http_attempts=sum(r["attempts"] for r in rows),
            calls_in_log=len(self.log.read_text(encoding="utf-8").splitlines()),
            format_failures=format_failures,
        )
