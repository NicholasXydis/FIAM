# FinBERT reads each masked 8-K excerpt once, then means by stock-month.

import hashlib

import numpy as np
import pandas as pd
import torch
from sklearn.decomposition import PCA

from fiam import book as P
from fiam import data, paths

# FinBERT (Araci 2019), trained on pre-2020 text, at a pinned revision.
MODEL, REVISION = "ProsusAI/finbert", "4556d13015211d73dccd3fdd39d39232506f3e43"
FOLDER = P.CACHE / "text"
MONTHLY = FOLDER / "finbert_monthly.parquet"
# Principal components a model sees, fitted on its training years only.
COMPONENTS = 32
CHUNK, BATCH = 20_000, 64
WIDTH = 768


# The fastest device here: Apple's GPU, then CUDA or ROCm, then the CPU.
def device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# FinBERT's tokenizer and encoder, fetched once at the pinned revision.
def encoder():
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModel.from_pretrained(MODEL, revision=REVISION).to(device()).eval()
    return tokenizer, model


# Excerpts to vectors: the last layer's mean over each excerpt's tokens.
def embed(texts: list[str], tokenizer, model) -> np.ndarray:
    order = np.argsort([len(t) for t in texts])
    out = np.zeros((len(texts), WIDTH), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(texts), BATCH):
            at = order[start : start + BATCH]
            batch = tokenizer(
                [texts[i] for i in at],
                truncation=True,
                max_length=512,
                padding=True,
                return_tensors="pt",
            ).to(model.device)
            hidden = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            mean = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            out[at] = mean.float().cpu().numpy()
    return out


# A chunk's vectors depend on the revision, settings and every excerpt.
def fingerprint(chunk: pd.DataFrame) -> str:
    digest = hashlib.sha256(f"{REVISION}|512|mean|{WIDTH}".encode())
    for document, excerpt in zip(chunk["document_id"], chunk["excerpt"]):
        digest.update(f"{document}\0{excerpt}\0".encode())
    return digest.hexdigest()


# Every filing's vector by chunk, so a stopped run resumes where it was.
def filing_vectors(texts: pd.DataFrame) -> pd.DataFrame:
    FOLDER.mkdir(parents=True, exist_ok=True)
    tokenizer, model = None, None
    parts = []
    for number, start in enumerate(range(0, len(texts), CHUNK)):
        path = FOLDER / f"finbert_{number:03d}.parquet"
        stamp = path.with_suffix(".sha256")
        chunk = texts.iloc[start : start + CHUNK]
        want = fingerprint(chunk)
        # A pre-stamp chunk holding exactly these filings is stamped once.
        if path.exists() and not stamp.exists():
            ids = pd.read_parquet(path, columns=["document_id"])["document_id"]
            if ids.equals(chunk["document_id"].reset_index(drop=True)):
                stamp.write_text(want, encoding="utf-8")
        # Any change of model, settings or text makes the chunk again.
        if not stamp.exists() or stamp.read_text(encoding="utf-8") != want:
            if model is None:
                tokenizer, model = encoder()
            vectors = embed(chunk["excerpt"].tolist(), tokenizer, model)
            frame = pd.DataFrame(vectors, columns=[f"v{i}" for i in range(WIDTH)])
            frame.insert(0, "document_id", chunk["document_id"].to_numpy())
            frame.to_parquet(path, index=False)
            stamp.write_text(want, encoding="utf-8")
            print(f"  {min(start + CHUNK, len(texts)):,} of {len(texts):,} filings", flush=True)
        parts.append(pd.read_parquet(path))
    return pd.concat(parts, ignore_index=True)


# Every filing's saved vector, without embedding anything new.
def saved_vectors() -> pd.DataFrame | None:
    chunks = sorted(FOLDER.glob("finbert_[0-9]*.parquet"))
    return pd.concat([pd.read_parquet(c) for c in chunks], ignore_index=True) if chunks else None


# Each stock-month's mean filing vector, keyed on the filing month.
def monthly(texts: pd.DataFrame, vectors: pd.DataFrame) -> pd.DataFrame:
    joined = texts[["document_id", *data.KEYS]].merge(vectors, on="document_id")
    return joined.drop(columns="document_id").groupby(data.KEYS).mean().reset_index()


# Each row's stock-month vector as a float32 matrix, NaN with no filing.
def aligned(frame: pd.DataFrame) -> np.ndarray | None:
    if not MONTHLY.exists():
        return None
    table = data.read(MONTHLY)
    keys = frame[data.KEYS].reset_index(drop=True)
    at = keys.merge(table[data.KEYS].reset_index(), on=data.KEYS, how="left")["index"]
    out = np.full((len(frame), WIDTH), np.nan, dtype=np.float32)
    found = at.notna().to_numpy()
    values = table[[f"v{i}" for i in range(WIDTH)]].to_numpy(dtype=np.float32)
    out[found] = values[at[found].astype(int).to_numpy()]
    return out


# Principal components fitted on a model's train rows, applied to all.
def components(matrix: np.ndarray, train: np.ndarray) -> np.ndarray:
    out = np.full((len(matrix), COMPONENTS), np.nan, dtype=np.float32)
    has = ~np.isnan(matrix[:, 0])
    fit = train & has
    if fit.sum() < 10 * COMPONENTS:
        return out
    pca = PCA(COMPONENTS, svd_solver="full").fit(matrix[fit])
    out[has] = pca.transform(matrix[has])
    return out


# The component columns a model reads, by name.
NAMES = [f"text_pc_{i + 1}" for i in range(COMPONENTS)]


# Embeds every filing and writes the monthly FinBERT table.
def main() -> None:
    texts = data.research("filing_text", ["document_id", "permno", "eom", "excerpt"])
    if texts is None:
        print("no filing_text layer in the bundle; rebuild it with uv run -m fiam.build_data")
        return
    texts = texts.sort_values("document_id", ignore_index=True)
    # A rehearsal embeds a sample, always with the triage agent's labels.
    if paths.SMOKE:
        labels = paths.EXHIBITS / "agents" / "triage_labels.parquet"
        keep = set(pd.read_parquet(labels)["document_id"]) if labels.exists() else set()
        chosen = texts["document_id"].isin(keep) | texts.index.isin(
            texts.sample(2_000, random_state=42).index
        )
        texts = texts[chosen].reset_index(drop=True)
    table = monthly(texts, filing_vectors(texts))
    table.to_parquet(MONTHLY, index=False)
    print(f"  {len(table):,} stock-months with filings, on {device()}")


if __name__ == "__main__":
    main()
