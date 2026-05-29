# Phase 1 — Synthetic Data Generation

**Capabilities touched:** qualitative + quantitative input handling.
**Exit criterion:** ~50 HCP accounts on disk (parquet + json), including 5 deliberately seeded *tension* accounts you can name by ID.
**Budget:** 1–1.5h.

---

### Step 1.1 — Data module skeleton and schemas

**Goal:** A typed schema for both quantitative and qualitative data so later phases can rely on field names.

**Do:**
- Create `src/data/` with `schemas.py`.
- Define a `pydantic` `AccountQuant` and `AccountQual`.

**Code / commands:**
```bash
mkdir -p src/data data
touch src/data/__init__.py
```

```python
# src/data/schemas.py
from typing import Literal
from pydantic import BaseModel, Field

Segment   = Literal["high_potential", "growing", "stable", "at_risk"]
Territory = Literal["T-North", "T-South", "T-East", "T-West", "T-Central"]
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
uv run python -c "from src.data.schemas import AccountQuant; print(AccountQuant.model_fields.keys())"
# Expected: dict_keys(['account_id', 'segment', 'territory', 'rx_volume_last_q', 'rx_trend_pct', 'call_count_last_q', 'market_potential_score', 'nps_proxy'])
```

**If broken:**
- `pydantic.errors.PydanticUserError` on `Literal` → ensure pydantic v2 (`uv pip show pydantic` shows `2.x`).

**Time estimate:** ~10m.

---

### Step 1.2 — Generate the 50-account quantitative dataset

**Goal:** A reproducible parquet file with 50 HCP accounts spanning realistic distributions.

**Do:**
- Write `scripts/gen_quant.py` with a fixed seed.
- Sample fields per the schema, persist to `data/accounts_quant.parquet`.

**Code / commands:**
```python
# scripts/gen_quant.py
import random, pandas as pd
from src.data.schemas import AccountQuant

random.seed(7)
segments    = ["high_potential", "growing", "stable", "at_risk"]
territories = ["T-North", "T-South", "T-East", "T-West", "T-Central"]

rows = []
for i in range(1, 51):
    seg = random.choices(segments, weights=[2, 3, 4, 1])[0]
    rows.append(AccountQuant(
        account_id=f"HCP-{i:03d}",
        segment=seg,
        territory=random.choice(territories),
        rx_volume_last_q=random.randint(20, 800),
        rx_trend_pct=round(random.uniform(-30, 30), 1),
        call_count_last_q=random.randint(0, 20),
        market_potential_score=random.randint(3, 10),
        nps_proxy=random.randint(-40, 70),
    ).model_dump())

pd.DataFrame(rows).to_parquet("data/accounts_quant.parquet", index=False)
print("wrote", len(rows), "rows")
```

```bash
uv run python scripts/gen_quant.py
```

**Self-check:**
```bash
uv run python - <<'PY'
import pandas as pd
df = pd.read_parquet("data/accounts_quant.parquet")
assert len(df) == 50
assert df["segment"].isin(["high_potential","growing","stable","at_risk"]).all()
print(df[["account_id","segment","rx_trend_pct","nps_proxy"]].head())
PY
```
50 rows, no assertion failure, head() prints.

**If broken:**
- `ValidationError` from pydantic → a sampled value fell outside the declared range; verify the `random.randint` / `random.uniform` arguments match the schema bounds.

**Time estimate:** ~15m.

---

### Step 1.3 — Seed the five tension accounts

**Goal:** Five deterministically known accounts that violate the surface signal. These are the Phase-5 ground truth.

**Do:**
- Overwrite five specific rows in the parquet with hand-picked field values.
- Document the expected pattern for each.

**Code / commands:**
```python
# scripts/seed_tensions.py
import pandas as pd

df = pd.read_parquet("data/accounts_quant.parquet")

tensions = {
    "HCP-001": dict(segment="growing",        rx_trend_pct=-22.5, nps_proxy=60,  call_count_last_q=18),  # rep over-optimistic
    "HCP-002": dict(segment="growing",        rx_trend_pct=18.0,  nps_proxy=50,  call_count_last_q=8),   # rising-but-threatened watch-list
    "HCP-003": dict(segment="stable",         rx_trend_pct=1.0,   nps_proxy=-35, call_count_last_q=10),  # early-warning NPS drop
    "HCP-004": dict(segment="high_potential", rx_trend_pct=5.0,   nps_proxy=20,  call_count_last_q=6),   # competitor only in MR snippet (traceability)
    "HCP-005": dict(segment="at_risk",        rx_trend_pct=-10.0, nps_proxy=10,  call_count_last_q=2),   # no qualitative data (graceful degradation)
}

for acct_id, patch in tensions.items():
    mask = df["account_id"] == acct_id
    for k, v in patch.items():
        df.loc[mask, k] = v

df.to_parquet("data/accounts_quant.parquet", index=False)
print(df[df["account_id"].isin(tensions)][["account_id","segment","rx_trend_pct","nps_proxy"]])
```

```bash
uv run python scripts/seed_tensions.py
```

**Self-check:** Printed five rows match the table below (rounded):

| account_id | segment | rx_trend_pct | nps_proxy |
|---|---|---|---|
| HCP-001 | growing | -22.5 | 60 |
| HCP-002 | growing | 18.0 | 50 |
| HCP-003 | stable | 1.0 | -35 |
| HCP-004 | high_potential | 5.0 | 20 |
| HCP-005 | at_risk | -10.0 | 10 |

**If broken:**
- Missing rows → re-run Step 1.2 first; the seed script depends on the IDs from the generated parquet.

**Time estimate:** ~15m.

---

### Step 1.4 — Generate qualitative free-text per account via Azure OpenAI

**Goal:** For each non-HCP-005 account, produce 1–3 rep call notes, 0–1 MSL summary, 0–1 comp-intel snippet, 0–1 market-research paragraph — varied, realistic, and *consistent with the tension seed where applicable*.

**Do:**
- For HCP-001 force "upbeat call notes despite declining Rx."
- For HCP-002 force a competitive threat only in comp-intel.
- For HCP-003 distribute NPS-drop signal across rep notes.
- For HCP-004 mention competitor `Brand-X` only inside the market-research paragraph.
- For HCP-005 produce nothing.
- For all others, generate neutral varied text.

**Code / commands:**
```python
# scripts/gen_qual.py
import json, random
from pathlib import Path
import pandas as pd
from langchain_openai import AzureChatOpenAI
from src.config import settings

random.seed(13)
df = pd.read_parquet("data/accounts_quant.parquet")

chat = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.chat_deployment, temperature=0.7,
)

TENSION_PROMPTS = {
    "HCP-001": "Notes are UPBEAT and confident about the relationship, even though prescribing volume is actually declining sharply. Do not mention the decline.",
    "HCP-002": "Comp-intel snippet must describe a credible competitive threat from a rival brand. Other documents should NOT mention any threat.",
    "HCP-003": "Rep call notes should describe small grievances and signs of cooling enthusiasm across multiple visits. Do not state the NPS number.",
    "HCP-004": "Market-research paragraph must explicitly name a competitor 'Brand-X' once. No other document may name Brand-X.",
}

def gen(prompt: str) -> str:
    return chat.invoke(prompt).content.strip()

docs = []
for _, row in df.iterrows():
    acct = row["account_id"]
    if acct == "HCP-005":
        continue  # graceful-degradation test: no qual data

    tension = TENSION_PROMPTS.get(acct, "")
    seg, terr = row["segment"], row["territory"]
    ctx = f"HCP account {acct}, segment={seg}, territory={terr}. {tension}".strip()

    # 1-3 rep call notes
    for _ in range(random.randint(1, 3)):
        docs.append({"account_id": acct, "source_type": "rep_call_note",
                     "text": gen(f"{ctx}\nWrite ONE realistic 80-120 word pharma rep call note in first person. No headers. No bullet points.")})

    if random.random() < 0.6:
        docs.append({"account_id": acct, "source_type": "msl_summary",
                     "text": gen(f"{ctx}\nWrite ONE 80-120 word MSL interaction summary. Neutral clinical tone.")})

    if random.random() < 0.5 or acct == "HCP-002":
        docs.append({"account_id": acct, "source_type": "comp_intel",
                     "text": gen(f"{ctx}\nWrite ONE 60-100 word competitive-intelligence snippet about this account's brand-loyalty dynamics.")})

    if random.random() < 0.4 or acct == "HCP-004":
        docs.append({"account_id": acct, "source_type": "market_research",
                     "text": gen(f"{ctx}\nWrite ONE 100-140 word market-research paragraph covering the prescriber's specialty area at the territory level.")})

Path("data/accounts_qual.jsonl").write_text("\n".join(json.dumps(d) for d in docs))
print("wrote", len(docs), "qualitative docs")
```

```bash
uv run python scripts/gen_qual.py
```

> This call costs ~$0.10–0.30 depending on how many tokens GPT-4o emits.

**Self-check:**
```bash
uv run python - <<'PY'
import json, collections
docs = [json.loads(l) for l in open("data/accounts_qual.jsonl")]
by_acct = collections.Counter(d["account_id"] for d in docs)
print("total docs:", len(docs))
print("HCP-005 doc count:", by_acct.get("HCP-005", 0))  # expected: 0
print("distinct accounts with docs:", len(by_acct))     # expected: 49
PY
```
HCP-005 count is `0`, distinct count is `49`.

**If broken:**
- `RateLimitError` → reduce `--sku-capacity` was too small; either raise it (Step 0.4) or add `time.sleep(1)` between calls.
- Wallclock blows past 10 minutes → parallelize with `concurrent.futures.ThreadPoolExecutor(max_workers=4)`.

**Time estimate:** ~20m.

---

### Step 1.5 — Spot-check the seeded tensions

**Goal:** Confirm GPT-4o respected the tension prompts. This is the eval target — if it didn't, fix the prompt now, not in Phase 5.

**Do:**
- Print the comp-intel for HCP-002, the market-research for HCP-004, and one rep note from HCP-001.

**Code / commands:**
```python
# scripts/inspect_tensions.py
import json
docs = [json.loads(l) for l in open("data/accounts_qual.jsonl")]

def pick(acct, src):
    return next((d["text"] for d in docs if d["account_id"] == acct and d["source_type"] == src), None)

print("--- HCP-001 rep_call_note ---")
print(pick("HCP-001", "rep_call_note"))
print("\n--- HCP-002 comp_intel ---")
print(pick("HCP-002", "comp_intel"))
print("\n--- HCP-004 market_research ---")
print(pick("HCP-004", "market_research"))
print("\n--- Brand-X mentions across all docs ---")
print(sum("Brand-X" in d["text"] for d in docs), "occurrences")
```

```bash
uv run python scripts/inspect_tensions.py
```

**Self-check:**
- HCP-001 rep note tone is positive/confident; no mention of decline.
- HCP-002 comp-intel mentions a competitor or threat.
- HCP-004 market-research paragraph contains the string `Brand-X`.
- Brand-X occurrences = `1` (only HCP-004 market-research).

**If broken:**
- Brand-X appears in >1 doc → the LLM leaked the name. Re-run only HCP-004's qual generation with a stricter prompt: `"Only the market-research paragraph for HCP-004 may name Brand-X."`
- HCP-001 note mentions decline → tighten the tension prompt to "Do not mention any negative signal."

**Time estimate:** ~10m.

---

### Step 1.6 — Persist a combined view and load round-trip

**Goal:** A single loader function later phases call to fetch accounts + their documents.

**Do:**
- Write `src/data/loader.py` with `load_quant()` and `load_qual()`.
- Verify both round-trip.

**Code / commands:**
```python
# src/data/loader.py
import json
from pathlib import Path
import pandas as pd

QUANT_PATH = Path("data/accounts_quant.parquet")
QUAL_PATH  = Path("data/accounts_qual.jsonl")

def load_quant() -> pd.DataFrame:
    return pd.read_parquet(QUANT_PATH)

def load_qual() -> list[dict]:
    return [json.loads(line) for line in QUAL_PATH.read_text().splitlines() if line.strip()]
```

**Self-check:**
```bash
uv run python - <<'PY'
from src.data.loader import load_quant, load_qual
q = load_quant()
d = load_qual()
print(f"quant rows: {len(q)}, qual docs: {len(d)}")
assert len(q) == 50
assert {x["source_type"] for x in d} <= {"rep_call_note","msl_summary","comp_intel","market_research"}
print("ok")
PY
```
Prints counts and `ok`.

**If broken:**
- File not found → re-run Steps 1.2 and 1.4.

**Time estimate:** ~10m.

---

Phase 1 done. Commit: `git add -A && git commit -m "phase 1: synthetic data + tension seeds"`.
