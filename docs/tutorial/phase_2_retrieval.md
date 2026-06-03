# Phase 2 — Retrieval + Grounding Layer

**Capabilities touched:** RAG, source traceability.
**Exit criterion:** `retrieve(account_id, query)` returns >0 chunks, each carrying `account_id` and `source_type`.
**Budget:** 1.5h.

---

### Step 2.1 — Chunking strategy and metadata schema

**Goal:** Decide how qualitative documents split into searchable chunks and what metadata travels with each chunk. Traceability requires this contract to be set once.

**Do:**
- Define `Chunk` model: `id`, `account_id`, `source_type`, `text`, `embedding` (filled later).
- Chunk by paragraph; if a doc is short, the whole doc is one chunk.

**Code / commands:**
```bash
mkdir -p src/acnt_strat_synth/retrieval
touch src/acnt_strat_synth/retrieval/__init__.py
```

```python
# src/acnt_strat_synth/retrieval/chunk.py
import re, uuid
from acnt_strat_synth.data.loader import load_qual
from pydantic import BaseModel

class Chunk(BaseModel):
    id: str
    account_id: str
    source_type: str
    text: str

def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 30]

def build_chunks() -> list[Chunk]:
    out = []
    for doc in load_qual():
        for para in split_paragraphs(doc["text"]) or [doc["text"]]:
            out.append(Chunk(
                id=str(uuid.uuid4()),
                account_id=doc["account_id"],
                source_type=doc["source_type"],
                text=para,
            ))
    return out
```

**Self-check:**
```bash
uv run python -c "from acnt_strat_synth.retrieval.chunk import build_chunks; c = build_chunks(); print(len(c), c[0].model_dump())"
```
Prints a count (~100–250) and one chunk dict containing `account_id` and `source_type`.

**If broken:**
- Count is suspiciously low → most qual docs are single-paragraph so chunks ≈ docs; that's expected. If 0 chunks, the qual file is missing.

**Time estimate:** ~15m.

---

### Step 2.2 — Create the AI Search index with vector and filterable metadata

**Goal:** Index schema supports filtered vector search by `account_id`.

**Do:**
- Define an index named `hcp-evidence` with a `text` field, a `content_vector` field (dim 1536, HNSW), and filterable `account_id` + `source_type` fields.

**Code / commands:**
```python
# scripts/create_index.py
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchField, SearchFieldDataType,
    VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
)
from acnt_strat_synth.config import settings

client = SearchIndexClient(settings.search_endpoint, AzureKeyCredential(settings.search_key))

fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True),
    SimpleField(name="account_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="source_type", type=SearchFieldDataType.String, filterable=True),
    SearchableField(name="text", type=SearchFieldDataType.String),
    SearchField(
        name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True, vector_search_dimensions=1536,
        vector_search_profile_name="hnsw-profile",
    ),
]
vs = VectorSearch(
    algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
    profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
)
client.create_or_update_index(SearchIndex(name=settings.search_index, fields=fields, vector_search=vs))
print("index ready:", settings.search_index)
```

```bash
uv run python scripts/create_index.py
```

**Self-check:**
```bash
uv run python - <<'PY'
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from acnt_strat_synth.config import settings
c = SearchIndexClient(settings.search_endpoint, AzureKeyCredential(settings.search_key))
idx = c.get_index(settings.search_index)
print([f.name for f in idx.fields])
PY
```
Output lists exactly `['id', 'account_id', 'source_type', 'text', 'content_vector']`.

**If broken:**
- `Free tier exceeded` → free tier allows 3 indexes / 50MB. Delete an old one: `client.delete_index("old-name")`.

**Time estimate:** ~20m.

---

### Step 2.3 — Embed chunks via Azure OpenAI

**Goal:** Produce a 1536-d vector per chunk.

**Do:**
- Batch chunks through `AzureOpenAIEmbeddings.embed_documents` (handles batching internally).
- Cache embeddings in memory in this run; persistence is the next step.

**Code / commands:**
```python
# scripts/embed_chunks.py
from acnt_strat_synth.retrieval.chunk import build_chunks
from langchain_openai import AzureOpenAIEmbeddings
from acnt_strat_synth.config import settings
import json, pathlib

chunks = build_chunks()
emb = AzureOpenAIEmbeddings(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.embed_deployment,
)
vectors = emb.embed_documents([c.text for c in chunks])
assert len(vectors) == len(chunks)
assert len(vectors[0]) == 1536

records = [{**c.model_dump(), "content_vector": v} for c, v in zip(chunks, vectors)]
pathlib.Path("data/chunks_embedded.jsonl").write_text("\n".join(json.dumps(r) for r in records))
print("embedded", len(records), "chunks")
```

```bash
uv run python scripts/embed_chunks.py
```

**Self-check:** Prints `embedded N chunks` where `N` matches the count from Step 2.1.

**If broken:**
- `DeploymentNotFound` for embedding → `AZURE_OPENAI_EMBED_DEPLOYMENT` in `.env` must match the deployment name from Step 0.4.

**Time estimate:** ~15m.

---

### Step 2.4 — Upload embedded chunks to the index

**Goal:** Documents live in AI Search and are queryable.

**Do:**
- Read the embedded jsonl, push to AI Search via `SearchClient.upload_documents`.

**Code / commands:**
```python
# scripts/upload_chunks.py
import json
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from acnt_strat_synth.config import settings

client = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
docs = [json.loads(l) for l in open("data/chunks_embedded.jsonl")]

BATCH = 100
for i in range(0, len(docs), BATCH):
    client.upload_documents(docs[i:i+BATCH])
print("uploaded", len(docs))
```

```bash
uv run python scripts/upload_chunks.py
```

**Self-check:**
```bash
uv run python - <<'PY'
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from acnt_strat_synth.config import settings
c = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
print("doc count:", c.get_document_count())
PY
```
Doc count matches the upload count.

**If broken:**
- Count shows `0` → indexing isn't instant; wait 30s and re-check.

**Time estimate:** ~10m.

---

### Step 2.5 — Implement the retrieval function

**Goal:** A single function that turns an account ID + query into ranked chunks with source tags.

**Do:**
- Implement vector retrieval with an `account_id` filter.
- Return at most `k` chunks, each with `account_id`, `source_type`, `text`, and search `@score`.

**Code / commands:**
```python
# src/acnt_strat_synth/retrieval/search.py
from dataclasses import dataclass
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from langchain_openai import AzureOpenAIEmbeddings
from acnt_strat_synth.config import settings

@dataclass
class Evidence:
    account_id: str
    source_type: str
    text: str
    score: float

_client = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
_emb = AzureOpenAIEmbeddings(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.embed_deployment,
)

def retrieve(account_id: str, query: str, k: int = 8) -> list[Evidence]:
    qv = _emb.embed_query(query)
    vq = VectorizedQuery(vector=qv, k_nearest_neighbors=k, fields="content_vector")
    results = _client.search(
        search_text=None,
        vector_queries=[vq],
        filter=f"account_id eq '{account_id}'",
        select=["account_id", "source_type", "text"],
        top=k,
    )
    return [Evidence(r["account_id"], r["source_type"], r["text"], r["@search.score"]) for r in results]
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.retrieval.search import retrieve
hits = retrieve("HCP-002", "competitive threat or market dynamics")
for h in hits[:3]:
    print(h.source_type, round(h.score, 3), h.text[:80])
assert all(h.account_id == "HCP-002" for h in hits)
print("ok")
PY
```
Top results include a `comp_intel` chunk; all hits have `account_id == "HCP-002"`.

**If broken:**
- Hits include other accounts → the filter wasn't applied; check the `account_id eq` string syntax and that the field is `filterable=True`.

**Time estimate:** ~15m.

---

### Step 2.6 — Verify graceful degradation for HCP-005

**Goal:** Confirm the retrieval path returns an empty list (not an error) for the account with no qualitative data.

**Do:**
- Call `retrieve("HCP-005", ...)`.

**Code / commands:**
```bash
uv run python -c "from acnt_strat_synth.retrieval.search import retrieve; print(len(retrieve('HCP-005', 'anything')))"
```

**Self-check:** Prints `0`.

**If broken:**
- Prints a positive number → Step 1.4 accidentally generated qual data for HCP-005. Delete those rows from `data/accounts_qual.jsonl`, re-run Steps 2.3 and 2.4.

**Time estimate:** ~10m.

---

### Step 2.7 — Traceability sanity check across all tension accounts

**Goal:** For each tension account, retrieval returns the right source types.

**Do:**
- Iterate the four non-degenerate tension accounts; confirm expected `source_type` is in top results.

**Code / commands:**
```python
# scripts/check_traceability.py
from acnt_strat_synth.retrieval.search import retrieve

cases = [
    ("HCP-001", "rep enthusiasm",       "rep_call_note"),
    ("HCP-002", "competitive pressure", "comp_intel"),
    ("HCP-003", "customer satisfaction signals", "rep_call_note"),
    ("HCP-004", "competitor Brand-X",   "market_research"),
]
for acnt, q, expected in cases:
    hits = retrieve(acnt, q, k=4)
    types = [h.source_type for h in hits]
    print(acnt, "->", types, "OK" if expected in types[:3] else "MISS")
```

```bash
uv run python scripts/check_traceability.py
```

**Self-check:** All four lines end `OK`.

**If broken:**
- `HCP-004 -> MISS` → the Brand-X paragraph may have ended up tokenized differently than the query phrasing; try `"Brand X competitor"` or boost `k`.
- A persistent `MISS` for HCP-001/003 → call notes are too short to differentiate; re-generate that account's qual with stronger tension prompting.

**Time estimate:** ~10m.

---

Phase 2 done. Commit: `git add -A && git commit -m "phase 2: retrieval layer with traceable metadata"`.
