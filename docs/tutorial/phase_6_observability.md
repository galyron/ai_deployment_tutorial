# Phase 6 — Observability + Guardrails

**Capabilities touched:** tracing/cost/latency, guardrails + compliance.
**Exit criterion:** a LangSmith trace screenshot of one graph run, and a unit-tested data-minimization function that strips fields before the LLM sees them.
**Budget:** 1h.

---

### Step 6.1 — Sign in to LangSmith and capture an API key

**Goal:** Have `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` available locally.

**Do:**
- Sign up at `https://smith.langchain.com` (free tier is fine).
- Create a project named `acnt-strat-synth`.
- Generate a personal API key.
- Append to `.env`.

**Code / commands:**
```bash
cat >> .env <<'EOF'
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxx
LANGSMITH_PROJECT=acnt-strat-synth
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
EOF
```

**Self-check:**
```bash
uv run python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(bool(os.getenv('LANGSMITH_API_KEY')))"
# Expected: True
```

**If broken:**
- LangSmith signup blocked by your network → fall back to OpenTelemetry → Azure Monitor (see *Fallback* section at the end of this file).

**Time estimate:** ~10m.

---

### Step 6.2 — Instrument and emit a trace

**Goal:** A single graph run produces a trace tree visible in the LangSmith UI.

**Do:**
- LangSmith auto-instruments `langchain_openai` / `langgraph` when env vars are set; no code change needed.
- Run a single-account synthesis with a recognizable thread ID.

**Code / commands:**
```python
# scripts/trace_one.py
from dotenv import load_dotenv; load_dotenv()
from src.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "trace-demo"}, "tags": ["tutorial", "phase-6"]}
state = g.invoke({"account_id": "HCP-002", "review_required": False}, config=cfg)
print(state["synthesis"].headline)
```

```bash
uv run python scripts/trace_one.py
```

**Self-check:** Open `https://smith.langchain.com` → project `acnt-strat-synth`. The most recent trace has these spans (collapsed):
- `LangGraph` (root) with thread_id `trace-demo`
  - `extract` — N retrieval calls
  - `score` — `account_risk_score` tool span
  - `synth` — one `AzureChatOpenAI` span with token + latency metadata

Take the screenshot of this trace tree; this is the "trace you can point at" deliverable.

**If broken:**
- No trace shows up → `LANGSMITH_TRACING=true` was not loaded; ensure `load_dotenv()` runs *before* importing `src.graph.build`.

**Time estimate:** ~10m.

---

### Step 6.3 — Confirm tokens, latency, and cost are visible

**Goal:** Click into the `synth` span and verify the three numbers that make this "observability," not just logging.

**Do:**
- In the LangSmith trace UI, expand the synth span.
- Confirm visible: total tokens (prompt + completion), latency in ms, USD cost estimate.

**Self-check:** All three are non-zero. If cost shows `--`, click *Settings → Project → Pricing* and confirm GPT-4o pricing is enabled (it is by default on free tier).

**If broken:**
- Tokens visible but cost `--` → set the model in LangSmith's model registry; or accept it and screenshot tokens + latency only. The capability claim is "I can see cost," provable with one mapped row.

**Time estimate:** ~10m.

---

### Step 6.4 — Data-minimization guardrail

**Goal:** A function that strips fields the LLM doesn't need before evidence reaches the synth node. Demonstrates the principle, not a full PII pipeline.

**Do:**
- Define `minimize(evidence_text)` — strips obvious PII patterns (emails, phone numbers, anything matching `Dr\.\s+\w+\s+\w+`).
- Wire it into the extract node.

**Code / commands:**
```python
# src/guardrails/minimize.py
import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?){2,4}\d{2,4}\b")
PERSON_NAME = re.compile(r"\bDr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")

def minimize(text: str) -> str:
    t = EMAIL.sub("[email]", text)
    t = PHONE.sub("[phone]", t)
    t = PERSON_NAME.sub("[person]", t)
    return t
```

```bash
mkdir -p src/guardrails
touch src/guardrails/__init__.py
```

Wire it into the extract node:

```python
# src/graph/nodes.py  (modify extract_node)
from src.guardrails.minimize import minimize
# ...
            seen[key] = EvidenceItem(
                chunk_id=f"E-{len(seen)+1:03d}",
                account_id=hit.account_id,
                source_type=hit.source_type,
                text=minimize(hit.text),
            )
```

**Self-check:**
```bash
uv run python -c "from src.guardrails.minimize import minimize; print(minimize('Contact Dr. Anna Lee at anna.lee@example.com or +44 20 7946 0958'))"
# Expected: Contact [person] at [email] or [phone]
```

**Time estimate:** ~15m.

---

### Step 6.5 — Unit test the minimization

**Goal:** A pytest test that locks the contract — emails, phones, and `Dr. Firstname Lastname` are always replaced.

**Do:**
- Add `tests/test_minimize.py`.

**Code / commands:**
```python
# tests/test_minimize.py
from src.guardrails.minimize import minimize

def test_email_redacted():
    assert minimize("write to foo@bar.com") == "write to [email]"

def test_phone_redacted():
    assert "[phone]" in minimize("call +44 20 7946 0958 today")

def test_person_name_redacted():
    out = minimize("Dr. Anna Lee was friendly")
    assert "Dr." not in out and "Anna" not in out

def test_non_pii_preserved():
    s = "Rx volume is up 12% in Q3."
    assert minimize(s) == s
```

```bash
mkdir -p tests && touch tests/__init__.py
uv run pytest tests/test_minimize.py -q
```

**Self-check:** `4 passed`.

**If broken:**
- `test_phone_redacted` fails → the phone regex is permissive on purpose; if it over-redacts in real text, prefer false-positive PII removal over false-negative leakage. Document the trade-off as a comment.

**Time estimate:** ~10m.

---

### Fallback — OpenTelemetry → Azure Monitor

If LangSmith is unavailable (corporate network, signup blocked), use Azure Monitor instead. The capability claim still holds: a trace exists, you can point at it.

```bash
uv add opentelemetry-sdk opentelemetry-exporter-otlp azure-monitor-opentelemetry
```

```python
# src/observability.py
from azure.monitor.opentelemetry import configure_azure_monitor
import os

def init_tracing():
    cs = os.environ.get("APPINSIGHTS_CONNECTION_STRING")
    if cs:
        configure_azure_monitor(connection_string=cs)
```

Create an Application Insights resource, copy its connection string into `.env` as `APPINSIGHTS_CONNECTION_STRING`, call `init_tracing()` at process start. Run `scripts/trace_one.py`; the trace appears in *Portal → Application Insights → Transaction search*.

---

Phase 6 done. Commit: `git add -A && git commit -m "phase 6: tracing + minimization guardrail"`.
