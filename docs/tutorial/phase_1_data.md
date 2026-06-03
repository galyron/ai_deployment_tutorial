# Phase 1 — Data: Loading, Streaming, Ensembling

**Capabilities touched:** qualitative + quantitative input handling.
**Exit criterion:** a typed loader, a streaming iterator, and a per-account "ensembler" that produces the payload structure downstream nodes will consume.
**Budget:** 45m–1h.

> **The dataset is already in the repo.** It lives at `data/seed/accounts_quant.csv` and `data/seed/accounts_qual.jsonl` and is small enough (~45KB) to commit. You do *not* generate it. The script that produced it (`scripts/seed_data.py`) is committed alongside as documentation — read it if you ever need to extend the dataset, otherwise ignore it.
>
> **What this phase is.** Phase 1 is the data-access layer. You write the loader, the streamer, and the assembler. Phase 2 indexes the qualitative side into AI Search. Phase 4 calls the ensembler to build LLM payloads.

---

## What's on disk

`data/seed/accounts_quant.csv` — 50 rows. One row per HCP account. Columns:

| column | type | range / values |
|---|---|---|
| `account_id` | str | `HCP-001` … `HCP-050` |
| `segment` | str | `high_potential` / `growing` / `stable` / `at_risk` |
| `territory` | str | `T-North` / `T-South` / `T-East` / `T-West` / `T-Central` |
| `rx_volume_last_q` | int | 20–800 |
| `rx_trend_pct` | float | −50.0 to +50.0 |
| `call_count_last_q` | int | 0–20 |
| `market_potential_score` | int | 1–10 |
| `nps_proxy` | int | −100 to +100 |

`data/seed/accounts_qual.jsonl` — 173 documents across 49 accounts (HCP-005 has none, deliberately). One JSON object per line:

```json
{"account_id": "HCP-002", "source_type": "comp_intel", "text": "Local intelligence flags a notable shift…"}
```

`source_type` is one of: `rep_call_note`, `msl_summary`, `comp_intel`, `market_research`.

### The five accounts that matter for evals (Phase 5)

| account | quant pattern | qual pattern (the tension) |
|---|---|---|
| `HCP-001` | growing, `rx_trend=-22.5` | rep notes are upbeat; never mention the Rx decline |
| `HCP-002` | growing, `rx_trend=+18` | `comp_intel` calls out a credible competitive threat; other docs don't |
| `HCP-003` | stable, `nps=-35` | rep notes describe cooling enthusiasm across visits |
| `HCP-004` | high_potential | `Brand-X` is named *only* in the `market_research` paragraph |
| `HCP-005` | at_risk, thin coverage | **no qualitative documents at all** (graceful-degradation test) |

Phase 5 hard-codes these expectations as ground truth, so do not edit the seed files by hand. If you want to extend the dataset, re-run `scripts/seed_data.py`.

---

### Step 1.1 — Take a look at the data

**Goal:** Build a mental model of the dataset before writing any code against it.

**Do:**
- Open both files. Read three random qualitative documents. Open the quant CSV in your editor's table view.
- Peek at the five tension accounts so you know what the system is supposed to handle.

**Code / commands:**
```bash
head -3 data/seed/accounts_quant.csv
echo "---"
shuf -n 3 data/seed/accounts_qual.jsonl | jq -r '.account_id + " | " + .source_type + " | " + (.text[0:80])'
echo "---"
grep -E '^HCP-00[1-5],' data/seed/accounts_quant.csv
echo "---"
grep -F 'HCP-005' data/seed/accounts_qual.jsonl | wc -l    # must print 0
grep -F 'Brand-X' data/seed/accounts_qual.jsonl | wc -l    # must print 1
```

**Self-check:**
- Three sample qual documents print with their `source_type` and a text snippet.
- The five tension rows print with their pinned values (`HCP-001` rx_trend `-22.5`, `HCP-002` `+18.0`, etc.).
- The two final lines print `0` and `1` respectively.

**If broken:**
- `data/seed/` missing → you're on a fresh clone but `git lfs` or shallow checkout mangled it; try `git restore data/seed/`.

**Time estimate:** ~5m.

---

### Step 1.2 — Schemas

**Goal:** Typed objects for `AccountQuant` and `QualDoc` so downstream code gets autocomplete and rejects malformed records at the boundary.

**Do:**
- Create `acnt_strat_synth/data/schemas.py`.
- Use pydantic v2 — same dependency the synthesis node will use for structured output in Phase 4.

**Code / commands:**
```bash
mkdir -p acnt_strat_synth/data
touch acnt_strat_synth/__init__.py acnt_strat_synth/data/__init__.py
```

```python
# acnt_strat_synth/data/schemas.py
from typing import Literal
from pydantic import BaseModel, Field

Segment    = Literal["high_potential", "growing", "stable", "at_risk"]
Territory  = Literal["T-North", "T-South", "T-East", "T-West", "T-Central"]
SourceType = Literal["rep_call_note", "msl_summary", "comp_intel", "market_research"]

class AccountQuant(BaseModel):
    account_id: str
    segment: Segment
    territory: Territory
    rx_volume_last_q: int = Field(ge=0)
    rx_trend_pct: float = Field(ge=-50, le=50)
    call_count_last_q: int = Field(ge=0, le=20)
    market_potential_score: int = Field(ge=1, le=10)
    nps_proxy: int = Field(ge=-100, le=100)

class QualDoc(BaseModel):
    account_id: str
    source_type: SourceType
    text: str
```

**Self-check:**
```bash
uv run python -c "from acnt_strat_synth.data.schemas import AccountQuant, QualDoc; print(list(AccountQuant.model_fields), list(QualDoc.model_fields))"
```
Prints two field lists — eight names for `AccountQuant`, three for `QualDoc`.

**Time estimate:** ~5m.

---

### Step 1.3 — Eager loader

**Goal:** `load_quant()` and `load_qual()` return validated, in-memory collections. This is what most downstream code calls.

**Do:**
- Create `acnt_strat_synth/data/loader.py`.
- Read CSV via stdlib (no pandas needed at the data-access layer; downstream code can wrap in a DataFrame if it wants).
- Read JSONL line by line.
- Validate each row through the schema.

**Code / commands:**
```python
# acnt_strat_synth/data/loader.py
import csv
import json
from pathlib import Path
from acnt_strat_synth.data.schemas import AccountQuant, QualDoc

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
QUANT_PATH = SEED_DIR / "accounts_quant.csv"
QUAL_PATH  = SEED_DIR / "accounts_qual.jsonl"

_INT_FIELDS   = {"rx_volume_last_q", "call_count_last_q", "market_potential_score", "nps_proxy"}
_FLOAT_FIELDS = {"rx_trend_pct"}

def _coerce_quant_row(row: dict) -> dict:
    out = dict(row)
    for k in _INT_FIELDS:   out[k] = int(out[k])
    for k in _FLOAT_FIELDS: out[k] = float(out[k])
    return out

def load_quant() -> list[AccountQuant]:
    with QUANT_PATH.open() as f:
        return [AccountQuant(**_coerce_quant_row(r)) for r in csv.DictReader(f)]

def load_qual() -> list[QualDoc]:
    return [QualDoc(**json.loads(line))
            for line in QUAL_PATH.read_text().splitlines() if line.strip()]
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.data.loader import load_quant, load_qual
q = load_quant()
d = load_qual()
print(f"quant: {len(q)} rows; qual: {len(d)} docs")
assert len(q) == 50 and len(d) == 173
h005 = [x for x in q if x.account_id == "HCP-005"][0]
assert h005.segment == "at_risk"
print("ok")
PY
```
Prints `quant: 50 rows; qual: 173 docs` and `ok`.

**If broken:**
- `ValidationError` on a row → a CSV value didn't match the schema. Most likely a stale CSV; re-run `python3 scripts/seed_data.py`.
- `FileNotFoundError` → run commands from the repo root, not from `acnt_strat_synth/`.

**Time estimate:** ~15m.

---

### Step 1.4 — Streaming iterator

**Goal:** `iter_accounts()` yields `(AccountQuant, list[QualDoc])` pairs lazily, one account at a time. This is the shape downstream batch jobs (Phase 4 batch run, Phase 5 evals) want when memory matters less than predictable per-record processing.

**Do:**
- Add `iter_accounts()` to `acnt_strat_synth/data/loader.py`.
- Stream the qual JSONL once, group docs by account ID via a dict, then yield (quant, docs) tuples in quant-row order. HCP-005 yields an empty list — do not skip it.

**Code / commands:**
```python
# acnt_strat_synth/data/loader.py  (append)
import json
from collections.abc import Iterator

def _qual_by_account() -> dict[str, list[QualDoc]]:
    grouped: dict[str, list[QualDoc]] = {}
    with QUAL_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = QualDoc(**json.loads(line))
            grouped.setdefault(doc.account_id, []).append(doc)
    return grouped

def iter_accounts() -> Iterator[tuple[AccountQuant, list[QualDoc]]]:
    qual_idx = _qual_by_account()
    for q in load_quant():
        yield q, qual_idx.get(q.account_id, [])
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.data.loader import iter_accounts
counts = {q.account_id: len(docs) for q, docs in iter_accounts()}
assert len(counts) == 50
assert counts["HCP-005"] == 0
assert counts["HCP-001"] >= 3
assert counts["HCP-002"] >= 3
total = sum(counts.values())
print("total qual docs via iterator:", total)
assert total == 173
print("ok")
PY
```
Prints `total qual docs via iterator: 173` and `ok`.

**If broken:**
- Generator returns 50 accounts but `HCP-005` is missing entirely → you skipped accounts with empty doc lists; remove the skip. The graceful-degradation test depends on HCP-005 being yielded with `[]`.

**Time estimate:** ~10m.

---

### Step 1.5 — Per-account ensembler

**Goal:** A function `assemble(account_id)` that produces the dict the LLM-facing nodes want. Decouples "what shape the data is on disk" from "what shape the LLM prompt expects."

**Do:**
- Add `acnt_strat_synth/data/ensemble.py`.
- Return `{account_id, features, docs_by_source}` where `features` is the quant fields the predictive tool reads and `docs_by_source` groups qualitative text by `source_type`.
- This is the contract Phase 3 (predictive tool input), Phase 4 (synthesis node prompt), and Phase 5 (eval harness) all consume — so set it once here.

**Code / commands:**
```python
# acnt_strat_synth/data/ensemble.py
from typing import TypedDict
from acnt_strat_synth.data.loader import load_quant, _qual_by_account

class Payload(TypedDict):
    account_id: str
    segment: str
    territory: str
    features: dict[str, float | int]
    docs_by_source: dict[str, list[str]]

_FEATURE_FIELDS = ["rx_volume_last_q", "rx_trend_pct", "call_count_last_q",
                   "market_potential_score", "nps_proxy"]

_quant_index = {q.account_id: q for q in load_quant()}
_qual_index  = _qual_by_account()

def assemble(account_id: str) -> Payload:
    if account_id not in _quant_index:
        raise KeyError(f"Unknown account: {account_id}")
    q = _quant_index[account_id]

    docs_by_source: dict[str, list[str]] = {}
    for d in _qual_index.get(account_id, []):
        docs_by_source.setdefault(d.source_type, []).append(d.text)

    return Payload(
        account_id=q.account_id,
        segment=q.segment,
        territory=q.territory,
        features={f: getattr(q, f) for f in _FEATURE_FIELDS},
        docs_by_source=docs_by_source,
    )
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.data.ensemble import assemble

p = assemble("HCP-002")
print("HCP-002 sources:", list(p["docs_by_source"]))
assert "comp_intel" in p["docs_by_source"]
assert any("watch-list" in t.lower() or "competit" in t.lower() for t in p["docs_by_source"]["comp_intel"])

p4 = assemble("HCP-004")
mr = " ".join(p4["docs_by_source"]["market_research"])
assert "Brand-X" in mr, "Brand-X must surface through the ensembler for HCP-004"

p5 = assemble("HCP-005")
assert p5["docs_by_source"] == {}
assert p5["features"]["rx_trend_pct"] == -10.0

print("ok")
PY
```
Prints the source list for HCP-002 and `ok`.

**If broken:**
- `Brand-X` not found → an upstream phase mutated the seed file. Reset: `git checkout data/seed/`.

**Time estimate:** ~15m.

---

## What's now wired

After Phase 1, the rest of the tutorial calls into this surface and nothing else:

- `acnt_strat_synth.data.loader.load_quant()` / `load_qual()` — eager loads with schema validation.
- `acnt_strat_synth.data.loader.iter_accounts()` — streaming pairs for batch jobs.
- `acnt_strat_synth.data.ensemble.assemble(account_id)` — the per-account payload Phase 3, 4, and 5 consume.

You are not expected to come back here. If something downstream is wrong with the data, it's because the seed file was edited or `assemble()` lost a field — both easy to bisect.

Commit: `git add -A && git commit -m "phase 1: data access layer over seed dataset"`.
